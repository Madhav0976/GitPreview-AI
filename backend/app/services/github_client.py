import httpx
import os
from typing import Dict, Any, Tuple
from urllib.parse import urlparse
from app.services.technology_detector import detect_technologies


GITHUB_API_BASE = "https://api.github.com/repos"
TIMEOUT = 10
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)


def get_github_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Extract owner and repository name from GitHub URL.
    Handles formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    """
    # Normalize the URL
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


async def fetch_repo_metadata(repo_url: str) -> Dict[str, Any]:
    """
    Fetch repository metadata from GitHub REST API.
    Returns:
        Dictionary containing owner, name, description, stars, forks, license, defaultBranch, languages, technologies
    """
    owner, repo_name = parse_repo_url(repo_url)
    headers = get_github_headers()
    
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        # Fetch repository information
        repo_url_api = f"{GITHUB_API_BASE}/{owner}/{repo_name}"
        repo_response = await client.get(repo_url_api)
        repo_response.raise_for_status()
        repo_data = repo_response.json()
        
        # Fetch languages
        languages_url = f"{GITHUB_API_BASE}/{owner}/{repo_name}/languages"
        languages_response = await client.get(languages_url)
        languages_data = {}
        if languages_response.status_code == 200:
            languages_data = languages_response.json() or {}
        
        # Detect technologies by analyzing repository files
        default_branch = repo_data.get("default_branch", "main")
        technologies_set = await detect_technologies(owner, repo_name, default_branch=default_branch)
        technologies_list = sorted(list(technologies_set))
        
        return {
            "owner": owner,
            "name": repo_data.get("name", repo_name),
            "description": repo_data.get("description"),
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "license": repo_data.get("license", {}).get("name") if repo_data.get("license") else None,
            "defaultBranch": repo_data.get("default_branch", "main"),
            "languages": languages_data,
            "technologies": technologies_list,
        }
