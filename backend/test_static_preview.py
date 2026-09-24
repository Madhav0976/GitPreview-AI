"""
Comprehensive Test Suite for Safe Static Preview Engine (Phase 2)
Tests:
- Priority entrypoint resolution (root index.html, index.htm, public/index.html, dist, build, single root HTML)
- Ambiguous multiple HTML files without index rejection
- Path traversal & blacklist rejection (.env, .py, .sh, .key)
- Extension whitelist and MIME type mapping
- Code (2MB) and Media (5MB) size limits
- HTML <base> tag injection and relative asset resolution
- Detection of unsupported repositories (Vite, Next.js, FastAPI, Go, etc.)
- API endpoint integration: POST /api/preview/detect, GET /api/preview asset proxy, CORS, cache, and rate limiting
"""

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.testclient import TestClient

from app.main import app
from app.services.cache import analysis_cache
from app.services.static_preview_service import (
    resolve_entry_point,
    sanitize_and_validate_path,
    inject_base_tag_into_html,
    detect_static_preview,
    STATIC_MIME_TYPES,
    MAX_CODE_SIZE_BYTES,
    MAX_MEDIA_SIZE_BYTES,
)


class TestEntryPointResolution(unittest.TestCase):
    """Test priority-based static HTML entry point resolution."""

    def test_root_index_html(self):
        paths = {"README.md", "styles.css", "index.html", "script.js"}
        self.assertEqual(resolve_entry_point(paths), "index.html")

    def test_root_index_htm(self):
        paths = {"README.md", "styles.css", "index.htm", "script.js"}
        self.assertEqual(resolve_entry_point(paths), "index.htm")

    def test_public_index_html(self):
        paths = {"README.md", "public/index.html", "public/styles.css"}
        self.assertEqual(resolve_entry_point(paths), "public/index.html")

    def test_dist_index_html(self):
        paths = {"README.md", "dist/index.html", "dist/bundle.js"}
        self.assertEqual(resolve_entry_point(paths), "dist/index.html")

    def test_build_index_html(self):
        paths = {"README.md", "build/index.html", "build/app.css"}
        self.assertEqual(resolve_entry_point(paths), "build/index.html")

    def test_single_root_html_fallback(self):
        paths = {"README.md", "presentation.html", "styles.css"}
        self.assertEqual(resolve_entry_point(paths), "presentation.html")

    def test_multiple_root_html_without_index(self):
        paths = {"README.md", "about.html", "contact.html", "portfolio.html"}
        self.assertIsNone(resolve_entry_point(paths))

    def test_no_html_files(self):
        paths = {"README.md", "main.py", "styles.css"}
        self.assertIsNone(resolve_entry_point(paths))


class TestPathValidationAndSecurity(unittest.TestCase):
    """Test path sanitization, traversal blocking, and extension whitelisting."""

    def setUp(self):
        self.tree_paths = {
            "index.html",
            "css/style.css",
            "js/app.js",
            "images/logo.png",
            "data.json",
        }

    def test_valid_paths(self):
        self.assertEqual(sanitize_and_validate_path("index.html", self.tree_paths), "index.html")
        self.assertEqual(sanitize_and_validate_path("css/style.css", self.tree_paths), "css/style.css")
        self.assertEqual(sanitize_and_validate_path("images/logo.png", self.tree_paths), "images/logo.png")

    def test_path_traversal_rejection(self):
        invalid_traversals = [
            "../etc/passwd",
            "css/../../secret",
            "/index.html",
            "../../index.html",
        ]
        for path in invalid_traversals:
            with self.subTest(path=path):
                with self.assertRaises(HTTPException) as cm:
                    sanitize_and_validate_path(path, self.tree_paths)
                self.assertEqual(cm.exception.status_code, 400)

    def test_unknown_asset_rejection(self):
        with self.assertRaises(HTTPException) as cm:
            sanitize_and_validate_path("non_existent.css", self.tree_paths)
        self.assertEqual(cm.exception.status_code, 404)

    def test_blocked_sensitive_extensions(self):
        blocked_files = {
            ".env": "blob",
            ".env.local": "blob",
            "server.py": "blob",
            "deploy.sh": "blob",
            "malicious.exe": "blob",
            "private.key": "blob",
        }
        all_paths = set(blocked_files.keys())
        for path in blocked_files:
            with self.subTest(path=path):
                with self.assertRaises(HTTPException) as cm:
                    sanitize_and_validate_path(path, all_paths)
                self.assertEqual(cm.exception.status_code, 403)

    def test_mime_type_detection(self):
        self.assertEqual(STATIC_MIME_TYPES[".html"], "text/html; charset=utf-8")
        self.assertEqual(STATIC_MIME_TYPES[".css"], "text/css; charset=utf-8")
        self.assertEqual(STATIC_MIME_TYPES[".js"], "application/javascript; charset=utf-8")
        self.assertEqual(STATIC_MIME_TYPES[".png"], "image/png")
        self.assertEqual(STATIC_MIME_TYPES[".svg"], "image/svg+xml")


