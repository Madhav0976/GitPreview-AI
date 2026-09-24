"""
Repository Run Analysis Engine (GitPreview-AI V2 - Phase 1)

Inspects repository Git tree and manifest files to determine:
- Runtime (Node.js, Python, Go, Rust, Java, Static, etc.)
- Package manager (npm, pnpm, yarn, bun, pip, uv, poetry, Maven, Gradle, cargo, go)
- Install, build, and start commands
- Expected application port
- Environment variables and example files
- External services (PostgreSQL, MySQL, MongoDB, Redis, etc.)
- Application category and preview feasibility
"""

import json
import logging
import os
import re
from typing import Dict, Any, List, Set, Optional, Tuple
import httpx

from app.models import (
    AppCategory,
    PreviewFeasibility,
    RunAnalysisResult,
)
from app.services.github_client import fetch_file_content

logger = logging.getLogger(__name__)

# Standard environment example file patterns
ENV_EXAMPLE_PATTERNS = {
    ".env.example",
    ".env.sample",
    ".env.template",
    "env.example",
    "example.env",
    ".env.dist",
    ".env.defaults",
    ".env.local.example",
}

# Known external service dependency signatures
SERVICE_SIGNATURES = {
    "PostgreSQL": {
        "pg", "postgres", "postgresql", "psycopg2", "psycopg2-binary",
        "psycopg", "asyncpg", "@prisma/client", "pg-promise"
    },
    "MySQL": {
        "mysql", "mysql2", "pymysql", "mysqlclient", "mariadb"
    },
    "MongoDB": {
        "mongodb", "mongoose", "pymongo", "motor"
    },
    "Redis": {
        "redis", "ioredis", "aioredis"
    },
    "SQLite": {
        "sqlite3", "better-sqlite3", "aiosqlite"
    },
    "RabbitMQ": {
        "amqplib", "pika"
    },
}


def parse_env_file_variables(content: str) -> List[str]:
    """Extract variable names from .env or .env.example file content."""
    variables: List[str] = []
    seen = set()

    for line in content.splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Handle export KEY=VALUE or KEY=VALUE
        if line.startswith("export "):
            line = line[len("export "):].strip()

        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=", line)
        if match:
            var_name = match.group(1).strip()
            if var_name not in seen:
                seen.add(var_name)
                variables.append(var_name)
        elif re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", line):
            # Key with no value specified (e.g. DATABASE_URL)
            var_name = line.strip()
            if var_name not in seen:
                seen.add(var_name)
                variables.append(var_name)

    return variables


def detect_external_services_from_docker_compose(content: str) -> Set[str]:
    """Inspect docker-compose content to identify declared services."""
    services = set()
    content_lower = content.lower()

    if re.search(r"image:\s*['\"]?(postgres|timescale)", content_lower) or "postgres:" in content_lower:
        services.add("PostgreSQL")
    if re.search(r"image:\s*['\"]?(mysql|mariadb)", content_lower) or "mysql:" in content_lower:
        services.add("MySQL")
    if re.search(r"image:\s*['\"]?mongo", content_lower) or "mongo:" in content_lower:
        services.add("MongoDB")
    if re.search(r"image:\s*['\"]?redis", content_lower) or "redis:" in content_lower:
        services.add("Redis")
    if re.search(r"image:\s*['\"]?rabbitmq", content_lower) or "rabbitmq:" in content_lower:
        services.add("RabbitMQ")
    if re.search(r"image:\s*['\"]?elasticsearch", content_lower) or "elasticsearch:" in content_lower:
        services.add("Elasticsearch")

    return services


