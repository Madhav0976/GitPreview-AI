import os
from typing import Any, Dict, List, Optional

import httpx

from app.services.github_client import get_github_headers

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 12

ENTRY_POINT_CANDIDATES = [
    "main.py",
    "app.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",

    "index.js",
    "index.ts",
    "main.js",
    "main.ts",
    "main.jsx",
    "main.tsx",

    "server.js",
    "server.ts",

    "src/index.js",
    "src/index.ts",
    "src/main.js",
    "src/main.ts",
    "src/main.jsx",
    "src/main.tsx",

    "app/page.tsx",
    "app/page.jsx",

    # Nested frontend/backend entry points
    "frontend/src/main.tsx",
    "frontend/src/index.tsx",
    "frontend/app/page.tsx",
    "client/src/main.tsx",
    "client/src/index.js",
    "backend/main.py",
    "backend/app.py",
    "server/index.js",
    "server/index.ts",
    "server/main.py",
]

IMPORTANT_FILE_NAMES = [
    "readme",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "dockerfile",
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    "next.config.js",
    "vite.config.ts",
    "cargo.toml",
    "go.mod",
    "pom.xml",
]

FOLDER_MARKERS = ["test", "tests", "docs"]


async def list_directory(owner: str, repo_name: str, path: str = "") -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/contents"
    if path:
        url = f"{url}/{path.strip('/') }"

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=get_github_headers()) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return []
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []


def normalize_name(name: str) -> str:
    return name.lower()


def is_readme(name: str) -> bool:
    name_lower = normalize_name(name)
    return name_lower.startswith("readme")


def detect_entry_points(root_names: List[str], src_names: List[str]) -> List[str]:
    results = []
    root_set = {normalize_name(name): name for name in root_names}
    src_set = {normalize_name(name): name for name in src_names}

    for candidate in ENTRY_POINT_CANDIDATES:
        if "src/" in candidate and "/" not in candidate.replace("src/", ""):
            src_file = candidate.split("src/")[1]
            if normalize_name(src_file) in src_set:
                results.append(candidate)
        else:
            if normalize_name(candidate) in root_set:
                results.append(candidate)

    # Safe fallback strategy
    if not results:
        fallbacks = [
            "package.json", "setup.py", "pyproject.toml", "Cargo.toml", 
            "go.mod", "pom.xml", "build.gradle", "Makefile"
        ]
        for fallback in fallbacks:
            if normalize_name(fallback) in root_set:
                results.append(root_set[normalize_name(fallback)])
                break

        if not results:
            for root_name in root_names:
                if normalize_name(root_name).startswith("readme"):
                    results.append(root_name)
                    break

        if not results and root_names:
            results.append(root_names[0])

    return results


def detect_important_files(root_names: List[str], workflows: List[str]) -> List[str]:
    important = []
    root_lower = {normalize_name(name): name for name in root_names}

    for important_name in IMPORTANT_FILE_NAMES:
        for root_name in root_names:
            if normalize_name(root_name) == important_name:
                important.append(root_name)
            elif important_name == "readme" and is_readme(root_name):
                important.append(root_name)

    if normalize_name("docker-compose.yml") in root_lower and "docker-compose.yml" not in important:
        important.append(root_lower[normalize_name("docker-compose.yml")])

    return sorted(dict.fromkeys(important))


def detect_folder_summary(root_dirs: List[str]) -> List[str]:
    return sorted(root_dirs)


async def detect_folder_structure(
    owner: str,
    repo_name: str,
    tree_entries: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, List[str]]:
    """
    Detect folder structure, entry points, and important files.
    If tree_entries is provided, performs all calculations in-memory with 0 API calls.
    Otherwise, gracefully falls back to GitHub contents API.
    """
    if tree_entries is not None:
        file_paths = [
            e["path"].replace("\\", "/")
            for e in tree_entries
            if e.get("type") in ("blob", "file") and "path" in e
        ]
        file_paths_lower_map = {p.lower(): p for p in file_paths}

        # Root files and root directories
        root_files = [p for p in file_paths if "/" not in p]
        root_dirs_set = set()
        for p in file_paths:
            if "/" in p:
                top_dir = p.split("/")[0]
                if top_dir not in (".git", "node_modules", "venv", ".venv"):
                    root_dirs_set.add(top_dir)

        workflows = [p for p in file_paths if p.startswith(".github/workflows/")]
        src_files = [p[4:] for p in file_paths if p.startswith("src/")]

        # Detect entry points from candidates in tree
        entry_points = []
        for candidate in ENTRY_POINT_CANDIDATES:
            cand_lower = candidate.lower()
            if cand_lower in file_paths_lower_map:
                entry_points.append(file_paths_lower_map[cand_lower])

        # If still empty, use fallback strategy
        if not entry_points:
            entry_points = detect_entry_points(root_files, src_files)

        # Detect important files from root files and workflows
        important_files = detect_important_files(root_files, workflows)

        # If root lacks manifest but nested exists, surface them
        for nested_manifest in ("frontend/package.json", "backend/requirements.txt", "client/package.json", "server/package.json"):
            if nested_manifest.lower() in file_paths_lower_map and nested_manifest not in important_files:
                important_files.append(file_paths_lower_map[nested_manifest.lower()])

        folder_summary = sorted(list(root_dirs_set))

        return {
            "entryPoints": sorted(dict.fromkeys(entry_points))[:6],
            "importantFiles": sorted(dict.fromkeys(important_files)),
            "folderSummary": folder_summary,
        }

    # Fallback when tree_entries is not provided
    root_entries = await list_directory(owner, repo_name)
    root_files = [entry["name"] for entry in root_entries if entry.get("type") == "file"]
    root_dirs = [entry["name"] for entry in root_entries if entry.get("type") == "dir"]

    workflows = []
    if ".github" in {normalize_name(name) for name in root_dirs}:
        workflows_entries = await list_directory(owner, repo_name, ".github/workflows")
        for entry in workflows_entries:
            if entry.get("type") == "file":
                workflows.append(f".github/workflows/{entry['name']}")

    src_files = []
    if "src" in {normalize_name(name) for name in root_dirs}:
        src_entries = await list_directory(owner, repo_name, "src")
        src_files = [entry["name"] for entry in src_entries if entry.get("type") == "file"]

    entry_points = detect_entry_points(root_files, src_files)
    important_files = detect_important_files(root_files, workflows)
    folder_summary = detect_folder_summary(root_dirs)

    return {
        "entryPoints": entry_points,
        "importantFiles": important_files,
        "folderSummary": folder_summary,
    }

