"""
Automated Production Readiness Test Suite
Tests:
- URL validation (parse_repo_url) with positive and negative attack vectors
- Rate limiting (slowapi) with 429 checks, CORS, and OPTIONS preflight
- Response cache (in-memory TTL, key normalization, error avoidance, TTL expiration, request coalescing)
- GitHub rate limit observability (header parsing, warning trigger, safe health endpoint)
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.main import app
from app.models import AnalysisResponse, RepositoryMetadata, FolderAnalysis
from app.services.cache import AnalysisCache, analysis_cache
from app.services.github_client import (
    parse_repo_url,
    rate_limit_tracker,
    RateLimitTracker,
)


class TestStrictURLValidation(unittest.TestCase):
    """Test strict GitHub repository URL validation."""

    def test_valid_urls(self):
        valid_cases = [
            ("https://github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo/", ("owner", "repo")),
            ("https://www.github.com/owner/repo", ("owner", "repo")),
            ("http://github.com/owner/repo", ("owner", "repo")),
            ("git@github.com:owner/repo.git", ("owner", "repo")),
            ("git@github.com:owner/repo", ("owner", "repo")),
            ("github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/Madhav0976/GitPreview-AI", ("Madhav0976", "GitPreview-AI")),
            ("https://github.com/vitejs/vite-plugin-react", ("vitejs", "vite-plugin-react")),
            ("https://github.com/shadcn-ui/taxonomy", ("shadcn-ui", "taxonomy")),
            ("https://github.com/octocat/Spoon-Knife", ("octocat", "Spoon-Knife")),
            ("https://github.com/psf/requests", ("psf", "requests")),
        ]
        for url, expected in valid_cases:
            with self.subTest(url=url):
                owner, repo = parse_repo_url(url)
                self.assertEqual((owner, repo), expected)

    def test_invalid_hosts(self):
        invalid_hosts = [
            "https://evilgithub.com/owner/repo",
            "https://github.com.evil.com/owner/repo",
            "https://google.com/owner/repo",
            "https://gitlab.com/owner/repo",
            "https://notgithub.com/owner/repo",
        ]
        for url in invalid_hosts:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_repo_url(url)

    def test_invalid_paths(self):
        invalid_paths = [
            "https://github.com/owner/repo/pull/1",
            "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/repo/blob/main/README.md",
            "https://github.com/owner",
            "https://github.com//repo",
            "https://github.com/owner/",
            "git@github.com:owner",
            "git@github.com:owner/repo/extra",
        ]
        for url in invalid_paths:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_repo_url(url)

    def test_traversal_and_malformed(self):
        malicious_inputs = [
            "https://github.com/../../etc",
            "https://github.com/owner/..",
            "https://github.com/..%2f../repo",
            "https://github.com/owner/%2e%2e/repo",
            "https://github.com/owner/repo$bad",
            "https://github.com/-owner-/repo",
            "https://github.com/owner/repo!name",
            "",
            "   ",
        ]
        for url in malicious_inputs:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_repo_url(url)


class TestResponseCache(unittest.IsolatedAsyncioTestCase):
    """Test in-memory TTL response cache functionality."""

    def setUp(self):
        self.dummy_metadata = RepositoryMetadata(
            owner="testowner",
            name="testrepo",
            description="A test repo",
            stars=42,
            forks=7,
            license="MIT",
            defaultBranch="main",
            languages={"Python": 100},
            technologies=["Python", "FastAPI"],
            projectType="Backend API",
            summary="Test summary.",
        )
        self.dummy_folder = FolderAnalysis(
            folderSummary=["backend"],
            entryPoints=["backend/main.py"],
            importantFiles=["README.md"],
            totalFiles=10,
        )
        self.dummy_response = AnalysisResponse(
            metadata=self.dummy_metadata,
            folderAnalysis=self.dummy_folder,
        )

    async def test_cache_hit_and_miss(self):
        cache = AnalysisCache(ttl_seconds=100)
        compute_mock = AsyncMock(return_value=self.dummy_response)

        # 1. First call: miss, calls compute
        res1 = await cache.get_or_compute("TestOwner", "TestRepo", compute_mock)
        self.assertEqual(compute_mock.call_count, 1)
        self.assertEqual(res1.metadata.name, "testrepo")

        # 2. Second call with case difference: hit, no compute
        res2 = await cache.get_or_compute("testowner", "testrepo", compute_mock)
        self.assertEqual(compute_mock.call_count, 1)
        self.assertEqual(res2.metadata.name, "testrepo")

    async def test_different_repositories_do_not_collide(self):
        cache = AnalysisCache(ttl_seconds=100)
        compute_mock1 = AsyncMock(return_value=self.dummy_response)
        compute_mock2 = AsyncMock(return_value=self.dummy_response)

        await cache.get_or_compute("owner", "repo1", compute_mock1)
        await cache.get_or_compute("owner", "repo2", compute_mock2)

        self.assertEqual(compute_mock1.call_count, 1)
        self.assertEqual(compute_mock2.call_count, 1)
        self.assertEqual(await cache.size(), 2)

    async def test_failed_requests_are_not_cached(self):
        cache = AnalysisCache(ttl_seconds=100)
        failing_compute = AsyncMock(side_effect=RuntimeError("GitHub error"))

        with self.assertRaises(RuntimeError):
            await cache.get_or_compute("owner", "failing-repo", failing_compute)

        self.assertEqual(await cache.size(), 0)
        self.assertIsNone(await cache.get("owner", "failing-repo"))

    async def test_cache_ttl_expiration(self):
        # Set a very short TTL of 0.05 seconds
        cache = AnalysisCache(ttl_seconds=0.05)
        compute_mock = AsyncMock(return_value=self.dummy_response)

        await cache.get_or_compute("owner", "repo", compute_mock)
        self.assertEqual(compute_mock.call_count, 1)

        # Immediate check: hit
        await cache.get_or_compute("owner", "repo", compute_mock)
        self.assertEqual(compute_mock.call_count, 1)

        # Wait for expiration
        await asyncio.sleep(0.06)

        # After TTL: miss, computes again
        await cache.get_or_compute("owner", "repo", compute_mock)
        self.assertEqual(compute_mock.call_count, 2)

    async def test_request_coalescing(self):
        """Simultaneous concurrent requests for same repo should only invoke compute once."""
        cache = AnalysisCache(ttl_seconds=100)
        compute_call_count = 0

        async def slow_compute():
            nonlocal compute_call_count
            compute_call_count += 1
            await asyncio.sleep(0.05)
            return self.dummy_response

        # Launch 5 concurrent calls
        tasks = [
            cache.get_or_compute("owner", "concurrent-repo", slow_compute)
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        self.assertEqual(compute_call_count, 1)
        for r in results:
            self.assertEqual(r.metadata.name, "testrepo")


class TestGitHubRateLimitObservability(unittest.TestCase):
    """Test rate limit header tracking and health reporting."""

    def test_header_tracking_and_warning(self):
        tracker = RateLimitTracker()
        headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "450",
            "x-ratelimit-reset": "1720000000",
        }

        with self.assertLogs("app.services.github_client", level="WARNING") as cm:
            tracker.update_from_headers(headers)
            self.assertTrue(any("quota running low" in log for log in cm.output))

        status = tracker.get_status()
        self.assertEqual(status["limit"], 5000)
        self.assertEqual(status["remaining"], 450)
        self.assertEqual(status["reset_timestamp"], 1720000000)
        self.assertIsNotNone(status["last_updated"])

    def test_health_endpoint_observability(self):
        client = TestClient(app)
        # Update tracker with known values
        rate_limit_tracker.update_from_headers({
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4800",
            "x-ratelimit-reset": "1720000000",
        })

        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("github_rate_limit", data)
        self.assertEqual(data["github_rate_limit"]["limit"], 5000)
        self.assertEqual(data["github_rate_limit"]["remaining"], 4800)

        # Verify absolutely no secrets are returned
        text_content = resp.text.lower()
        self.assertNotIn("token", text_content)
        self.assertNotIn("authorization", text_content)
        self.assertNotIn("bearer", text_content)


class TestRateLimitingAndCORS(unittest.TestCase):
    """Test endpoint rate limiting, CORS headers, and preflight OPTIONS handling."""

    def setUp(self):
        self.client = TestClient(app)

    def test_options_preflight_bypasses_limiter_and_includes_cors(self):
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        }
        resp = self.client.options("/api/analyze", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("POST", resp.headers.get("access-control-allow-methods", ""))

    @patch("app.api.analyze.analysis_cache.get_or_compute")
    def test_rate_limiter_triggers_429_with_clean_json(self, mock_get_or_compute):
        mock_get_or_compute.return_value = AnalysisResponse(
            metadata=RepositoryMetadata(
                owner="mock",
                name="repo",
                description="Mock repo",
                stars=1,
                forks=0,
                license=None,
                defaultBranch="main",
                languages={},
                technologies=[],
                projectType="Library",
                summary="Mock summary",
            ),
            folderAnalysis=FolderAnalysis()
        )

        client_ip = "192.168.100.99"
        headers = {
            "X-Forwarded-For": client_ip,
            "Origin": "http://localhost:3000",
        }

        responses = []
        for _ in range(12):
            resp = self.client.post(
                "/api/analyze",
                json={"repoUrl": "https://github.com/mock/repo"},
                headers=headers,
            )
            responses.append(resp)

        # First 10 requests should succeed (200), 11th and 12th should be rate-limited (429)
        self.assertEqual(responses[0].status_code, 200)
        statuses = [r.status_code for r in responses]
        self.assertIn(429, statuses)

        last_resp = responses[-1]
        self.assertEqual(last_resp.status_code, 429)
        data = last_resp.json()
        self.assertIn("detail", data)
        self.assertIn("Rate limit exceeded", data["detail"])

        # Verify OPTIONS STILL returns 200 even after IP is rate-limited on POST
        preflight_headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "X-Forwarded-For": client_ip,
        }
        opt_resp = self.client.options("/api/analyze", headers=preflight_headers)
        self.assertEqual(opt_resp.status_code, 200)
        self.assertEqual(opt_resp.headers.get("access-control-allow-origin"), "http://localhost:3000")


class TestSharedGitHubApiCacheSingleFlight(unittest.IsolatedAsyncioTestCase):
    """Test PROD-02 shared GitHub API TTL cache and single-flight coalescing across endpoints."""

    async def asyncSetUp(self):
        from app.services.cache import github_api_cache
        await github_api_cache.clear()

    async def asyncTearDown(self):
        from app.services.cache import github_api_cache
        await github_api_cache.clear()

    async def test_shared_cache_reuses_repo_info_languages_tree_and_file_content(self):
        """Repeated/concurrent calls for the same repository hit upstream HTTP client only once."""
        from app.services.github_client import (
            fetch_repo_info,
            fetch_languages,
            fetch_git_tree,
            fetch_file_content,
            fetch_file_bytes,
        )

        call_counts = {
            "repo_info": 0,
            "languages": 0,
            "git_tree": 0,
            "file_content": 0,
        }

        class MockResponse:
            def __init__(self, status_code, json_data=None, text="", content=b"", headers=None):
                self.status_code = status_code
                self._json_data = json_data
                self.text = text
                self.content = content
                self.headers = headers or {"content-type": "application/json", "etag": '"etag1"'}

            def json(self):
                return self._json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception(f"HTTP {self.status_code}")

        async def mock_get(url: str):
            await asyncio.sleep(0.01)
            if url.endswith("/repos/octocat/spoon-knife") or url.endswith("/repos/Octocat/Spoon-Knife"):
                call_counts["repo_info"] += 1
                return MockResponse(200, {"name": "Spoon-Knife", "default_branch": "main", "stargazers_count": 10})
            if "/languages" in url:
                call_counts["languages"] += 1
                return MockResponse(200, {"HTML": 1200, "CSS": 400})
            if "/git/trees/" in url:
                call_counts["git_tree"] += 1
                return MockResponse(200, {"tree": [{"path": "index.html", "type": "blob"}]})
            if "/contents/" in url:
                call_counts["file_content"] += 1
                import base64
                b64 = base64.b64encode(b"<h1>Hello</h1>").decode("ascii")
                return MockResponse(200, {"content": b64, "encoding": "base64"}, content=b"<h1>Hello</h1>")
            return MockResponse(404)

        client = AsyncMock()
        client.get.side_effect = mock_get

        # Launch concurrent requests simulating /api/analyze, /api/run-analysis, and /api/preview/detect
        info_results = await asyncio.gather(
            fetch_repo_info("Octocat", "Spoon-Knife", client),
            fetch_repo_info("octocat", "spoon-knife", client),
            fetch_repo_info("OCTOCAT", "SPOON-KNIFE", client),
        )
        lang_results = await asyncio.gather(
            fetch_languages("Octocat", "Spoon-Knife", client),
            fetch_languages("octocat", "spoon-knife", client),
        )
        tree_results = await asyncio.gather(
            fetch_git_tree("Octocat", "Spoon-Knife", "main", client),
            fetch_git_tree("octocat", "spoon-knife", "main", client),
        )
        file_results = await asyncio.gather(
            fetch_file_content("Octocat", "Spoon-Knife", "index.html", client, default_branch="main"),
            fetch_file_content("octocat", "spoon-knife", "/index.html", client, default_branch="main"),
        )
        byte_results = await asyncio.gather(
            fetch_file_bytes("Octocat", "Spoon-Knife", "index.html", client, default_branch="main"),
            fetch_file_bytes("octocat", "spoon-knife", "index.html", client, default_branch="main"),
        )

        self.assertEqual(call_counts["repo_info"], 1)
        self.assertEqual(call_counts["languages"], 1)
        self.assertEqual(call_counts["git_tree"], 1)
        # 1 call for fetch_file_content + 1 call for fetch_file_bytes
        self.assertEqual(call_counts["file_content"], 2)

        self.assertEqual(info_results[0]["name"], "Spoon-Knife")
        self.assertEqual(lang_results[0]["HTML"], 1200)
        self.assertEqual(len(tree_results[0]), 1)
        self.assertEqual(file_results[0], "<h1>Hello</h1>")
        self.assertEqual(byte_results[0][0], b"<h1>Hello</h1>")

        # Verify mutating returned dict/list does not corrupt cached payload
        info_results[0]["name"] = "MUTATED"
        fresh_info = await fetch_repo_info("octocat", "spoon-knife", client)
        self.assertEqual(fresh_info["name"], "Spoon-Knife")

    async def test_different_repos_branches_and_files_never_collide(self):
        """Ensure different repositories, branches, and case-sensitive file paths do not collide."""
        from app.services.github_client import fetch_git_tree, fetch_file_content

        class MockResponse:
            def __init__(self, status_code, json_data=None, text="", headers=None):
                self.status_code = status_code
                self._json_data = json_data
                self.text = text
                self.headers = headers or {"content-type": "text/plain"}

            def json(self):
                return self._json_data

        async def mock_get(url: str):
            if "/git/trees/main" in url:
                return MockResponse(200, {"tree": [{"path": "main_only.html", "type": "blob"}]}, headers={"content-type": "application/json"})
            if "/git/trees/dev" in url:
                return MockResponse(200, {"tree": [{"path": "dev_only.html", "type": "blob"}]}, headers={"content-type": "application/json"})
            return MockResponse(200, text=f"URL={url}")

        client = AsyncMock()
        client.get.side_effect = mock_get

        tree_main = await fetch_git_tree("owner", "repo1", "main", client)
        tree_dev = await fetch_git_tree("owner", "repo1", "dev", client)
        self.assertEqual(tree_main[0]["path"], "main_only.html")
        self.assertEqual(tree_dev[0]["path"], "dev_only.html")

        f_upper = await fetch_file_content("owner", "repo1", "README.md", client, default_branch="main")
        f_lower = await fetch_file_content("owner", "repo1", "readme.md", client, default_branch="main")
        f_dev = await fetch_file_content("owner", "repo1", "README.md", client, default_branch="dev")
        f_repo2 = await fetch_file_content("owner", "repo2", "README.md", client, default_branch="main")

        self.assertNotEqual(f_upper, f_lower)
        self.assertNotEqual(f_upper, f_dev)
        self.assertNotEqual(f_upper, f_repo2)

    async def test_transient_failures_are_never_cached_as_success(self):
        """Verify that transient 500/network failures return fallback values without being cached."""
        from app.services.github_client import fetch_languages, fetch_git_tree, fetch_file_content

        class MockResponse:
            def __init__(self, status_code, json_data=None, text="", headers=None):
                self.status_code = status_code
                self._json_data = json_data
                self.text = text
                self.headers = headers or {"content-type": "application/json"}

            def json(self):
                return self._json_data

        attempt = {"count": 0}

        async def flaky_get(url: str):
            attempt["count"] += 1
            if attempt["count"] == 1:
                return MockResponse(500)
            return MockResponse(200, {"Python": 5000})

        client = AsyncMock()
        client.get.side_effect = flaky_get

        # 1st call fails with HTTP 500 -> returns graceful {} fallback
        res1 = await fetch_languages("owner", "flaky-repo", client)
        self.assertEqual(res1, {})

        # 2nd call must NOT serve cached {}, it must retry upstream and succeed
        res2 = await fetch_languages("owner", "flaky-repo", client)
        self.assertEqual(res2, {"Python": 5000})
        self.assertEqual(attempt["count"], 2)


class TestStep3UxAndMultiEndpointIntegration(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 2.1 Step 3 (UX-01, UX-02, UX-03) contracts and multi-endpoint single-flight reuse."""

    async def asyncSetUp(self):
        from app.services.cache import github_api_cache, analysis_cache
        from app.api.run_analysis import run_analysis_cache
        await github_api_cache.clear()
        await analysis_cache.clear()
        await run_analysis_cache.clear()

    def test_frontend_step3_contracts_ux01_ux02_ux03(self):
        """Verify frontend source contracts for UX-01 (/api/run-analysis), UX-02 (EXAMPLE_REPOS auto-analyze), and UX-03 (stale Dashboard hidden)."""
        import os

        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
        api_ts_path = os.path.join(frontend_dir, "lib", "api.ts")
        types_ts_path = os.path.join(frontend_dir, "lib", "types.ts")
        dashboard_path = os.path.join(frontend_dir, "app", "components", "Dashboard.tsx")
        form_path = os.path.join(frontend_dir, "app", "components", "RepoInputForm.tsx")

        with open(api_ts_path, "r", encoding="utf-8") as f:
            api_ts = f.read()
        with open(types_ts_path, "r", encoding="utf-8") as f:
            types_ts = f.read()
        with open(dashboard_path, "r", encoding="utf-8") as f:
            dashboard_tsx = f.read()
        with open(form_path, "r", encoding="utf-8") as f:
            form_tsx = f.read()

        # UX-01: fetchRunAnalysis uses getApiBase() and /run-analysis with AbortSignal
        self.assertIn("export async function fetchRunAnalysis", api_ts)
        self.assertIn("${getApiBase()}/run-analysis", api_ts)
        self.assertIn("export interface RunAnalysisResult", types_ts)
        self.assertIn("export interface RunAnalysisResponse", types_ts)
        self.assertIn("fetchRunAnalysis({ repoUrl: targetUrl }, controller.signal)", dashboard_tsx)
        self.assertIn("Run &amp; Execution Analysis", dashboard_tsx)
        self.assertIn("Secret values are never accessed or exposed", dashboard_tsx)

        # UX-02: EXAMPLE_REPOS includes shahriar-tasnim.github.io and handleExampleClick triggers analysis immediately
        self.assertIn("https://github.com/shahriar-tasnim/shahriar-tasnim.github.io", form_tsx)
        self.assertIn("void runRepositoryAnalysis(url)", form_tsx)

        # UX-03: LoadingSkeleton rendered while loading, and Dashboard hidden during loading / cleared on error
        self.assertIn("setResult(null)", form_tsx)
        self.assertIn("setAnalyzedRepoUrl('')", form_tsx)
        self.assertIn("{!loading && result ?", form_tsx)

    async def test_full_dashboard_workflow_analyze_run_analysis_and_preview_detect_reuse_cache(self):
        """Simulate the complete frontend Dashboard flow (/api/analyze + /api/run-analysis + /api/preview/detect) for shahriar-tasnim.github.io."""
        from app.api.analyze import analyze
        from app.api.run_analysis import run_analysis
        from app.api.preview import detect_preview
        from app.models import AnalyzeRequest, PreviewDetectRequest
        from starlette.requests import Request

        repo_url = "https://github.com/shahriar-tasnim/shahriar-tasnim.github.io"
        upstream_calls = {"repo_info": 0, "languages": 0, "git_tree": 0}

        class MockResponse:
            def __init__(self, status_code, json_data=None, text="", headers=None):
                self.status_code = status_code
                self._json_data = json_data
                self.text = text
                self.headers = headers or {"content-type": "application/json"}

            def json(self):
                return self._json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception(f"HTTP {self.status_code}")

        async def mock_get(self_client, url: str, *args, **kwargs):
            if url.endswith("/repos/shahriar-tasnim/shahriar-tasnim.github.io"):
                upstream_calls["repo_info"] += 1
                return MockResponse(200, {
                    "name": "shahriar-tasnim.github.io",
                    "default_branch": "main",
                    "description": "Portfolio site",
                    "stargazers_count": 5,
                    "forks_count": 1,
                    "license": {"name": "MIT"},
                })
            if "/languages" in url:
                upstream_calls["languages"] += 1
                return MockResponse(200, {"HTML": 15000, "CSS": 8000, "JavaScript": 4000})
            if "/git/trees/" in url:
                upstream_calls["git_tree"] += 1
                return MockResponse(200, {
                    "tree": [
                        {"path": "index.html", "type": "blob"},
                        {"path": "styles.css", "type": "blob"},
                        {"path": "script.js", "type": "blob"},
                    ]
                })
            return MockResponse(404)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/analyze",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        dummy_req = Request(scope)

        with patch("httpx.AsyncClient.get", new=mock_get):
            analyze_res = await analyze(dummy_req, AnalyzeRequest(repoUrl=repo_url))
            run_res, preview_res = await asyncio.gather(
                run_analysis(dummy_req, AnalyzeRequest(repoUrl=repo_url)),
                detect_preview(dummy_req, PreviewDetectRequest(repoUrl=repo_url)),
            )

        self.assertEqual(analyze_res.metadata.name, "shahriar-tasnim.github.io")
        self.assertEqual(run_res.analysis.feasibility, "READY")
        self.assertEqual(preview_res.status, "READY")
        self.assertEqual(preview_res.entryPoint, "index.html")

        # Across all 3 endpoints, GitHub API was called only ONCE for repo_info, languages, and git_tree!
        self.assertEqual(upstream_calls["repo_info"], 1)
        self.assertEqual(upstream_calls["languages"], 1)
        self.assertEqual(upstream_calls["git_tree"], 1)


