"""
Technology detection service that analyzes repository files to identify:
- Frontend frameworks (React, Next.js, Vue, Angular, Vite)
- Backend frameworks (Node.js, Express, FastAPI, Flask, Django)
- Programming languages (JavaScript, TypeScript, Python, Java, C++, Go)
"""
import json
import logging
import os
import httpx
from typing import Set, Dict, Any

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 10
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

# Files to fetch and analyze
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


def get_github_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


async def list_repository_directory(
    owner: str,
    repo_name: str,
    path: str,
    client: httpx.AsyncClient,
    default_branch: str = "main",
) -> list[dict[str, Any]]:
    """List the contents of a repository directory using the GitHub API."""
    directory = path.strip("/")
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/contents/{directory}"
    try:
        response = await client.get(url)
        logger.debug("Listing %s/%s/%s => %s", owner, repo_name, directory or ".", response.status_code)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data

        if response.status_code in {403, 404}:
            logger.debug("Contents API failed for %s, falling back to git tree", url)
            tree_url = (
                f"{GITHUB_API_BASE}/{owner}/{repo_name}/git/trees/{default_branch}:{directory}"
                if directory
                else f"{GITHUB_API_BASE}/{owner}/{repo_name}/git/trees/{default_branch}"
            )
            tree_response = await client.get(tree_url)
            if tree_response.status_code == 200:
                tree_data = tree_response.json()
                if isinstance(tree_data, dict) and "tree" in tree_data:
                    entries = []
                    for entry in tree_data["tree"]:
                        if entry.get("path") and entry.get("type") in {"blob", "tree"}:
                            entries.append({
                                "name": entry["path"].split("/")[-1],
                                "type": "dir" if entry["type"] == "tree" else "file",
                            })
                    return entries
    except Exception:
        logger.exception("Failed to list repository directory %s/%s/%s", owner, repo_name, directory)
    return []


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
            entries = await list_repository_directory(owner, repo_name, directory, client, default_branch="main")
            for entry in entries:
                if entry.get("type") == "dir":
                    package_paths.append(f"{directory}/{entry['name']}/package.json")
            continue

        if "*" in pattern:
            prefix = pattern.split("*")[0].strip("/")
            entries = await list_repository_directory(owner, repo_name, prefix, client, default_branch="main")
            for entry in entries:
                if entry.get("type") == "dir":
                    package_paths.append(f"{prefix}{entry['name']}/package.json")
    return package_paths


async def fetch_file_content(
    owner: str,
    repo_name: str,
    file_path: str,
    client: httpx.AsyncClient,
    default_branch: str = "main",
) -> str:
    """Fetch file content from GitHub API, with raw.githubusercontent.com fallback."""
    api_url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/contents/{file_path}"
    try:
        response = await client.get(api_url)
        logger.debug("Fetching %s from %s/%s => %s", file_path, owner, repo_name, response.status_code)

        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                data = response.json()
                if isinstance(data, dict):
                    if "content" in data and data.get("encoding") == "base64":
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8")
                    if data.get("type") == "file" and "download_url" in data:
                        download_response = await client.get(data["download_url"])
                        if download_response.status_code == 200:
                            return download_response.text
                logger.debug("Unexpected JSON response for %s: %s", file_path, data)
                return ""
            if content_type.startswith("text/") or content_type == "application/octet-stream":
                return response.text
            try:
                return response.text
            except Exception:
                pass
        elif response.status_code == 404:
            logger.debug("File not found: %s", file_path)
        else:
            logger.warning("Failed to fetch %s: %s %s", file_path, response.status_code, response.text[:200])

        # Fallback to raw.githubusercontent.com for public repos when API access is blocked.
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{default_branch}/{file_path}"
        logger.debug("Falling back to raw.githubusercontent.com for %s", file_path)
        raw_response = await client.get(raw_url)
        if raw_response.status_code == 200:
            return raw_response.text
        logger.warning(
            "Raw fallback failed for %s: %s %s",
            file_path,
            raw_response.status_code,
            raw_response.text[:200],
        )
    except Exception as exc:
        logger.exception("Error fetching file %s for %s/%s", file_path, owner, repo_name)
    return ""


def detect_from_package_json(content: str) -> Set[str]:
    """Detect technologies from package.json."""
    technologies = set()
    try:
        data = json.loads(content)
        deps = data.get("dependencies") or {}
        dev_deps = data.get("devDependencies") or {}
        dependencies = {**deps, **dev_deps}
        package_name = str(data.get("name", "")).lower()

        # Frontend frameworks
        if "react" in dependencies or package_name == "react":
            technologies.add("React")
        if "next" in dependencies or package_name == "next":
            technologies.add("Next.js")
        if "vue" in dependencies or package_name == "vue":
            technologies.add("Vue")
        if "@angular/core" in dependencies or package_name == "angular" or package_name == "@angular/core":
            technologies.add("Angular")
        if "vite" in dependencies or package_name == "vite":
            technologies.add("Vite")

        # Backend frameworks
        if "express" in dependencies or package_name == "express":
            technologies.add("Express")

        # Languages
        if "typescript" in dependencies or "typescript" in dev_deps:
            technologies.add("TypeScript")
        else:
            technologies.add("JavaScript")

        # Node.js is implied if package.json exists
        technologies.add("Node.js")

    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return technologies


