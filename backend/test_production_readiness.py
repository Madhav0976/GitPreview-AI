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


if __name__ == "__main__":
    unittest.main()
