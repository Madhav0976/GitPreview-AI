import os
from typing import Any, Dict, List

import httpx

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 10
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

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
]

FOLDER_MARKERS = ["test", "tests", "docs"]


def get_github_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


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
        if "src/" in candidate:
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
                
        # If still empty, try to find a README
        if not results:
            for root_name in root_names:
                if normalize_name(root_name).startswith("readme"):
                    results.append(root_name)
                    break
                    
        # Ultimate fallback: just return the first file if one exists
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
    

    # Add docker-compose if it exists in root regardless of case
    if normalize_name("docker-compose.yml") in root_lower and "docker-compose.yml" not in important:
        important.append(root_lower[normalize_name("docker-compose.yml")])

    return sorted(dict.fromkeys(important))


def detect_folder_summary(root_dirs: List[str]) -> List[str]:
    return sorted(root_dirs)


async def detect_folder_structure(owner: str, repo_name: str) -> Dict[str, List[str]]:
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

    # Entry points are only recorded if they exist.
    entry_points = detect_entry_points(root_files, src_files)

    important_files = detect_important_files(root_files, workflows)

    folder_summary = detect_folder_summary(root_dirs)

    return {
        "entryPoints": entry_points,
        "importantFiles": important_files,
        "folderSummary": folder_summary,
    }