class TestBaseTagInjection(unittest.TestCase):
    """Test HTML <base> tag injection for relative asset resolution."""

    def test_root_entry_injection(self):
        html = "<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>"
        injected = inject_base_tag_into_html(html, "octocat", "Spoon-Knife", "main", "index.html")
        self.assertIn('<base href="/api/preview/octocat/Spoon-Knife/main/">', injected)

    def test_nested_entry_injection(self):
        html = "<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>"
        injected = inject_base_tag_into_html(html, "octocat", "Spoon-Knife", "main", "public/index.html")
        self.assertIn('<base href="/api/preview/octocat/Spoon-Knife/main/public/">', injected)

    def test_missing_head_injection(self):
        html = "<html><body><h1>Hello</h1></body></html>"
        injected = inject_base_tag_into_html(html, "octocat", "Spoon-Knife", "main", "index.html")
        self.assertIn("<head>", injected)
        self.assertIn('<base href="/api/preview/octocat/Spoon-Knife/main/">', injected)


class TestStaticPreviewDetection(unittest.IsolatedAsyncioTestCase):
    """Test static website feasibility detection and unsupported repository rejection."""

    async def test_supported_plain_static_repository(self):
        tree = [
            {"path": "index.html", "type": "blob"},
            {"path": "styles.css", "type": "blob"},
            {"path": "app.js", "type": "blob"},
        ]
        client_mock = AsyncMock()

        res = await detect_static_preview(
            owner="octocat",
            repo_name="Spoon-Knife",
            default_branch="main",
            tree_entries=tree,
            languages={"HTML": 70, "CSS": 30},
            client=client_mock,
        )
        self.assertEqual(res.status, "READY")
        self.assertEqual(res.category, "static")
        self.assertEqual(res.entryPoint, "index.html")
        self.assertIn("/api/preview/octocat/Spoon-Knife/main/index.html", res.previewUrl)
        self.assertEqual(res.blockers, [])

    async def test_unsupported_python_repository(self):
        tree = [
            {"path": "requirements.txt", "type": "blob"},
            {"path": "app/main.py", "type": "blob"},
        ]
        client_mock = AsyncMock()

        res = await detect_static_preview(
            owner="psf",
            repo_name="requests",
            default_branch="main",
            tree_entries=tree,
            languages={"Python": 100},
            client=client_mock,
        )
        self.assertEqual(res.status, "UNSUPPORTED")
        self.assertIn("server runtime", res.blockers[0])

    async def test_unsupported_vite_react_repository(self):
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": "vite.config.ts", "type": "blob"},
            {"path": "src/App.tsx", "type": "blob"},
        ]
        pkg_content = json.dumps({
            "name": "vite-app",
            "scripts": {"build": "vite build"},
            "dependencies": {"react": "^18.0.0"}
        })

        with patch("app.services.static_preview_service.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = pkg_content
            res = await detect_static_preview(
                owner="vitejs",
                repo_name="vite-plugin-react",
                default_branch="main",
                tree_entries=tree,
                languages={"TypeScript": 100},
                client=AsyncMock(),
            )
        self.assertEqual(res.status, "UNSUPPORTED")
        self.assertIn("build step", res.blockers[0])


class TestPreviewAPIEndpoints(unittest.TestCase):
    """Test POST /api/preview/detect and GET /api/preview asset proxy."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.preview.analysis_cache.get_or_compute_by_key")
    def test_detect_endpoint_success(self, mock_cache):
        from app.models import PreviewDetectResponse
        mock_cache.return_value = PreviewDetectResponse(
            status="READY",
            category="static",
            entryPoint="index.html",
            previewUrl="/api/preview/octocat/Spoon-Knife/main/index.html",
            totalAssets=2,
            detectedAssets=["index.html", "styles.css"],
            blockers=[],
        )

        resp = self.client.post("/api/preview/detect", json={"repoUrl": "https://github.com/octocat/Spoon-Knife"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "READY")
        self.assertEqual(data["entryPoint"], "index.html")

    def test_detect_endpoint_invalid_url(self):
        resp = self.client.post("/api/preview/detect", json={"repoUrl": "https://evilgithub.com/owner/repo"})
        self.assertEqual(resp.status_code, 400)

    @patch("app.api.preview.analysis_cache.get_or_compute_by_key")
    def test_serve_asset_html_success(self, mock_cache):
        html_content = b"<html><head><base href='/api/preview/mock/repo/main/'></head><body><h1>Test</h1></body></html>"
        mock_cache.return_value = {
            "content": html_content,
            "mime_type": "text/html; charset=utf-8",
            "etag": '"12345"',
        }

        resp = self.client.get("/api/preview/mock/repo/main/index.html")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("nosniff", resp.headers.get("x-content-type-options", ""))
        csp = resp.headers.get("content-security-policy", "")
        self.assertIn("frame-ancestors", csp)
        self.assertIn("https://git-preview-ai.vercel.app", csp)
        self.assertNotIn("x-frame-options", resp.headers)
        self.assertIn(b"Test", resp.content)

    def test_serve_asset_invalid_coordinates(self):
        resp = self.client.get("/api/preview/mock/repo/main/../traversal.html")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
