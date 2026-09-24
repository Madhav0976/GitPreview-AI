"""
Technology detection service that analyzes repository structure and key files to identify:
- Frontend frameworks (React, Next.js, Vue, Angular, Vite, Svelte, Nuxt, Tailwind CSS)
- Backend frameworks (Node.js, Express, FastAPI, Flask, Django, NestJS)
- Programming languages (JavaScript, TypeScript, Python, Java, Go, Rust, PHP, Ruby, C#, Kotlin, C++)
- Package managers and dev tooling (npm, Yarn, pnpm, Bun, Docker, Maven, Gradle)
"""
import json
import logging
import os
import re
from typing import Set, Dict, Any, List, Optional
import httpx

from app.services.github_client import get_github_headers, fetch_file_content

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 12

# Standard root files for fallback detection
DETECTION_FILES = {
    "package.json": "detect_from_package_json",
    "requirements.txt": "detect_from_requirements_txt",
    "pyproject.toml": "detect_from_pyproject_toml",
    "package-lock.json": "detect_from_package_lock_json",
    "vite.config.ts": "detect_vite",
    "vite.config.js": "detect_vite",
    "next.config.js": "detect_next_config",
    "next.config.mjs": "detect_next_config",
    "manage.py": "detect_django",
    "app.py": "detect_flask_or_fastapi",
    "main.py": "detect_python_framework",
}

IGNORED_PATH_SEGMENTS = {
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "vendor",
    ".nuxt",
    ".cache",
}


