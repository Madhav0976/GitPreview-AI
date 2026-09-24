import asyncio
import logging
import os
from typing import Dict, Any, Tuple, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 12


def get_github_headers() -> Dict[str, str]:
    """Get standardized headers for GitHub API requests with dynamic token loading."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitPreview-AI"
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token.strip()}"
    return headers


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Extract owner and repository name from GitHub URL.
    Handles formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    """
    repo_url = repo_url.strip()

    # Handle git@ SSH format
    if repo_url.startswith("git@github.com:"):
        parts = repo_url.replace("git@github.com:", "").replace(".git", "").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]

    # Handle HTTPS format
    parsed = urlparse(repo_url)
    if parsed.hostname and "github.com" in parsed.hostname:
        path = parsed.path.strip("/")
        path = path.replace(".git", "")
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]

    raise ValueError(f"Invalid GitHub repository URL: {repo_url}")


async def fetch_repo_info(owner: str, repo_name: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Fetch core repository metadata from GitHub REST API."""
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}"
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def fetch_languages(owner: str, repo_name: str, client: httpx.AsyncClient) -> Dict[str, int]:
    """Fetch repository language breakdown."""
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/languages"
    try:
        response = await client.get(url)
        if response.status_code == 200:
            return response.json() or {}
    except Exception as e:
        logger.warning("Failed to fetch languages for %s/%s: %s", owner, repo_name, e)
    return {}


async def fetch_git_tree(
    owner: str,
    repo_name: str,
    branch: str,
    client: httpx.AsyncClient
) -> List[Dict[str, Any]]:
    """
    Fetch the entire repository tree recursively using the GitHub Git Trees API.
    Returns list of tree entries with 'path' and 'type' ('blob' or 'tree').
    """
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
    try:
        response = await client.get(url)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "tree" in data:
                return data["tree"]
        elif response.status_code in (404, 409):
            logger.info("Git tree not available for %s/%s at branch %s (status %s)", owner, repo_name, branch, response.status_code)
        else:
            logger.warning("Unexpected status %s fetching git tree for %s/%s", response.status_code, owner, repo_name)
    except Exception as e:
        logger.warning("Exception fetching git tree for %s/%s: %s", owner, repo_name, e)
    return []


async def fetch_file_content(
    owner: str,
    repo_name: str,
    file_path: str,
    client: httpx.AsyncClient,
    default_branch: str = "main",
) -> str:
    """
    Fetch file content cleanly using GitHub contents API.
    Returns empty string immediately on 404 without noisy fallbacks.
    """
    api_url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/contents/{file_path}"
    try:
        response = await client.get(api_url)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                data = response.json()
                if isinstance(data, dict):
                    if "content" in data and data.get("encoding") == "base64":
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    if data.get("type") == "file" and "download_url" in data:
                        download_resp = await client.get(data["download_url"])
                        if download_resp.status_code == 200:
                            return download_resp.text
                return ""
            return response.text
        elif response.status_code == 404:
            # File legitimately does not exist: return immediately. NO raw fallback.
            return ""

        # For 403/429 rate limit errors or other status codes on public repos, try raw content fallback
        if response.status_code in (403, 429):
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{default_branch}/{file_path}"
            raw_response = await client.get(raw_url)
            if raw_response.status_code == 200:
                return raw_response.text
    except Exception as exc:
        logger.debug("Error fetching %s for %s/%s: %s", file_path, owner, repo_name, exc)
    return ""


async def fetch_repo_metadata(repo_url: str) -> Dict[str, Any]:
    """
    Fetch repository metadata using the tree-based approach.
    Maintains full backwards compatibility with existing consumers.
    """
    from app.services.technology_detector import detect_technologies

    owner, repo_name = parse_repo_url(repo_url)
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        # 1. Fetch repository information
        repo_data = await fetch_repo_info(owner, repo_name, client)
        default_branch = repo_data.get("default_branch", "main")

        # 2. Fetch languages and git tree in parallel
        lang_task = fetch_languages(owner, repo_name, client)
        tree_task = fetch_git_tree(owner, repo_name, default_branch, client)
        languages_data, tree_entries = await asyncio.gather(lang_task, tree_task)

        # 3. Detect technologies from tree
        technologies_set = await detect_technologies(
            owner, repo_name, default_branch=default_branch, tree_entries=tree_entries, client=client
        )
        technologies_list = sorted(list(technologies_set))

        return {
            "owner": owner,
            "name": repo_data.get("name", repo_name),
            "description": repo_data.get("description"),
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "license": repo_data.get("license", {}).get("name") if repo_data.get("license") else None,
            "defaultBranch": default_branch,
            "languages": languages_data,
            "technologies": technologies_list,
        }