async def analyze_run_configuration(
    owner: str,
    repo_name: str,
    default_branch: str,
    tree_entries: List[Dict[str, Any]],
    languages: Dict[str, int],
    client: httpx.AsyncClient,
) -> RunAnalysisResult:
    """
    Main run analysis engine.
    Inspects repository tree and key configuration files to determine run and preview properties.
    """
    # 1. Normalize tree paths
    all_paths = {entry.get("path", "") for entry in tree_entries if entry.get("path")}
    path_lower_map = {p.lower(): p for p in all_paths}

    # 2. Check for environment files
    detected_env_files: List[str] = []
    required_env_vars: List[str] = []

    for path in all_paths:
        filename = os.path.basename(path).lower()
        if filename in ENV_EXAMPLE_PATTERNS or path.lower().endswith(".env.example"):
            detected_env_files.append(path)

    # Fetch content of the primary env example file (at most 1 network call)
    if detected_env_files:
        primary_env_file = sorted(detected_env_files, key=lambda p: (p.count("/"), len(p)))[0]
        env_content = await fetch_file_content(owner, repo_name, primary_env_file, client, default_branch)
        if env_content:
            required_env_vars = parse_env_file_variables(env_content)

    # 3. Detect external services from docker-compose if present
    external_services_set: Set[str] = set()
    for compose_candidate in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
        if compose_candidate in all_paths:
            compose_content = await fetch_file_content(owner, repo_name, compose_candidate, client, default_branch)
            if compose_content:
                external_services_set.update(detect_external_services_from_docker_compose(compose_content))
            break

    # 4. Resolve working directory and ecosystem targets
    # Check root first, then nested frontend / backend folders
    root_files = {p for p in all_paths if "/" not in p}

    working_dir = "."
    runtime: Optional[str] = None
    package_manager: Optional[str] = None
    install_command: Optional[str] = None
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    expected_port: Optional[int] = None
    category = AppCategory.UNKNOWN.value
    entry_point: Optional[str] = None

    # Check for Node.js package.json (root or nested)
    package_json_path: Optional[str] = None
    if "package.json" in root_files:
        package_json_path = "package.json"
        working_dir = "."
    elif "frontend/package.json" in all_paths:
        package_json_path = "frontend/package.json"
        working_dir = "frontend"
    elif "client/package.json" in all_paths:
        package_json_path = "client/package.json"
        working_dir = "client"
    elif "web/package.json" in all_paths:
        package_json_path = "web/package.json"
        working_dir = "web"

    # Check for Python manifests (root or nested)
    py_manifest_path: Optional[str] = None
    py_working_dir = "."
    for cand in ("requirements.txt", "pyproject.toml", "Pipfile", "manage.py"):
        if cand in root_files:
            py_manifest_path = cand
            py_working_dir = "."
            break
        elif f"backend/{cand}" in all_paths:
            py_manifest_path = f"backend/{cand}"
            py_working_dir = "backend"
            break
        elif f"server/{cand}" in all_paths:
            py_manifest_path = f"server/{cand}"
            py_working_dir = "server"
            break

    # -------------------------------------------------------------
    # A. NODE.JS APPLICATION HANDLING
    # -------------------------------------------------------------
    if package_json_path:
        runtime = "Node.js"
        # Determine package manager from lockfiles in same directory or root
        dir_prefix = "" if working_dir == "." else f"{working_dir}/"
        if f"{dir_prefix}pnpm-lock.yaml" in all_paths or "pnpm-lock.yaml" in all_paths:
            package_manager = "pnpm"
            install_command = "pnpm install"
        elif f"{dir_prefix}yarn.lock" in all_paths or "yarn.lock" in all_paths:
            package_manager = "yarn"
            install_command = "yarn install"
        elif f"{dir_prefix}bun.lockb" in all_paths or f"{dir_prefix}bun.lock" in all_paths or "bun.lockb" in all_paths:
            package_manager = "bun"
            install_command = "bun install"
        elif f"{dir_prefix}package-lock.json" in all_paths or "package-lock.json" in all_paths:
            package_manager = "npm"
            install_command = "npm install"
        else:
            package_manager = "npm"
            install_command = "npm install"

        # Fetch package.json content to inspect scripts & dependencies
        pkg_content = await fetch_file_content(owner, repo_name, package_json_path, client, default_branch)
        pkg_data: Dict[str, Any] = {}
        try:
            pkg_data = json.loads(pkg_content) if pkg_content else {}
        except Exception:
            pkg_data = {}

        deps = pkg_data.get("dependencies") or {}
        dev_deps = pkg_data.get("devDependencies") or {}
        all_deps = {**deps, **dev_deps}
        scripts = pkg_data.get("scripts") or {}

        # Scan dependencies for external service hints
        for dep in all_deps.keys():
            dep_lower = dep.lower()
            for service, sigs in SERVICE_SIGNATURES.items():
                if dep_lower in sigs:
                    external_services_set.add(service)

        # Build command
        if "build" in scripts:
            if package_manager == "npm":
                build_command = "npm run build"
            elif package_manager == "pnpm":
                build_command = "pnpm run build"
            elif package_manager == "yarn":
                build_command = "yarn build"
            elif package_manager == "bun":
                build_command = "bun run build"

        # Start / Run command
        pm_run = "npm run" if package_manager == "npm" else ("yarn" if package_manager == "yarn" else f"{package_manager} run")
        if "dev" in scripts:
            start_command = f"{pm_run} dev"
        elif "start" in scripts:
            start_command = f"{package_manager} start" if package_manager in ("npm", "yarn") else f"{package_manager} run start"
        elif "serve" in scripts:
            start_command = f"{pm_run} serve"
        elif "preview" in scripts:
            start_command = f"{pm_run} preview"

        # Port & Category
        if "next" in all_deps:
            expected_port = 3000
            category = AppCategory.FULL_STACK.value
            entry_point = "app/page.tsx" if "app/page.tsx" in all_paths or "src/app/page.tsx" in all_paths else "pages/index.tsx"
        elif "vite" in all_deps or "vite.config.ts" in all_paths or "vite.config.js" in all_paths:
            expected_port = 5173
            category = AppCategory.FRONTEND.value
            entry_point = "src/main.tsx" if "src/main.tsx" in all_paths else ("src/main.jsx" if "src/main.jsx" in all_paths else "index.html")
        elif "react-scripts" in all_deps:
            expected_port = 3000
            category = AppCategory.FRONTEND.value
            entry_point = "src/index.tsx" if "src/index.tsx" in all_paths else "src/index.js"
        elif "vue" in all_deps or "@vue/cli-service" in all_deps:
            expected_port = 5173 if "vite" in all_deps else 8080
            category = AppCategory.FRONTEND.value
        elif "svelte" in all_deps or "@sveltejs/kit" in all_deps:
            expected_port = 5173
            category = AppCategory.FULL_STACK.value if "@sveltejs/kit" in all_deps else AppCategory.FRONTEND.value
        elif "express" in all_deps or "@nestjs/core" in all_deps:
            expected_port = 3000
            category = AppCategory.BACKEND_API.value
        elif py_manifest_path and working_dir != ".":
            # Decoupled frontend + backend
            category = AppCategory.FULL_STACK.value
        elif start_command:
            expected_port = 3000
            category = AppCategory.BACKEND_API.value
        else:
            expected_port = 3000
            category = AppCategory.FRONTEND.value

    # -------------------------------------------------------------
    # B. PYTHON APPLICATION HANDLING (if not already handled or backend focus)
    # -------------------------------------------------------------
    elif py_manifest_path:
        runtime = "Python"
        working_dir = py_working_dir

        # Package manager detection
        dir_prefix = "" if working_dir == "." else f"{working_dir}/"
        if f"{dir_prefix}poetry.lock" in all_paths or "poetry.lock" in all_paths:
            package_manager = "poetry"
            install_command = "poetry install"
        elif f"{dir_prefix}uv.lock" in all_paths or "uv.lock" in all_paths:
            package_manager = "uv"
            install_command = "uv sync"
        elif f"{dir_prefix}Pipfile" in all_paths or "Pipfile" in all_paths:
            package_manager = "pipenv"
            install_command = "pipenv install"
        else:
            package_manager = "pip"
            req_file = f"{dir_prefix}requirements.txt" if f"{dir_prefix}requirements.txt" in all_paths else "requirements.txt"
            install_command = f"pip install -r {req_file}" if req_file in all_paths else "pip install -e ."

        # Inspect Python content for framework & dependencies
        content = await fetch_file_content(owner, repo_name, py_manifest_path, client, default_branch)
        content_lower = content.lower()

        for service, sigs in SERVICE_SIGNATURES.items():
            for sig in sigs:
                if re.search(rf"\b{re.escape(sig)}\b", content_lower):
                    external_services_set.add(service)

        # Detect framework & start command
        is_fastapi = "fastapi" in content_lower or any("fastapi" in p.lower() for p in all_paths)
        is_django = "django" in content_lower or "manage.py" in all_paths or f"{dir_prefix}manage.py" in all_paths
        is_flask = "flask" in content_lower

        if is_fastapi:
            category = AppCategory.BACKEND_API.value
            expected_port = 8000
            # Identify entry module
            if f"{dir_prefix}app/main.py" in all_paths:
                start_command = "uvicorn app.main:app --reload --port 8000"
                entry_point = f"{dir_prefix}app/main.py"
            elif f"{dir_prefix}main.py" in all_paths or "main.py" in all_paths:
                start_command = "uvicorn main:app --reload --port 8000"
                entry_point = "main.py"
            else:
                start_command = "uvicorn main:app --port 8000"

        elif is_django:
            category = AppCategory.FULL_STACK.value if "templates" in str(all_paths) else AppCategory.BACKEND_API.value
            expected_port = 8000
            start_command = "python manage.py runserver 0.0.0.0:8000"
            entry_point = f"{dir_prefix}manage.py" if f"{dir_prefix}manage.py" in all_paths else "manage.py"

        elif is_flask:
            category = AppCategory.BACKEND_API.value
            expected_port = 5000
            start_command = "flask run --port 5000"
            entry_point = f"{dir_prefix}app.py" if f"{dir_prefix}app.py" in all_paths else "app.py"

        else:
            # Check for CLI scripts
            if any(p.endswith("cli.py") or "click" in content_lower or "typer" in content_lower for p in all_paths):
                category = AppCategory.CLI.value
                start_command = "python main.py"
            else:
                category = AppCategory.LIBRARY.value

    # -------------------------------------------------------------
    # C. STATIC HTML / JAVASCRIPT HANDLING
    # -------------------------------------------------------------
    elif "index.html" in root_files or "index.htm" in root_files:
        runtime = "Static HTML / JS"
        package_manager = "None"
        install_command = None
        build_command = None
        start_command = "npx serve ."
        expected_port = 3000
        category = AppCategory.STATIC.value
        entry_point = "index.html"

    # -------------------------------------------------------------
    # D. OTHER ECOSYSTEMS (Go, Rust, Java)
    # -------------------------------------------------------------
    elif "go.mod" in root_files:
        runtime = "Go"
        package_manager = "go"
        install_command = "go mod download"
        build_command = "go build -o app"
        start_command = "go run ."
        expected_port = 8080
        category = AppCategory.BACKEND_API.value if any("http" in p for p in all_paths) else AppCategory.CLI.value
        entry_point = "main.go" if "main.go" in root_files else None

    elif "Cargo.toml" in root_files:
        runtime = "Rust"
        package_manager = "cargo"
        install_command = "cargo build"
        build_command = "cargo build --release"
        start_command = "cargo run"
        expected_port = 8080
        category = AppCategory.CLI.value

    elif "pom.xml" in root_files:
        runtime = "Java"
        package_manager = "Maven"
        install_command = "mvn clean install"
        build_command = "mvn package"
        start_command = "mvn spring-boot:run"
        expected_port = 8080
        category = AppCategory.BACKEND_API.value

    elif "build.gradle" in root_files or "build.gradle.kts" in root_files:
        runtime = "Java"
        package_manager = "Gradle"
        install_command = "./gradlew build" if "./gradlew" in all_paths or "gradlew" in all_paths else "gradle build"
        build_command = "./gradlew assemble"
        start_command = "./gradlew bootRun"
        expected_port = 8080
        category = AppCategory.BACKEND_API.value

    # -------------------------------------------------------------
    # 5. FEASIBILITY AND HUMAN-READABLE BLOCKERS
    # -------------------------------------------------------------
    blockers: List[str] = []
    feasibility = PreviewFeasibility.READY.value

    external_services = sorted(list(external_services_set))

    # Condition 1: Unsupported categories
    if category == AppCategory.LIBRARY.value:
        feasibility = PreviewFeasibility.UNSUPPORTED.value
        blockers.append("Repository is a library or reusable package rather than a standalone web application.")
    elif category == AppCategory.CLI.value:
        feasibility = PreviewFeasibility.UNSUPPORTED.value
        blockers.append("Repository is a command-line interface (CLI) tool, which cannot be previewed in a web browser.")
    elif not runtime:
        feasibility = PreviewFeasibility.UNKNOWN.value
        blockers.append("Could not confidently identify a supported web application runtime or entry point.")

    # Condition 2: External database/services required
    if external_services:
        feasibility = PreviewFeasibility.NEEDS_EXTERNAL_SERVICE.value
        blockers.append(f"Requires external service(s): {', '.join(external_services)}")

    # Condition 3: Mandatory environment variables required
    if required_env_vars:
        # If not already blocked by external service or unsupported, set to NEEDS_ENV
        if feasibility in (PreviewFeasibility.READY.value, PreviewFeasibility.UNKNOWN.value):
            feasibility = PreviewFeasibility.NEEDS_ENV.value
        # List up to 5 critical variable names
        var_sample = ", ".join(required_env_vars[:5])
        suffix = f" (+{len(required_env_vars) - 5} more)" if len(required_env_vars) > 5 else ""
        blockers.append(f"Requires mandatory environment variable(s): {var_sample}{suffix}")

    # Condition 4: Static sites and standard frontends with no blockers are READY
    if not blockers and category in (AppCategory.STATIC.value, AppCategory.FRONTEND.value):
        feasibility = PreviewFeasibility.READY.value

    return RunAnalysisResult(
        runtime=runtime,
        packageManager=package_manager,
        installCommand=install_command,
        buildCommand=build_command,
        startCommand=start_command,
        expectedPort=expected_port,
        requiredEnvVars=required_env_vars,
        detectedEnvFiles=sorted(detected_env_files),
        externalServices=external_services,
        category=category,
        feasibility=feasibility,
        blockers=blockers,
        entryPoint=entry_point,
        workingDirectory=working_dir if working_dir != "." else None,
    )