def parse_workspaces_from_package_json(content: str) -> list[str]:
    """Extract workspace patterns from a package.json file."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    workspaces = data.get("workspaces")
    if isinstance(workspaces, dict):
        return workspaces.get("packages", []) or []
    if isinstance(workspaces, list):
        return workspaces
    return []


async def expand_workspace_package_paths(
    owner: str,
    repo_name: str,
    workspace_patterns: list[str],
    client: httpx.AsyncClient,
) -> list[str]:
    """Resolve workspace package.json paths from workspace patterns."""
    package_paths: list[str] = []
    for pattern in workspace_patterns:
        if pattern.endswith("/package.json"):
            package_paths.append(pattern)
            continue
        if pattern.endswith("/*"):
            directory = pattern[:-2].strip("/")
            package_paths.append(f"{directory}/package.json")
    return package_paths


def detect_from_package_json(content: str) -> Set[str]:
    """Detect technologies from package.json dependencies."""
    technologies = set()
    try:
        data = json.loads(content)
        deps = data.get("dependencies") or {}
        dev_deps = data.get("devDependencies") or {}
        peer_deps = data.get("peerDependencies") or {}
        dependencies = {**deps, **dev_deps, **peer_deps}
        package_name = str(data.get("name", "")).lower()

        # Frontend frameworks
        if "react" in dependencies or package_name == "react":
            technologies.add("React")
        if "next" in dependencies or package_name == "next":
            technologies.add("Next.js")
            technologies.add("React")
        if "vue" in dependencies or package_name == "vue":
            technologies.add("Vue")
        if "@angular/core" in dependencies or package_name in ("angular", "@angular/core"):
            technologies.add("Angular")
        if "svelte" in dependencies or "@sveltejs/kit" in dependencies or package_name == "svelte":
            technologies.add("Svelte")
        if "vite" in dependencies or package_name == "vite":
            technologies.add("Vite")
        if "tailwindcss" in dependencies:
            technologies.add("Tailwind CSS")

        # Backend frameworks
        if "express" in dependencies or package_name == "express":
            technologies.add("Express")
        if "@nestjs/core" in dependencies or package_name == "nest":
            technologies.add("NestJS")

        # Languages
        if "typescript" in dependencies or "typescript" in dev_deps:
            technologies.add("TypeScript")
        else:
            technologies.add("JavaScript")

        # Node.js is implied by package.json
        technologies.add("Node.js")

    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return technologies


def detect_from_requirements_txt(content: str) -> Set[str]:
    """Detect technologies from requirements.txt."""
    technologies = set()
    technologies.add("Python")
    lines = content.lower().split("\n")

    for line in lines:
        line = line.strip().split("#")[0].strip()
        if not line:
            continue
        package_name = line.split("==")[0].split(">")[0].split("<")[0].split("!")[0].split("~=")[0].strip()

        if package_name == "fastapi":
            technologies.add("FastAPI")
        elif package_name == "flask":
            technologies.add("Flask")
        elif package_name == "django":
            technologies.add("Django")

    return technologies


def _get_primary_deps_from_pyproject(content: str) -> str:
    """
    Extract dependencies block from pyproject.toml:
    supports standard [project.dependencies] (PEP 621) and [tool.poetry.dependencies] (Poetry).
    """
    primary_lines = []
    in_primary_deps = False
    in_project_block = False
    in_poetry_block = False

    for line in content.splitlines():
        stripped = line.strip().lower()

        if stripped.startswith('['):
            if stripped in ('[project]',):
                in_project_block = True
                in_poetry_block = False
                in_primary_deps = False
            elif stripped in ('[tool.poetry.dependencies]', '[tool.poetry.group.main.dependencies]'):
                in_poetry_block = True
                in_project_block = False
                in_primary_deps = True
                continue
            else:
                in_project_block = False
                in_poetry_block = False
                in_primary_deps = False
            continue

        if in_poetry_block:
            primary_lines.append(line)
            continue

        if in_project_block and re.match(r'^dependencies\s*=', stripped):
            in_primary_deps = True

        if in_primary_deps:
            primary_lines.append(line)
            if ']' in line and line.strip() != 'dependencies = [':
                in_primary_deps = False

    # Also capture project name
    name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
    if name_match:
        primary_lines.append(f'name = "{name_match.group(1)}"')

    return '\n'.join(primary_lines)


def detect_from_pyproject_toml(content: str) -> Set[str]:
    """Detect technologies from pyproject.toml primary dependencies."""
    technologies = set()
    technologies.add("Python")

    primary_section = _get_primary_deps_from_pyproject(content)
    check_text = primary_section.lower() if primary_section else content.lower()

    name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
    project_name = name_match.group(1).lower().strip() if name_match else ""

    if project_name == "fastapi" or re.search(r'\bfastapi\b', check_text):
        technologies.add("FastAPI")
    if project_name == "flask" or re.search(r'\bflask\b', check_text):
        technologies.add("Flask")
    if project_name in ("django", "django-cms") or re.search(r'\bdjango\b', check_text):
        technologies.add("Django")

    return technologies


def detect_from_package_lock_json(content: str) -> Set[str]:
    """Detect technologies from package-lock.json."""
    technologies = set()
    try:
        data = json.loads(content)
        dependencies = data.get("dependencies") or {}
        packages = data.get("packages") or {}
        package_name = str(data.get("name", "")).lower()

        root_pkg = packages.get("") or {}
        root_deps = root_pkg.get("dependencies") or {}
        root_dev_deps = root_pkg.get("devDependencies") or {}
        all_deps = {**dependencies, **root_deps, **root_dev_deps, **packages}

        if "react" in all_deps or "node_modules/react" in all_deps or package_name == "react":
            technologies.add("React")
        if "next" in all_deps or "node_modules/next" in all_deps or package_name == "next":
            technologies.add("Next.js")
            technologies.add("React")
        if "vue" in all_deps or "node_modules/vue" in all_deps or package_name == "vue":
            technologies.add("Vue")
        if "@angular/core" in all_deps or "node_modules/@angular/core" in all_deps or package_name == "angular":
            technologies.add("Angular")
        if "vite" in all_deps or "node_modules/vite" in all_deps or package_name == "vite":
            technologies.add("Vite")
        if "express" in all_deps or "node_modules/express" in all_deps or package_name == "express":
            technologies.add("Express")

        technologies.add("Node.js")
        technologies.add("JavaScript")
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return technologies


def detect_vite(content: str) -> Set[str]:
    """Detect Vite from config file."""
    return {"Vite"}


def detect_next_config(content: str) -> Set[str]:
    """Detect Next.js from config file."""
    return {"Next.js", "React", "Node.js", "JavaScript"}


def detect_django(content: str) -> Set[str]:
    """Detect Django from manage.py."""
    return {"Django", "Python"}


def detect_flask_or_fastapi(content: str) -> Set[str]:
    """Detect Flask or FastAPI from app.py."""
    technologies = set()
    technologies.add("Python")
    content_lower = content.lower()
    if re.search(r'from\s+fastapi\s+import|import\s+fastapi', content_lower):
        technologies.add("FastAPI")
    elif re.search(r'from\s+flask\s+import|import\s+flask', content_lower):
        technologies.add("Flask")
    return technologies


def detect_python_framework(content: str) -> Set[str]:
    """Detect Python frameworks from main.py."""
    technologies = set()
    technologies.add("Python")
    content_lower = content.lower()
    if re.search(r'from\s+fastapi\s+import|import\s+fastapi', content_lower):
        technologies.add("FastAPI")
    elif re.search(r'from\s+flask\s+import|import\s+flask', content_lower):
        technologies.add("Flask")
    elif re.search(r'from\s+django\s+import|import\s+django', content_lower):
        technologies.add("Django")
    return technologies


def _is_relevant_path(path: str) -> bool:
    """Filter out noise directories like node_modules, .git, venv, etc."""
    parts = set(path.split("/"))
    return not bool(parts & IGNORED_PATH_SEGMENTS)


async def detect_technologies(
    owner: str,
    repo_name: str,
    default_branch: str = "main",
    tree_entries: Optional[List[Dict[str, Any]]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Set[str]:
    """
    Detect technologies in a repository using a tree-first approach.
    Inspects normalized paths from the recursive Git Tree, then fetches at most
    1-2 manifest files (package.json, requirements.txt, pyproject.toml) to identify
    frameworks, without blind individual file probing.
    """
    technologies: Set[str] = set()

    # Determine if we need an internal client
    client_provided = client is not None
    active_client = client if client_provided else httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers=get_github_headers()
    )

    try:
        # If tree_entries was not passed, fetch it now
        if tree_entries is None:
            from app.services.github_client import fetch_git_tree
            tree_entries = await fetch_git_tree(owner, repo_name, default_branch, active_client)

        if tree_entries:
            # 1. Normalize and filter file paths
            relevant_files = [
                entry["path"].replace("\\", "/")
                for entry in tree_entries
                if entry.get("type") in ("blob", "file") and _is_relevant_path(entry.get("path", ""))
            ]

            filenames_set = {p.split("/")[-1].lower() for p in relevant_files}
            paths_lower = [p.lower() for p in relevant_files]

            # 2. Structural & Filename-based Detection (0 API calls!)
            # Ecosystems & Languages
            if any(f in filenames_set for f in ("package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")):
                technologies.add("Node.js")
                technologies.add("JavaScript")
            if any(p.endswith((".ts", ".tsx")) for p in paths_lower) or "tsconfig.json" in filenames_set:
                technologies.add("TypeScript")
                technologies.add("JavaScript")
                technologies.add("Node.js")
            if any(p.endswith(".py") for p in paths_lower) or any(f in filenames_set for f in ("requirements.txt", "pyproject.toml", "pipfile", "setup.py", "manage.py")):
                technologies.add("Python")
            if any(p.endswith(".go") for p in paths_lower) or "go.mod" in filenames_set:
                technologies.add("Go")
            if any(p.endswith(".rs") for p in paths_lower) or "cargo.toml" in filenames_set:
                technologies.add("Rust")
            if any(p.endswith(".java") for p in paths_lower) or any(f in filenames_set for f in ("pom.xml", "build.gradle")):
                technologies.add("Java")
            if "pom.xml" in filenames_set:
                technologies.add("Maven")
            if any(f in filenames_set for f in ("build.gradle", "build.gradle.kts")):
                technologies.add("Gradle")
            if any(p.endswith(".kt") for p in paths_lower) or "build.gradle.kts" in filenames_set:
                technologies.add("Kotlin")
            if any(p.endswith(".php") for p in paths_lower) or "composer.json" in filenames_set:
                technologies.add("PHP")
            if any(p.endswith(".rb") for p in paths_lower) or "gemfile" in filenames_set:
                technologies.add("Ruby")
            if any(p.endswith((".csproj", ".sln", ".cs")) for p in paths_lower):
                technologies.add("C#")
                technologies.add(".NET")
            if any(f in filenames_set for f in ("dockerfile", "docker-compose.yml", "docker-compose.yaml")) or any(f.endswith(".dockerfile") for f in filenames_set):
                technologies.add("Docker")

            # Package managers
            if "package-lock.json" in filenames_set:
                technologies.add("npm")
            if "yarn.lock" in filenames_set:
                technologies.add("Yarn")
            if "pnpm-lock.yaml" in filenames_set:
                technologies.add("pnpm")
            if "bun.lockb" in filenames_set:
                technologies.add("Bun")

            # Framework configs
            if any(f in filenames_set for f in ("vite.config.ts", "vite.config.js", "vite.config.mjs", "vite.config.cjs")):
                technologies.add("Vite")
            if any(f in filenames_set for f in ("next.config.js", "next.config.mjs", "next.config.ts")) or any("/pages/_app" in p or "/app/layout" in p for p in paths_lower):
                technologies.add("Next.js")
                technologies.add("React")
                technologies.add("Node.js")
                technologies.add("JavaScript")
            if any(f in filenames_set for f in ("nuxt.config.js", "nuxt.config.ts")):
                technologies.add("Nuxt")
                technologies.add("Vue")
            if any(f in filenames_set for f in ("vue.config.js", "vue.config.ts")) or any(p.endswith(".vue") for p in paths_lower):
                technologies.add("Vue")
            if any(f in filenames_set for f in ("svelte.config.js", "svelte.config.ts")) or any(p.endswith(".svelte") for p in paths_lower):
                technologies.add("Svelte")
            if "angular.json" in filenames_set:
                technologies.add("Angular")
            if any(f in filenames_set for f in ("tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs", "tailwind.config.cjs")):
                technologies.add("Tailwind CSS")
            if "manage.py" in filenames_set:
                technologies.add("Django")
                technologies.add("Python")

            # 3. Targeted Content Inspection (Fetch ONLY existing manifest files, max 2-3 files)
            # Find candidate package.json files (prefer root, then frontend/client/packages)
            package_json_candidates = [p for p in relevant_files if p.lower().endswith("package.json")]
            package_json_candidates.sort(key=lambda p: (p.count("/"), len(p)))

            for pkg_path in package_json_candidates[:2]:
                content = await fetch_file_content(owner, repo_name, pkg_path, active_client, default_branch=default_branch)
                if content:
                    detected = detect_from_package_json(content)
                    technologies.update(detected)

            # Find candidate Python requirement files
            py_manifest_candidates = [
                p for p in relevant_files
                if p.lower().endswith("requirements.txt") or p.lower().endswith("pyproject.toml")
            ]
            py_manifest_candidates.sort(key=lambda p: (0 if "requirements" in p.lower() else 1, p.count("/")))

            for py_path in py_manifest_candidates[:2]:
                content = await fetch_file_content(owner, repo_name, py_path, active_client, default_branch=default_branch)
                if content:
                    if py_path.lower().endswith("pyproject.toml"):
                        technologies.update(detect_from_pyproject_toml(content))
                    else:
                        technologies.update(detect_from_requirements_txt(content))

            # If Python frameworks not detected yet, check standalone app.py or main.py
            if not ({"FastAPI", "Flask", "Django"} & technologies) and "Python" in technologies:
                py_scripts = [p for p in relevant_files if p.lower().endswith(("/app.py", "app.py", "/main.py", "main.py"))]
                py_scripts.sort(key=lambda p: p.count("/"))
                for script_path in py_scripts[:1]:
                    content = await fetch_file_content(owner, repo_name, script_path, active_client, default_branch=default_branch)
                    if content:
                        technologies.update(detect_python_framework(content))

        else:
            # Fallback when Git tree is unavailable (e.g. empty repository or tree API error)
            logger.debug("Tree entries unavailable, executing fallback detection for %s/%s", owner, repo_name)
            for file_path, detector_name in DETECTION_FILES.items():
                detector_func = globals().get(detector_name)
                if not callable(detector_func):
                    continue
                content = await fetch_file_content(owner, repo_name, file_path, active_client, default_branch=default_branch)
                if content:
                    technologies.update(detector_func(content))

    finally:
        if not client_provided:
            await active_client.aclose()

    return technologies

