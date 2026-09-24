import asyncio
from dataclasses import dataclass
import logging
import os
import re
import threading
import time
from typing import Dict, Any, Tuple, List, Optional
from urllib.parse import urlparse, unquote

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 12

# GitHub username/organization rules:
# - Alphanumeric characters or single hyphens
# - Cannot begin or end with a hyphen
# - Max length 39 characters
OWNER_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")

# GitHub repository name rules:
# - Alphanumeric characters, periods, hyphens, and underscores
# - Max length 100 characters
# - Cannot be '.' or '..'
REPO_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")

VALID_GITHUB_HOSTS = {"github.com", "www.github.com"}


@dataclass
class GitHubRateLimitStatus:
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_timestamp: Optional[int] = None
    last_updated: Optional[float] = None


class RateLimitTracker:
    """Thread-safe tracker for GitHub API quota usage based on response headers."""

    def __init__(self):
        self._status = GitHubRateLimitStatus()
        self._lock = threading.Lock()

    def update_from_headers(self, headers: Any) -> None:
        """Extract rate limit headers and update status safely."""
        if not headers:
            return

        limit_val = headers.get("x-ratelimit-limit")
        remaining_val = headers.get("x-ratelimit-remaining")
        reset_val = headers.get("x-ratelimit-reset")

        if remaining_val is not None:
            try:
                remaining = int(remaining_val)
                limit = int(limit_val) if limit_val is not None else None
                reset = int(reset_val) if reset_val is not None else None

                with self._lock:
                    self._status.limit = limit
                    self._status.remaining = remaining
                    self._status.reset_timestamp = reset
                    self._status.last_updated = time.time()

                if remaining < 500:
                    logger.warning(
                        "GitHub API quota running low: %d remaining (limit: %s, reset: %s)",
                        remaining,
                        limit,
                        reset,
                    )
            except (ValueError, TypeError):
                pass

    def get_status(self) -> Dict[str, Any]:
        """Return safe, non-sensitive rate limit statistics."""
        with self._lock:
            return {
                "limit": self._status.limit,
                "remaining": self._status.remaining,
                "reset_timestamp": self._status.reset_timestamp,
                "last_updated": self._status.last_updated,
            }


rate_limit_tracker = RateLimitTracker()


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
    Strictly validate and extract owner and repository name from GitHub URL.

    Accepts:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - http://github.com/owner/repo
    - git@github.com:owner/repo.git
    - git@github.com:owner/repo
    - Trailing slashes (e.g. https://github.com/owner/repo/)

    Rejects:
    - Host spoofing (evilgithub.com, github.com.evil.com, google.com)
    - Extra path segments (/owner/repo/pull/1, /owner/repo/tree/main)
    - Empty owner or empty repo
    - Path traversal attempts (.., %2e%2e)
    - Invalid characters in owner or repository name
    """
    if not repo_url or not isinstance(repo_url, str):
        raise ValueError("Repository URL must be a non-empty string.")

    cleaned = repo_url.strip()

    # Reject traversal tokens before or after URL decoding
    decoded = unquote(cleaned).lower()
    if ".." in cleaned or ".." in decoded:
        raise ValueError("Invalid GitHub repository URL: path traversal detected.")

    owner = ""
    repo_name = ""

    # 1. Handle SSH format: git@github.com:owner/repo[.git]
    if cleaned.startswith("git@github.com:"):
        path_part = cleaned[len("git@github.com:"):].strip("/")
        if path_part.endswith(".git"):
            path_part = path_part[:-4]

        parts = [p for p in path_part.split("/") if p]
        if len(parts) != 2:
            raise ValueError(f"Invalid GitHub repository URL path: expected 'owner/repo', got '{path_part}'")
        owner, repo_name = parts[0], parts[1]

    else:
        # 2. Handle HTTP/HTTPS format
        # Allow input without scheme like github.com/owner/repo
        if cleaned.startswith("github.com/") or cleaned.startswith("www.github.com/"):
            cleaned = "https://" + cleaned

        try:
            parsed = urlparse(cleaned)
        except Exception:
            raise ValueError(f"Malformed URL: {repo_url}")

        hostname = (parsed.hostname or "").lower()
        if hostname not in VALID_GITHUB_HOSTS:
            raise ValueError(f"Invalid GitHub repository host: '{hostname}'. Must be github.com.")

        # Require exactly two non-empty path segments: owner and repo
        raw_path = parsed.path.strip("/")
        if raw_path.endswith(".git"):
            raw_path = raw_path[:-4]

        parts = [p for p in raw_path.split("/") if p]
        if len(parts) != 2:
            raise ValueError(
                f"Invalid GitHub repository URL path. Expected exactly 'owner/repo', got '{parsed.path}'."
            )

        owner, repo_name = parts[0], parts[1]

    # Validate owner name
    if not OWNER_REGEX.match(owner):
        raise ValueError(
            f"Invalid GitHub repository owner name: '{owner}'. Must follow GitHub username guidelines."
        )

    # Validate repository name
    if not REPO_REGEX.match(repo_name) or repo_name in (".", ".."):
        raise ValueError(
            f"Invalid GitHub repository name: '{repo_name}'. Must follow GitHub repository naming rules."
        )

    return owner, repo_name


async def fetch_repo_info(owner: str, repo_name: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Fetch core repository metadata from GitHub REST API."""
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}"
    response = await client.get(url)
    rate_limit_tracker.update_from_headers(response.headers)
    response.raise_for_status()
    return response.json()


async def fetch_languages(owner: str, repo_name: str, client: httpx.AsyncClient) -> Dict[str, int]:
    """Fetch repository language breakdown."""
    url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/languages"
    try:
        response = await client.get(url)
        rate_limit_tracker.update_from_headers(response.headers)
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
        rate_limit_tracker.update_from_headers(response.headers)
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
        rate_limit_tracker.update_from_headers(response.headers)
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
                        rate_limit_tracker.update_from_headers(download_resp.headers)
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
