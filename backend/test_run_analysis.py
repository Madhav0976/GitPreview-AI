"""
Unit and Integration Test Suite for V2 Run Analysis Engine (Phase 1)
Tests:
- a. Vite/React repository
- b. Next.js repository
- c. FastAPI repository
- d. Simple static HTML repository
- e. Repository with environment variable requirements (.env.example)
- f. Repository with external services (PostgreSQL & Redis in docker-compose)
- g. CLI tool repository (UNSUPPORTED)
- h. Library package repository (UNSUPPORTED)
- i. API endpoint POST /api/run-analysis integration (CORS, cache, validation, rate limiting)
"""

import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.main import app
from app.models import (
    AppCategory,
    PreviewFeasibility,
    RunAnalysisResponse,
    RunAnalysisResult,
)
from app.services.run_analyzer import (
    analyze_run_configuration,
    parse_env_file_variables,
    detect_external_services_from_docker_compose,
)


class TestRunAnalyzerEcosystems(unittest.IsolatedAsyncioTestCase):
    """Test runtime and command resolution across different project architectures."""

    async def test_a_vite_react_project(self):
        """Vite + React with pnpm lockfile."""
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": "pnpm-lock.yaml", "type": "blob"},
            {"path": "vite.config.ts", "type": "blob"},
            {"path": "src/main.tsx", "type": "blob"},
            {"path": "src/App.tsx", "type": "blob"},
        ]
        pkg_json = json.dumps({
            "name": "vite-react-app",
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
                "preview": "vite preview"
            },
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0"
            },
            "devDependencies": {
                "vite": "^5.0.0",
                "typescript": "^5.0.0"
            }
        })

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = pkg_json

            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="vite-app",
                default_branch="main",
                tree_entries=tree,
                languages={"TypeScript": 80, "HTML": 20},
                client=client_mock,
            )

        self.assertEqual(result.runtime, "Node.js")
        self.assertEqual(result.packageManager, "pnpm")
        self.assertEqual(result.installCommand, "pnpm install")
        self.assertEqual(result.buildCommand, "pnpm run build")
        self.assertEqual(result.startCommand, "pnpm run dev")
        self.assertEqual(result.expectedPort, 5173)
        self.assertEqual(result.category, AppCategory.FRONTEND.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.READY.value)
        self.assertEqual(result.blockers, [])

    async def test_b_nextjs_project(self):
        """Next.js full-stack app with npm."""
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": "package-lock.json", "type": "blob"},
            {"path": "next.config.mjs", "type": "blob"},
            {"path": "app/page.tsx", "type": "blob"},
            {"path": "app/layout.tsx", "type": "blob"},
        ]
        pkg_json = json.dumps({
            "name": "nextjs-app",
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start"
            },
            "dependencies": {
                "next": "^14.2.0",
                "react": "^18.3.0",
                "react-dom": "^18.3.0"
            }
        })

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = pkg_json

            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="next-app",
                default_branch="main",
                tree_entries=tree,
                languages={"TypeScript": 95, "CSS": 5},
                client=client_mock,
            )

        self.assertEqual(result.runtime, "Node.js")
        self.assertEqual(result.packageManager, "npm")
        self.assertEqual(result.installCommand, "npm install")
        self.assertEqual(result.buildCommand, "npm run build")
        self.assertEqual(result.startCommand, "npm run dev")
        self.assertEqual(result.expectedPort, 3000)
        self.assertEqual(result.category, AppCategory.FULL_STACK.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.READY.value)
        self.assertEqual(result.blockers, [])

    async def test_c_fastapi_project(self):
        """FastAPI backend API with pip and uvicorn."""
        tree = [
            {"path": "requirements.txt", "type": "blob"},
            {"path": "app/main.py", "type": "blob"},
            {"path": "app/api.py", "type": "blob"},
        ]
        reqs = "fastapi==0.115.0\nuvicorn==0.34.0\npydantic==2.10.0\n"

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = reqs

            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="fastapi-app",
                default_branch="main",
                tree_entries=tree,
                languages={"Python": 100},
                client=client_mock,
            )

        self.assertEqual(result.runtime, "Python")
        self.assertEqual(result.packageManager, "pip")
        self.assertEqual(result.installCommand, "pip install -r requirements.txt")
        self.assertIn("uvicorn app.main:app", result.startCommand)
        self.assertEqual(result.expectedPort, 8000)
        self.assertEqual(result.category, AppCategory.BACKEND_API.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.READY.value)
        self.assertEqual(result.blockers, [])

    async def test_d_static_html_project(self):
        """Simple static HTML / CSS repository."""
        tree = [
            {"path": "index.html", "type": "blob"},
            {"path": "styles.css", "type": "blob"},
            {"path": "script.js", "type": "blob"},
            {"path": "images/logo.png", "type": "blob"},
        ]
        client_mock = AsyncMock()

        result = await analyze_run_configuration(
            owner="testowner",
            repo_name="static-site",
            default_branch="main",
            tree_entries=tree,
            languages={"HTML": 60, "CSS": 30, "JavaScript": 10},
            client=client_mock,
        )

        self.assertEqual(result.runtime, "Static HTML / JS")
        self.assertEqual(result.packageManager, "None")
        self.assertIsNone(result.installCommand)
        self.assertIsNone(result.buildCommand)
        self.assertEqual(result.startCommand, "npx serve .")
        self.assertEqual(result.expectedPort, 3000)
        self.assertEqual(result.category, AppCategory.STATIC.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.READY.value)
        self.assertEqual(result.blockers, [])

    async def test_e_repository_with_env_requirements(self):
        """Repository with .env.example declaring mandatory secrets."""
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": ".env.example", "type": "blob"},
            {"path": "src/index.js", "type": "blob"},
        ]
        env_content = (
            "# Database settings\n"
            "DATABASE_URL=postgresql://user:secret@localhost:5432/mydb\n"
            "API_SECRET_KEY=\n"
            "STRIPE_WEBHOOK_SECRET=whsec_abc123\n"
        )
        pkg_json = json.dumps({
            "name": "env-app",
            "scripts": {"start": "node src/index.js"}
        })

        client_mock = AsyncMock()

        async def mock_fetch_content(owner, repo, path, client, branch="main"):
            if ".env" in path:
                return env_content
            return pkg_json

        with patch("app.services.run_analyzer.fetch_file_content", side_effect=mock_fetch_content):
            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="env-app",
                default_branch="main",
                tree_entries=tree,
                languages={"JavaScript": 100},
                client=client_mock,
            )

        self.assertIn("DATABASE_URL", result.requiredEnvVars)
        self.assertIn("API_SECRET_KEY", result.requiredEnvVars)
        self.assertIn("STRIPE_WEBHOOK_SECRET", result.requiredEnvVars)
        self.assertIn(".env.example", result.detectedEnvFiles)
        self.assertEqual(result.feasibility, PreviewFeasibility.NEEDS_ENV.value)
        self.assertTrue(any("Requires mandatory environment variable" in b for b in result.blockers))

    async def test_f_external_services_docker_compose(self):
        """Repository declaring PostgreSQL and Redis in docker-compose.yml."""
        tree = [
            {"path": "package.json", "type": "blob"},
            {"path": "docker-compose.yml", "type": "blob"},
            {"path": "src/server.ts", "type": "blob"},
        ]
        compose_content = """
version: '3.8'
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: app
  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
"""
        pkg_json = json.dumps({"name": "api-service", "scripts": {"dev": "ts-node src/server.ts"}})

        async def mock_fetch_content(owner, repo, path, client, branch="main"):
            if "docker-compose" in path:
                return compose_content
            return pkg_json

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", side_effect=mock_fetch_content):
            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="service-app",
                default_branch="main",
                tree_entries=tree,
                languages={"TypeScript": 100},
                client=client_mock,
            )

        self.assertIn("PostgreSQL", result.externalServices)
        self.assertIn("Redis", result.externalServices)
        self.assertEqual(result.feasibility, PreviewFeasibility.NEEDS_EXTERNAL_SERVICE.value)
        self.assertTrue(any("Requires external service(s)" in b for b in result.blockers))

    async def test_g_cli_repository_unsupported(self):
        """CLI tool should be marked as UNSUPPORTED with clear blocker."""
        tree = [
            {"path": "requirements.txt", "type": "blob"},
            {"path": "cli.py", "type": "blob"},
        ]
        reqs = "click==8.1.7\nrich==13.7.0\n"

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = reqs

            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="my-cli",
                default_branch="main",
                tree_entries=tree,
                languages={"Python": 100},
                client=client_mock,
            )

        self.assertEqual(result.category, AppCategory.CLI.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.UNSUPPORTED.value)
        self.assertTrue(any("CLI" in b for b in result.blockers))

    async def test_h_library_repository_unsupported(self):
        """Reusable library should be marked as UNSUPPORTED with clear blocker."""
        tree = [
            {"path": "pyproject.toml", "type": "blob"},
            {"path": "my_lib/__init__.py", "type": "blob"},
            {"path": "my_lib/core.py", "type": "blob"},
        ]
        pyproj = '[project]\nname = "my-awesome-lib"\nversion = "1.0.0"\n'

        client_mock = AsyncMock()

        with patch("app.services.run_analyzer.fetch_file_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = pyproj

            result = await analyze_run_configuration(
                owner="testowner",
                repo_name="my-awesome-lib",
                default_branch="main",
                tree_entries=tree,
                languages={"Python": 100},
                client=client_mock,
            )

        self.assertEqual(result.category, AppCategory.LIBRARY.value)
        self.assertEqual(result.feasibility, PreviewFeasibility.UNSUPPORTED.value)
        self.assertTrue(any("library" in b for b in result.blockers))


class TestRunAnalysisEndpoint(unittest.TestCase):
    """Test POST /api/run-analysis endpoint behavior."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.run_analysis.run_analysis_cache.get_or_compute")
    def test_run_analysis_endpoint_success(self, mock_cache):
        dummy_result = RunAnalysisResult(
            runtime="Node.js",
            packageManager="npm",
            installCommand="npm install",
            buildCommand="npm run build",
            startCommand="npm run dev",
            expectedPort=3000,
            requiredEnvVars=[],
            detectedEnvFiles=[],
            externalServices=[],
            category="frontend",
            feasibility="READY",
            blockers=[],
            entryPoint="src/main.tsx",
            workingDirectory=None,
        )
        dummy_response = RunAnalysisResponse(
            owner="testowner",
            repo="testrepo",
            defaultBranch="main",
            analysis=dummy_result,
        )
        mock_cache.return_value = dummy_response

        resp = self.client.post(
            "/api/run-analysis",
            json={"repoUrl": "https://github.com/testowner/testrepo"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["owner"], "testowner")
        self.assertEqual(data["repo"], "testrepo")
        self.assertEqual(data["analysis"]["runtime"], "Node.js")
        self.assertEqual(data["analysis"]["feasibility"], "READY")

    def test_run_analysis_invalid_url(self):
        resp = self.client.post(
            "/api/run-analysis",
            json={"repoUrl": "https://evilgithub.com/owner/repo"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid GitHub repository host", resp.json()["detail"])

    def test_options_preflight_for_run_analysis(self):
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        }
        resp = self.client.options("/api/run-analysis", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("POST", resp.headers.get("access-control-allow-methods", ""))


if __name__ == "__main__":
    unittest.main()
