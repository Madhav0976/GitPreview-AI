import asyncio
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request
import httpx

from app.limiter import limiter
from app.models import (
    AnalyzeRequest,
    RunAnalysisResponse,
)
from app.services.cache import AnalysisCache
from app.services.github_client import (
    parse_repo_url,
    get_github_headers,
    fetch_repo_info,
    fetch_languages,
    fetch_git_tree,
    rate_limit_tracker,
    TIMEOUT,
)
from app.services.run_analyzer import analyze_run_configuration

logger = logging.getLogger(__name__)

router = APIRouter()

# 30-minute in-memory TTL cache for run-analysis responses
run_analysis_cache = AnalysisCache(ttl_seconds=30 * 60)


@router.post("/run-analysis", response_model=RunAnalysisResponse, tags=["run-analysis"])
@limiter.limit("10/minute")
async def run_analysis(request: Request, body: AnalyzeRequest):
    repo_url = str(body.repoUrl).strip()

    try:
        owner, repo_name = parse_repo_url(repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def _do_run_analysis() -> RunAnalysisResponse:
        headers = get_github_headers()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
                # 1. Fetch repo metadata for default branch
                repo_data = await fetch_repo_info(owner, repo_name, client)
                default_branch = repo_data.get("default_branch", "main")

                # 2. Fetch languages and recursive git tree in parallel (single-flight)
                lang_task = fetch_languages(owner, repo_name, client)
                tree_task = fetch_git_tree(owner, repo_name, default_branch, client)
                languages_data, tree_entries = await asyncio.gather(lang_task, tree_task)

                # 3. Analyze run properties and preview feasibility
                analysis_result = await analyze_run_configuration(
                    owner=owner,
                    repo_name=repo_name,
                    default_branch=default_branch,
                    tree_entries=tree_entries,
                    languages=languages_data,
                    client=client,
                )

                return RunAnalysisResponse(
                    owner=owner,
                    repo=repo_data.get("name", repo_name),
                    defaultBranch=default_branch,
                    analysis=analysis_result,
                )

        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            if e.response is not None:
                rate_limit_tracker.update_from_headers(e.response.headers)
            status = e.response.status_code if e.response is not None else 500
            if status == 404:
                raise HTTPException(status_code=404, detail="Repository not found or is private.")
            elif status == 401:
                raise HTTPException(
                    status_code=401,
                    detail="GitHub API authentication failed. The configured token is invalid or expired."
                )
            elif status in (403, 429):
                raise HTTPException(
                    status_code=429,
                    detail="GitHub API rate limit exceeded. Please try again later."
                )
            raise HTTPException(
                status_code=500,
                detail=f"GitHub API error: {status}"
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="GitHub API request timed out.")
        except Exception as e:
            logger.exception("Unexpected error analyzing run configuration for %s", repo_url)
            raise HTTPException(
                status_code=500,
                detail=f"Error analyzing repository run configuration: {str(e)}"
            )

    return await run_analysis_cache.get_or_compute(owner, repo_name, _do_run_analysis)
