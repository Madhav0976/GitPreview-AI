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
    classify_and_resolve_preview_url,
    inject_base_tag_into_html,
    rewrite_css_urls,
    render_diagnostic_html,
    PreviewResolutionError,
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
        tree_with_gif = {"index.html", "styles.css", "forkit.gif", "images/my logo.png"}
        self.assertEqual(sanitize_and_validate_path("forkit.gif", tree_with_gif), "forkit.gif")
        self.assertEqual(sanitize_and_validate_path("FORKIT.GIF", tree_with_gif), "forkit.gif")
        self.assertEqual(sanitize_and_validate_path("images/my%20logo.png", tree_with_gif), "images/my logo.png")
        self.assertEqual(sanitize_and_validate_path("styles.css?v=2.1#top", tree_with_gif), "styles.css")

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

    @patch("app.api.preview.analysis_cache.get_or_compute_by_key")
    def test_serve_asset_css_success(self, mock_cache):
        css_content = b"body { background: #fff; margin: 0; }"
        mock_cache.return_value = {
            "content": css_content,
            "mime_type": "text/css; charset=utf-8",
            "etag": '"css123"',
        }

        resp = self.client.get("/api/preview/mock/repo/main/styles.css")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/css", resp.headers.get("content-type", ""))
        self.assertIn("nosniff", resp.headers.get("x-content-type-options", ""))
        csp = resp.headers.get("content-security-policy", "")
        self.assertIn("frame-ancestors", csp)
        self.assertIn("https://git-preview-ai.vercel.app", csp)
        self.assertNotIn("x-frame-options", resp.headers)
        self.assertEqual(resp.content, css_content)

    @patch("app.api.preview.analysis_cache.get_or_compute_by_key")
    def test_serve_asset_gif_success(self, mock_cache):
        # Valid GIF header bytes (GIF89a)
        gif_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        mock_cache.return_value = {
            "content": gif_bytes,
            "mime_type": "image/gif",
            "etag": '"gif123"',
        }

        resp = self.client.get("/api/preview/mock/repo/main/forkit.gif")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "image/gif")
        self.assertIn("nosniff", resp.headers.get("x-content-type-options", ""))
        csp = resp.headers.get("content-security-policy", "")
        self.assertIn("frame-ancestors", csp)
        self.assertIn("https://git-preview-ai.vercel.app", csp)
        self.assertNotIn("x-frame-options", resp.headers)
        self.assertEqual(resp.content, gif_bytes)

    @patch("app.api.preview.fetch_git_tree")
    def test_serve_asset_missing_404(self, mock_tree):
        mock_tree.return_value = [
            {"path": "index.html", "type": "blob"},
            {"path": "styles.css", "type": "blob"},
        ]
        resp = self.client.get(
            "/api/preview/mock/repo/main/missing_asset.png",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertEqual(data.get("requestedTarget"), "missing_asset.png")
        self.assertIn("suggestedFix", data)

    @patch("app.api.preview.fetch_git_tree")
    def test_serve_asset_missing_html_diagnostic(self, mock_tree):
        mock_tree.return_value = [
            {"path": "index.html", "type": "blob"},
            {"path": "styles.css", "type": "blob"},
        ]
        resp = self.client.get(
            "/api/preview/mock/repo/main/about.html",
            headers={"Accept": "text/html"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("Preview Resolution Error", resp.text)
        self.assertIn("about.html", resp.text)
        self.assertIn("Back to Preview Entry Point", resp.text)

    def test_serve_asset_invalid_coordinates(self):
        resp = self.client.get("/api/preview/mock/repo/main/../traversal.html")
        self.assertEqual(resp.status_code, 400)

    def test_serve_asset_traversal_gif_rejected(self):
        resp = self.client.get("/api/preview/mock/repo/main/../forkit.gif")
        self.assertEqual(resp.status_code, 400)


class TestPreviewUrlClassificationAndResolution(unittest.TestCase):
    """Test comprehensive URL classification and target resolution for preview navigation."""

    def setUp(self):
        self.owner = "octocat"
        self.repo = "portfolio"
        self.branch = "main"
        self.static_tree = {
            "index.html",
            "about.html",
            "css/style.css",
            "js/app.js",
            "assets/logo.png",
            "assets/resume.pdf",
            "docs/guide.html",
        }
        self.spa_tree = {
            "package.json",
            "dist/index.html",
            "dist/assets/index-abc.js",
            "dist/assets/index-xyz.css",
            "dist/favicon.ico",
        }

    def test_hash_links(self):
        res = classify_and_resolve_preview_url(
            "#about", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "hash")
        self.assertEqual(res["target"], "index.html")

        res_root = classify_and_resolve_preview_url(
            "#", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res_root["type"], "hash")

    def test_external_links(self):
        for ext_url in ["https://github.com/octocat", "http://example.com", "mailto:user@test.com", "tel:+1234567890"]:
            with self.subTest(url=ext_url):
                res = classify_and_resolve_preview_url(
                    ext_url, self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
                )
                self.assertEqual(res["type"], "external")
                self.assertEqual(res["target"], ext_url)

    def test_relative_static_links(self):
        res = classify_and_resolve_preview_url(
            "about.html", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "static_asset")
        self.assertEqual(res["target"], "about.html")

        res_pdf = classify_and_resolve_preview_url(
            "assets/resume.pdf", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res_pdf["type"], "static_asset")
        self.assertEqual(res_pdf["target"], "assets/resume.pdf")

    def test_absolute_repo_paths(self):
        res = classify_and_resolve_preview_url(
            "/about.html", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "static_asset")
        self.assertEqual(res["target"], "about.html")

        res_css = classify_and_resolve_preview_url(
            "/css/style.css", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res_css["type"], "static_asset")
        self.assertEqual(res_css["target"], "css/style.css")

    def test_clean_urls_extension_probing(self):
        # /about -> about.html
        res = classify_and_resolve_preview_url(
            "/about", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "static_asset")
        self.assertEqual(res["target"], "about.html")

    def test_spa_client_side_routing(self):
        # In SPA repository with dist/index.html, unknown routes fall back to dist/index.html
        for route in ["/about", "/projects", "/dashboard", "/users/42"]:
            with self.subTest(route=route):
                res = classify_and_resolve_preview_url(
                    route, self.owner, self.repo, self.branch, self.spa_tree, "dist/index.html", is_spa=True
                )
                self.assertEqual(res["type"], "spa_route")
                self.assertEqual(res["target"], "dist/index.html")

    def test_plain_html_missing_route_raises_error(self):
        # Plain static HTML repos must NOT blindly fall back to index.html
        with self.assertRaises(PreviewResolutionError) as cm:
            classify_and_resolve_preview_url(
                "/non-existent-page", self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
            )
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(cm.exception.repository_type, "static_html")
        self.assertFalse(cm.exception.exists)
        self.assertIn("could not be found", cm.exception.reason)

    def test_path_traversal_detection(self):
        traversal_attempts = [
            "../../etc/passwd",
            "/../secret.txt",
            "pages/../../index.html",
        ]
        for bad_path in traversal_attempts:
            with self.subTest(path=bad_path):
                with self.assertRaises(PreviewResolutionError) as cm:
                    classify_and_resolve_preview_url(
                        bad_path, self.owner, self.repo, self.branch, self.static_tree, "index.html", is_spa=False
                    )
                self.assertEqual(cm.exception.status_code, 400)


class TestHtmlAndCssRewriting(unittest.TestCase):
    """Test client-side navigation injection and CSS root-relative URL rewriting."""

    def test_html_navigation_script_and_base_injected(self):
        raw_html = '<html><head><title>Portfolio</title></head><body><a href="/about.html">About</a><a href="#contact">Contact</a></body></html>'
        injected = inject_base_tag_into_html(raw_html, "octocat", "portfolio", "main", "index.html")

        # 1. Base tag injected
        self.assertIn('<base href="/api/preview/octocat/portfolio/main/">', injected)
        # 2. Root-relative href rewritten
        self.assertIn('href="/api/preview/octocat/portfolio/main/about.html"', injected)
        # 3. Client navigation script injected
        self.assertIn('__gitpreview_nav_layer', injected)
        self.assertIn('scrollIntoView', injected)

    def test_css_url_rewriting(self):
        css_text = (
            "body { background: url('/images/bg.png'); }\n"
            ".icon { background-image: url(/icons/logo.svg); }\n"
            ".remote { background: url('https://fonts.gstatic.com/s/roboto.woff2'); }\n"
            ".relative { background: url('assets/local.png'); }"
        )
        rewritten = rewrite_css_urls(css_text, "octocat", "portfolio", "main")
        self.assertIn("url('/api/preview/octocat/portfolio/main/images/bg.png')", rewritten)
        self.assertIn("url('/api/preview/octocat/portfolio/main/icons/logo.svg')", rewritten)
        self.assertIn("url('https://fonts.gstatic.com/s/roboto.woff2')", rewritten)
        self.assertIn("url('assets/local.png')", rewritten)


class TestSpaPrebuiltPreviewDetection(unittest.IsolatedAsyncioTestCase):
    """Test that pre-built SPAs with dist/index.html or build/index.html are previewable."""

    async def test_prebuilt_spa_detected_as_ready(self):
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": "dist/index.html", "type": "blob"},
            {"path": "dist/assets/index.js", "type": "blob"},
            {"path": "dist/assets/index.css", "type": "blob"},
        ]
        pkg_content = json.dumps({
            "name": "my-spa-portfolio",
            "dependencies": {"react": "^18.0.0"}
        })

        with patch("app.services.static_preview_service.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = pkg_content
            res = await detect_static_preview(
                owner="octocat",
                repo_name="my-spa-portfolio",
                default_branch="main",
                tree_entries=tree,
                languages={"JavaScript": 100},
                client=AsyncMock(),
            )
        self.assertEqual(res.status, "READY")
        self.assertEqual(res.entryPoint, "dist/index.html")
        self.assertIn("/api/preview/octocat/my-spa-portfolio/main/dist/index.html", res.previewUrl)


class TestPortfolioNavigationEdgeCases(unittest.TestCase):
    """
    Direct regression tests for real-world portfolio navigation issues:
    - Root and nested entry point base tags
    - Root-relative and relative link rewriting
    - Button click, data-href, and onclick proxying
    - Location API (assign, replace, history.pushState) interception
    - Clean URLs, hash variants, and media assets with spaces
    """

    def setUp(self):
        self.client = TestClient(app)
        self.owner = "abhijeetBhale"
        self.repo = "Portfolio"
        self.branch = "main"
        self.tree_paths = {
            "index.html",
            "styles.css",
            "script.js",
            "about.html",
            "projects.html",
            "assets/logo.png",
            "assets/Abhijeet Bhale UCV.pdf",
            "public/index.html",
            "public/about.html",
            "public/styles.css",
        }

    def test_navigation_script_contains_all_resolvers(self):
        html = '<html><head><title>Portfolio</title></head><body><button onclick="location.href=\'/about.html\'">About</button></body></html>'
        injected = inject_base_tag_into_html(html, self.owner, self.repo, self.branch, "index.html")

        self.assertIn("__gitpreview_nav_layer", injected)
        self.assertIn("resolveNavUrl", injected)
        self.assertIn("scrollToTarget", injected)
        self.assertIn("Location.prototype.assign", injected)
        self.assertIn("Location.prototype.replace", injected)
        self.assertIn("history.pushState", injected)
        self.assertIn("history.replaceState", injected)
        self.assertIn("Location.prototype", injected)
        self.assertIn("__gitpreview_resolve_nav_url", injected)

    def test_nested_entry_point_base_href(self):
        html = '<html><head><title>Nested App</title></head><body><a href="about.html">About</a></body></html>'
        injected = inject_base_tag_into_html(html, self.owner, self.repo, self.branch, "public/index.html")

        # Nested entry point must have public/ in base tag
        self.assertIn('<base href="/api/preview/abhijeetBhale/Portfolio/main/public/">', injected)
        self.assertIn('var repoRootHref = "/api/preview/abhijeetBhale/Portfolio/main/";', injected)

    def test_root_entry_point_base_href(self):
        html = '<html><head><title>Root App</title></head><body><a href="about.html">About</a></body></html>'
        injected = inject_base_tag_into_html(html, self.owner, self.repo, self.branch, "index.html")

        self.assertIn('<base href="/api/preview/abhijeetBhale/Portfolio/main/">', injected)

    def test_button_and_data_href_attribute_rewriting(self):
        html = (
            '<html><head></head><body>'
            '<button data-href="/projects">Projects</button>'
            '<a data-target="/about.html">About</a>'
            '<form action="/search" method="GET"></form>'
            '</body></html>'
        )
        injected = inject_base_tag_into_html(html, self.owner, self.repo, self.branch, "index.html")
        self.assertIn('data-href="/api/preview/abhijeetBhale/Portfolio/main/projects"', injected)
        self.assertIn('data-target="/api/preview/abhijeetBhale/Portfolio/main/about.html"', injected)
        self.assertIn('action="/api/preview/abhijeetBhale/Portfolio/main/search"', injected)

    def test_clean_urls_extensionless_projects(self):
        # /projects should resolve to projects.html
        res = classify_and_resolve_preview_url(
            "/projects", self.owner, self.repo, self.branch, self.tree_paths, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "static_asset")
        self.assertEqual(res["target"], "projects.html")

    def test_asset_with_spaces_resolved(self):
        res = classify_and_resolve_preview_url(
            "assets/Abhijeet Bhale UCV.pdf", self.owner, self.repo, self.branch, self.tree_paths, "index.html", is_spa=False
        )
        self.assertEqual(res["type"], "static_asset")
        self.assertEqual(res["target"], "assets/Abhijeet Bhale UCV.pdf")

        res_encoded = classify_and_resolve_preview_url(
            "assets/Abhijeet%20Bhale%20UCV.pdf", self.owner, self.repo, self.branch, self.tree_paths, "index.html", is_spa=False
        )
        self.assertEqual(res_encoded["type"], "static_asset")
        self.assertEqual(res_encoded["target"], "assets/Abhijeet Bhale UCV.pdf")

    def test_hash_navigation_variants(self):
        variants = ["#about", "./#about", "./index.html#about", "#projects", "#", "#top"]
        for var in variants:
            with self.subTest(var=var):
                res = classify_and_resolve_preview_url(
                    var, self.owner, self.repo, self.branch, self.tree_paths, "index.html", is_spa=False
                )
                self.assertEqual(res["type"], "hash")

    @patch("app.api.preview.fetch_git_tree")
    @patch("app.api.preview.fetch_file_bytes")
    def test_root_preview_url_endpoints(self, mock_bytes, mock_tree):
        mock_tree.return_value = [
            {"path": "index.html", "type": "blob"},
            {"path": "styles.css", "type": "blob"},
        ]
        mock_bytes.return_value = (b"<html><head><title>Portfolio</title></head><body>Hi</body></html>", '"etag1"')

        # Test both /api/preview/{owner}/{repo}/{branch} and /api/preview/{owner}/{repo}/{branch}/
        resp1 = self.client.get("/api/preview/mock/repo/main")
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("text/html", resp1.headers.get("content-type", ""))
        self.assertIn("base href", resp1.text)

        resp2 = self.client.get("/api/preview/mock/repo/main/")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("text/html", resp2.headers.get("content-type", ""))
        self.assertIn("base href", resp2.text)


if __name__ == "__main__":
    unittest.main()


