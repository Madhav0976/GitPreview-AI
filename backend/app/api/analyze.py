import asyncio
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
import httpx

from app.limiter import limiter
from app.models import (
    AnalyzeRequest,
    AnalysisResponse,
    RepositoryMetadata,
    FolderAnalysis,
)
from app.services.cache import analysis_cache
from app.services.github_client import (
    parse_repo_url,
    get_github_headers,
    fetch_repo_info,
    fetch_languages,
    fetch_git_tree,
    rate_limit_tracker,
    TIMEOUT,
)
from app.services.technology_detector import detect_technologies
from app.services.folder_analyzer import detect_folder_structure

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse, tags=["analysis"])
@limiter.limit("10/minute")
async def analyze(request: Request, body: AnalyzeRequest):
    repo_url = str(body.repoUrl).strip()

    try:
        owner, repo_name = parse_repo_url(repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def _do_analysis() -> AnalysisResponse:
        headers = get_github_headers()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
                # 1. Fetch core repository information
                repo_data = await fetch_repo_info(owner, repo_name, client)
                default_branch = repo_data.get("default_branch", "main")

                # 2. Fetch languages breakdown and recursive git tree in parallel
                lang_task = fetch_languages(owner, repo_name, client)
                tree_task = fetch_git_tree(owner, repo_name, default_branch, client)
                languages_data, tree_entries = await asyncio.gather(lang_task, tree_task)

                # 3. Detect technologies and folder structure in parallel using the tree
                tech_task = detect_technologies(
                    owner, repo_name, default_branch=default_branch, tree_entries=tree_entries, client=client
                )
                folder_task = detect_folder_structure(owner, repo_name, tree_entries=tree_entries)
                technologies_set, folder_analysis_data = await asyncio.gather(tech_task, folder_task)

                technologies_list = sorted(list(technologies_set))

                metadata_dict: Dict[str, Any] = {
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

                # 4. Project Type Detection (Enhanced with nested directory & multi-stack support)
                techs_lower = [t.lower() for t in technologies_list]
                folders_lower = [f.lower() for f in folder_analysis_data.get("folderSummary", [])]
                repo_name_lower = repo_name.lower()

                has_frontend_dir = any(d in folders_lower for d in ("frontend", "client", "web", "ui"))
                has_backend_dir = any(d in folders_lower for d in ("backend", "server", "api"))

                frontend_techs = {"react", "vue", "angular", "svelte", "next.js", "vite", "nuxt"}
                backend_techs = {"fastapi", "flask", "express", "django", "nestjs", "node.js", "go", "rust"}

                has_fe_tech = bool(set(techs_lower) & frontend_techs)
                has_be_tech = bool(set(techs_lower) & (backend_techs - {"node.js"}))

                project_type = "Library"

                if "next.js" in techs_lower or "django" in techs_lower or "nuxt" in techs_lower:
                    project_type = "Full Stack App"
                elif (has_frontend_dir and has_backend_dir) or (has_fe_tech and has_be_tech):
                    project_type = "Full Stack App"
                elif "fastapi" in techs_lower or "flask" in techs_lower or "express" in techs_lower or "nestjs" in techs_lower:
                    project_type = "Backend API"
                elif any(t in techs_lower for t in ("react", "vue", "angular", "svelte", "vite")):
                    if repo_name_lower in ("react", "vue", "angular", "svelte", "vite", "next.js"):
                        project_type = "Framework"
                    else:
                        project_type = "Frontend App"
                elif "go" in techs_lower or "rust" in techs_lower:
                    project_type = "Backend API" if has_backend_dir else "CLI / Systems App"

                metadata_dict["projectType"] = project_type

                # 5. Generate Summary
                desc = (metadata_dict.get("description") or "").strip()
                summary_parts: List[str] = []
                name = metadata_dict.get("name", repo_name)

                # Sentence 1: Purpose & Identity
                primary_lang = ""
                if languages_data:
                    primary_lang = max(languages_data.items(), key=lambda x: x[1])[0]

                if desc:
                    if not desc.endswith('.'):
                        desc += '.'
                    summary_parts.append(
                        f"{name} is a {primary_lang + ' ' if primary_lang else ''}{project_type.lower()}. {desc}"
                    )
                else:
                    summary_parts.append(
                        f"{name} is a {primary_lang + ' ' if primary_lang else ''}{project_type.lower()} repository."
                    )

                # Sentence 2: Architecture & Tooling
                arch_parts = []
                if "packages" in folders_lower or "workspaces" in folders_lower:
                    arch_parts.append("uses a monorepo architecture")
                elif has_frontend_dir and has_backend_dir:
                    arch_parts.append("features a decoupled frontend and backend architecture")

                if technologies_list:
                    top_techs = technologies_list[:3]
                    tech_str = ", ".join(top_techs) if len(top_techs) < 3 else f"{top_techs[0]}, {top_techs[1]}, and {top_techs[2]}"
                    arch_parts.append(f"is built with {tech_str}")

                if arch_parts:
                    summary_parts.append(f"This project {' and '.join(arch_parts)}.")

                # Sentence 3: Target Audience / Closing
                if "Framework" in project_type or "Library" in project_type:
                    summary_parts.append(f"It contains the core source code, tooling, and documentation for developers building with {name}.")
                elif "Full Stack" in project_type:
                    summary_parts.append("It provides an end-to-end full-stack application experience with client and server components.")
                elif project_type == "Frontend App" or has_fe_tech:
                    summary_parts.append("It is intended for frontend developers interested in modern web infrastructure.")
                elif project_type == "Backend API" or has_be_tech:
                    summary_parts.append("It is intended for backend developers interested in scalable API development.")
                else:
                    summary_parts.append("It serves as a reference for developers exploring this technology stack.")

                metadata_dict["summary"] = " ".join(summary_parts)

                metadata = RepositoryMetadata(**metadata_dict)
                folder_analysis = FolderAnalysis(**folder_analysis_data)

                return AnalysisResponse(
                    metadata=metadata,
                    folderAnalysis=folder_analysis
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
            logger.exception("Unexpected error analyzing repository %s", repo_url)
            raise HTTPException(
                status_code=500,
                detail=f"Error analyzing repository: {str(e)}"
            )

    return await analysis_cache.get_or_compute(owner, repo_name, _do_analysis)