class TestStep4UxNormalizationModalAndCopyFeedback(unittest.TestCase):
    """Verify Phase 2.1 Step 4 (UX-04, UX-05, UX-06) contracts, URL normalization runtime behavior, and modal security."""

    def test_ux04_normalize_github_repo_url_runtime_execution(self):
        """Execute normalizeGitHubRepoUrl via Node.js against all supported and malicious URL formats."""
        import json
        import os
        import subprocess

        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
        api_ts_path = os.path.join(frontend_dir, "lib", "api.ts")
        with open(api_ts_path, "r", encoding="utf-8") as f:
            api_ts = f.read()

        # Strip TypeScript type annotations from normalizeGitHubRepoUrl to run directly in Node
        js_code = (
            api_ts.split("export function getApiBase()")[0]
            .replace("import type { AnalyzeRequest, AnalysisResponse, RunAnalysisResponse } from './types'", "")
            .replace("export function normalizeGitHubRepoUrl(rawInput: string): string | null {", "function normalizeGitHubRepoUrl(rawInput) {")
            .replace("let parsed: URL", "let parsed")
        )

        test_script = js_code + """
const positiveCases = [
  ["https://github.com/owner/repo", "https://github.com/owner/repo"],
  ["http://github.com/owner/repo", "https://github.com/owner/repo"],
  ["github.com/owner/repo", "https://github.com/owner/repo"],
  ["www.github.com/owner/repo", "https://github.com/owner/repo"],
  ["owner/repo", "https://github.com/owner/repo"],
  ["shahriar-tasnim/shahriar-tasnim.github.io", "https://github.com/shahriar-tasnim/shahriar-tasnim.github.io"],
  ["https://github.com/owner/repo/tree/main", "https://github.com/owner/repo"],
  ["https://github.com/owner/repo/tree/main/src/components", "https://github.com/owner/repo"],
  ["https://github.com/owner/repo/blob/main/README.md", "https://github.com/owner/repo"],
  ["git@github.com:owner/repo.git", "https://github.com/owner/repo"],
  ["https://github.com/owner/repo.git/", "https://github.com/owner/repo"],
];

const negativeCases = [
  "",
  "   ",
  "https://evil.com/?q=github.com",
  "https://github.com.evil.com/owner/repo",
  "https://evilgithub.com/owner/repo",
  "https://gitlab.com/owner/repo",
  "gitlab.com/owner/repo",
  "owner/..",
  "https://github.com/owner/../etc",
  "https://github.com/owner",
  "just-a-single-word",
];

for (const [input, expected] of positiveCases) {
  const actual = normalizeGitHubRepoUrl(input);
  if (actual !== expected) {
    console.error("Positive case failed:", input, "expected:", expected, "got:", actual);
    process.exit(1);
  }
}

for (const input of negativeCases) {
  const actual = normalizeGitHubRepoUrl(input);
  if (actual !== null) {
    console.error("Negative case should have returned null:", input, "got:", actual);
    process.exit(1);
  }
}
console.log("ALL_NORMALIZATION_TESTS_PASSED");
"""
        proc = subprocess.run(["node", "-e", test_script], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Node test failed: {proc.stderr}")
        self.assertIn("ALL_NORMALIZATION_TESTS_PASSED", proc.stdout)

    def test_ux05_and_ux06_modal_and_copy_feedback_contracts(self):
        """Verify UX-05 modal accessibility/scroll-lock/timeout/new-tab/sandbox and UX-06 copy feedback."""
        import os

        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
        modal_path = os.path.join(frontend_dir, "app", "components", "StaticPreviewModal.tsx")
        form_path = os.path.join(frontend_dir, "app", "components", "RepoInputForm.tsx")

        with open(modal_path, "r", encoding="utf-8") as f:
            modal_tsx = f.read()
        with open(form_path, "r", encoding="utf-8") as f:
            form_tsx = f.read()

        # UX-05: Accessibility attributes
        self.assertIn('role="dialog"', modal_tsx)
        self.assertIn('aria-modal="true"', modal_tsx)
        self.assertIn('aria-labelledby="static-preview-modal-title"', modal_tsx)
        self.assertIn('aria-label="Close preview modal"', modal_tsx)

        # UX-05: Body scroll lock and restoration
        self.assertIn("const previousOverflow = document.body.style.overflow", modal_tsx)
        self.assertIn("document.body.style.overflow = 'hidden'", modal_tsx)
        self.assertIn("document.body.style.overflow = previousOverflow", modal_tsx)

        # UX-05: Iframe loading timeout (~15s), Retry, and Open in New Tab
        self.assertIn("IFRAME_LOAD_TIMEOUT_MS = 15000", modal_tsx)
        self.assertIn("window.open(fullUrl, '_blank', 'noopener,noreferrer')", modal_tsx)
        self.assertIn("Open in New Tab", modal_tsx)
        self.assertIn("Retry", modal_tsx)

        # UX-05: Security invariant — exact sandbox preserved, no allow-same-origin or allow-top-navigation
        self.assertIn('sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"', modal_tsx)
        self.assertNotIn("allow-same-origin", modal_tsx)
        self.assertNotIn("allow-top-navigation", modal_tsx)

        # UX-06: Copy URL confirmation & unmount cleanup
        self.assertIn("✓ Copied!", form_tsx)
        self.assertIn("📋 Copy URL", form_tsx)
        self.assertIn("copyTimeoutRef", form_tsx)


if __name__ == "__main__":
    unittest.main()