def detect_from_requirements_txt(content: str) -> Set[str]:
    """Detect technologies from requirements.txt."""
    technologies = set()
    technologies.add("Python")  # requirements.txt implies Python
    
    lines = content.lower().split("\n")
    
    for line in lines:
        line = line.strip().split("#")[0].strip()  # Remove comments
        if not line:
            continue
        
        # Extract package name (before version specifiers)
        package_name = line.split("==")[0].split(">")[0].split("<")[0].split("!")[0].strip()
        
        if package_name == "fastapi":
            technologies.add("FastAPI")
        elif package_name == "flask":
            technologies.add("Flask")
        elif package_name == "django":
            technologies.add("Django")
    
    return technologies


import re

def _get_primary_deps_from_pyproject(content: str) -> str:
    """
    Extract ONLY the primary [project] dependencies block from pyproject.toml,
    ignoring [project.optional-dependencies], [tool.*], etc.
    This prevents false positives from test/optional deps like flask in FastAPI.
    """
    primary_lines = []
    in_primary_deps = False
    in_project_block = False
    
    for line in content.splitlines():
        stripped = line.strip().lower()
        
        # Detect section headers
        if stripped.startswith('['):
            # Enter [project] block
            if stripped in ('[project]',):
                in_project_block = True
                in_primary_deps = False
            # Inside [project], detect the dependencies array start
            elif in_project_block and stripped == 'dependencies':
                # This is an inline key, handled below
                pass
            else:
                # Any other [section] exits the primary deps zone
                in_project_block = False
                in_primary_deps = False
            continue
        
        # Look for 'dependencies = [' inside [project] block only
        if in_project_block and re.match(r'^dependencies\s*=', stripped):
            in_primary_deps = True
        
        # Collect lines only while inside primary dependencies
        if in_primary_deps:
            primary_lines.append(line)
            # End of deps list
            if ']' in line and line.strip() != 'dependencies = [':
                in_primary_deps = False
    
    # Also capture name = "..." from [project] section for the repo's own identity
    name_match = re.search(r'^\[project\].*?^name\s*=\s*"([^"]+)"', content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if name_match:
        primary_lines.append(f'name = "{name_match.group(1)}"')
    
    return '\n'.join(primary_lines)


def detect_from_pyproject_toml(content: str) -> Set[str]:
    """Detect technologies from pyproject.toml primary dependencies only."""
    technologies = set()
    technologies.add("Python")
    
    # Use only primary deps to avoid false positives from test/optional groups
    primary_section = _get_primary_deps_from_pyproject(content)
    check_text = primary_section.lower() if primary_section else ""
    
    # Also always check the project name for direct framework repos
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
        
        # In lockfile v3, dependencies might be in "packages" -> "" -> "dependencies"
        root_pkg = packages.get("") or {}
        root_deps = root_pkg.get("dependencies") or {}
        root_dev_deps = root_pkg.get("devDependencies") or {}
        
        all_deps = {**dependencies, **root_deps, **root_dev_deps, **packages}
        
        # Frontend frameworks
        if "react" in all_deps or "node_modules/react" in all_deps or package_name == "react":
            technologies.add("React")
        if "next" in all_deps or "node_modules/next" in all_deps or package_name == "next":
            technologies.add("Next.js")
        if "vue" in all_deps or "node_modules/vue" in all_deps or package_name == "vue":
            technologies.add("Vue")
        if "@angular/core" in all_deps or "node_modules/@angular/core" in all_deps or package_name == "angular":
            technologies.add("Angular")
        if "vite" in all_deps or "node_modules/vite" in all_deps or package_name == "vite":
            technologies.add("Vite")
        
        # Backend
        if "express" in all_deps or "node_modules/express" in all_deps or package_name == "express":
            technologies.add("Express")
        
        # Node.js is implied
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


async def detect_technologies(owner: str, repo_name: str, default_branch: str = "main") -> Set[str]:
    """
    Detect technologies in a repository by fetching and analyzing key files.
    
    Args:
        owner: Repository owner
        repo_name: Repository name
        default_branch: Repository default branch name
    
    Returns:
        Set of detected technologies
    """
    technologies: Set[str] = set()
    headers = get_github_headers()
    logger.info("Starting technology detection for %s/%s", owner, repo_name)

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        for file_path, detector_name in DETECTION_FILES.items():
            detector_func = globals().get(detector_name)
            if not callable(detector_func):
                logger.warning("No detector function found for %s", detector_name)
                continue

            try:
                logger.debug("Checking file %s", file_path)
                content = await fetch_file_content(owner, repo_name, file_path, client, default_branch=default_branch)

                if file_path == "package.json":
                    workspace_patterns = parse_workspaces_from_package_json(content)
                    if workspace_patterns:
                        package_paths = await expand_workspace_package_paths(owner, repo_name, workspace_patterns, client)
                        for package_path in package_paths:
                            package_content = await fetch_file_content(owner, repo_name, package_path, client, default_branch=default_branch)
                            if package_content:
                                detected = detector_func(package_content)
                                logger.info("Detected %s from workspace package %s", detected, package_path)
                                technologies.update(detected)

                if not content:
                    logger.debug("No content found for %s", file_path)
                    continue

                detected = detector_func(content)
                logger.info("Detected %s from %s", detected, file_path)
                technologies.update(detected)
            except Exception as exc:
                logger.exception("Detection failed for %s: %s", file_path, exc)
                continue

    if not technologies:
        logger.warning("No technologies detected for %s/%s", owner, repo_name)
    else:
        logger.info("Final technologies for %s/%s: %s", owner, repo_name, technologies)

    return technologies
