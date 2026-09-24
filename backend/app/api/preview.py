"""
Static Preview API Router (GitPreview-AI V2 - Phase 2)

Endpoints:
- POST /api/preview/detect: Detects whether a repository can be previewed statically.
- GET /api/preview/{owner}/{repo}/{branch}/{file_path:path}: Secure static asset delivery proxy.
"""

import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
import httpx

from app.limiter import limiter
from app.models import (
    PreviewDetectRequest,
    PreviewDetectResponse,
)
from app.services.cache import analysis_cache
from app.services.github_client import (
    parse_repo_url,
    get_github_headers,
    fetch_repo_info,
    fetch_languages,
    fetch_git_tree,
    fetch_file_bytes,
    rate_limit_tracker,
    OWNER_REGEX,
    REPO_REGEX,
    TIMEOUT,
)
from app.services.static_preview_service import (
    detect_static_preview,
    sanitize_and_validate_path,
    inject_base_tag_into_html,
    STATIC_MIME_TYPES,
    MAX_CODE_SIZE_BYTES,
    MAX_MEDIA_SIZE_BYTES,
)

logger = logging.getLogger(__name__)

router = APIRouter()

BRANCH_REGEX = re.compile(r"^[a-zA-Z0-9_./-]+$")


@router.post("/preview/detect", response_model=PreviewDetectResponse, tags=["preview"])
@limiter.limit("10/minute")
async def detect_preview(request: Request, body: PreviewDetectRequest):
    """
    Detect whether a repository is eligible for static web preview.
    Reuses existing tree-first architecture and single-flight in-memory caching.
    """
    repo_url = str(body.repoUrl).strip()

    try:
        owner, repo_name = parse_repo_url(repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cache_key = f"preview_detect:{owner}/{repo_name}"

    async def _do_detect() -> PreviewDetectResponse:
        headers = get_github_headers()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
                repo_data = await fetch_repo_info(owner, repo_name, client)
                default_branch = repo_data.get("default_branch", "main")

                # Fetch languages and recursive git tree in parallel
                lang_task = fetch_languages(owner, repo_name, client)
                tree_task = fetch_git_tree(owner, repo_name, default_branch, client)
                languages_data, tree_entries = await asyncio.gather(lang_task, tree_task)

                return await detect_static_preview(
                    owner=owner,
                    repo_name=repo_data.get("name", repo_name),
                    default_branch=default_branch,
                    tree_entries=tree_entries,
                    languages=languages_data,
                    client=client,
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
                raise HTTPException(status_code=401, detail="GitHub API authentication failed.")
            elif status in (403, 429):
                raise HTTPException(status_code=429, detail="GitHub API rate limit exceeded.")
            raise HTTPException(status_code=500, detail=f"GitHub API error: {status}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="GitHub API request timed out.")
        except Exception as e:
            logger.exception("Error detecting static preview for %s", repo_url)
            raise HTTPException(status_code=500, detail=f"Error detecting preview: {str(e)}")

    return await analysis_cache.get_or_compute_by_key(cache_key, _do_detect)


@router.get("/preview/{owner}/{repo}/{branch}/{file_path:path}", tags=["preview"])
@limiter.limit("60/minute")
async def serve_preview_asset(
    request: Request,
    owner: str,
    repo: str,
    branch: str,
    file_path: str,
):
    """
    Secure static asset proxy:
    - Validates path against Git tree
    - Rejects path traversal and sensitive/executable files
    - Enforces size limits (2MB code, 5MB media)
    - Injects <base> tag into HTML entry point
    - Serves proper MIME types and restrictive Content-Security-Policy
    """
    # 1. Validate owner, repo, and branch format
    if not OWNER_REGEX.match(owner) or not REPO_REGEX.match(repo) or repo in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid repository coordinates.")

    if not BRANCH_REGEX.match(branch) or ".." in branch:
        raise HTTPException(status_code=400, detail="Invalid branch name.")

    cache_key = f"preview_asset:{owner}/{repo}/{branch}:{file_path.strip().lower()}"

    async def _fetch_and_prepare_asset() -> Dict[str, Any]:
        headers = get_github_headers()

        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
            # Fetch git tree to verify existence and avoid 404 probes
            tree_entries = await fetch_git_tree(owner, repo, branch, client)
            tree_paths = {entry.get("path", "") for entry in tree_entries if entry.get("type") == "blob"}

            # Validate path, extension, and ensure it exists in tree
            clean_path = sanitize_and_validate_path(file_path, tree_paths)

            ext = os.path.splitext(clean_path)[1].lower()
            mime_type = STATIC_MIME_TYPES.get(ext, "application/octet-stream")

            # Determine size limit
            is_code = ext in (".html", ".htm", ".css", ".js", ".mjs", ".json")
            size_limit = MAX_CODE_SIZE_BYTES if is_code else MAX_MEDIA_SIZE_BYTES

            raw_bytes, etag = await fetch_file_bytes(owner, repo, clean_path, client, branch)
            if raw_bytes is None:
                raise HTTPException(status_code=404, detail="Asset not found in repository.")

            if len(raw_bytes) > size_limit:
                max_mb = size_limit // (1024 * 1024)
                raise HTTPException(
                    status_code=413,
                    detail=f"Asset exceeds maximum allowed preview size of {max_mb}MB."
                )

            # If HTML, inject <base> tag for seamless relative asset resolution
            final_content = raw_bytes
            if ext in (".html", ".htm"):
                try:
                    html_text = raw_bytes.decode("utf-8", errors="replace")
                    processed_html = inject_base_tag_into_html(
                        html_text, owner=owner, repo=repo, branch=branch, file_path=clean_path
                    )
                    final_content = processed_html.encode("utf-8")
                except Exception as exc:
                    logger.warning("Failed to inject base tag into %s: %s", clean_path, exc)

            return {
                "content": final_content,
                "mime_type": mime_type,
                "etag": etag,
            }

    # Fetch from cache or compute
    asset_data = await analysis_cache.get_or_compute_by_key(cache_key, _fetch_and_prepare_asset)

    # Restrictive security headers
    response_headers = {
        "Content-Security-Policy": (
            "default-src 'self' 'unsafe-inline' data: blob: https:; "
            "object-src 'none'; "
            "frame-ancestors 'self' https://git-preview-ai.vercel.app https://gitpreview-ai.vercel.app http://localhost:3000;"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "public, max-age=1800",
    }
    if asset_data.get("etag"):
        response_headers["ETag"] = asset_data["etag"]

    return Response(
        content=asset_data["content"],
        media_type=asset_data["mime_type"],
        headers=response_headers,
    )
