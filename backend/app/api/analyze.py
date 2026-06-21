import asyncio
from fastapi import APIRouter, HTTPException

from app.models import (
    AnalyzeRequest,
    AnalysisResponse,
    RepositoryMetadata,
    FolderAnalysis,
)

from app.services.github_client import (
    fetch_repo_metadata,
    parse_repo_url,
)

from app.services.folder_analyzer import detect_folder_structure

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse, tags=["analysis"])
async def analyze(request: AnalyzeRequest):
    try:
        repo_url = str(request.repoUrl)

        # Validate GitHub URL
        if "github.com" not in repo_url:
            raise HTTPException(
                status_code=400,
                detail="Invalid GitHub repository URL"
            )

        owner, repo_name = parse_repo_url(repo_url)

        # Run both tasks in parallel
        metadata_task = fetch_repo_metadata(repo_url)
        folder_task = detect_folder_structure(owner, repo_name)

        metadata_dict, folder_analysis_data = await asyncio.gather(
            metadata_task,
            folder_task
        )

        # Detect Project Type
        techs = [t.lower() for t in metadata_dict.get("technologies", [])]
        repo_name_lower = repo_name.lower()
        project_type = "Library"
        
        if "next.js" in techs or "django" in techs or "nuxt" in techs:
            project_type = "Full Stack App"
        elif "fastapi" in techs or "flask" in techs or "express" in techs:
            project_type = "Backend API"
        elif "react" in techs or "vue" in techs or "angular" in techs:
            if repo_name_lower in ["react", "vue", "angular", "next.js"]:
                project_type = "Framework"
            else:
                project_type = "Frontend App"

        metadata_dict["projectType"] = project_type

        # Generate Summary
        desc = metadata_dict.get("description", "").strip()
        tech_list = metadata_dict.get("technologies", [])
        folders = folder_analysis_data.get("folderSummary", [])
        
        summary_parts = []
        name = metadata_dict.get('name', repo_name)
        
        # Sentence 1: Purpose & Identity
        primary_lang = ""
        langs = metadata_dict.get("languages", {})
        if langs:
            primary_lang = max(langs.items(), key=lambda x: x[1])[0]
            
        if desc:
            if not desc.endswith('.'): desc += '.'
            summary_parts.append(f"{name} is a {primary_lang + ' ' if primary_lang else ''}{project_type.lower()}. {desc}")
        else:
            summary_parts.append(f"{name} is a {primary_lang + ' ' if primary_lang else ''}{project_type.lower()} repository.")
            
        # Sentence 2: Architecture & Tooling
        arch_parts = []
        if "packages" in folders or "workspaces" in folders:
            arch_parts.append("uses a monorepo architecture")
        
        if tech_list:
            top_techs = tech_list[:3]
            tech_str = ", ".join(top_techs) if len(top_techs) < 3 else f"{top_techs[0]}, {top_techs[1]}, and {top_techs[2]}"
            arch_parts.append(f"is built with {tech_str}")
            
        if arch_parts:
            summary_parts.append(f"This project {' and '.join(arch_parts)}.")
            
        # Sentence 3: Target Audience / Closing
        if "Framework" in project_type or "Library" in project_type:
            summary_parts.append(f"It contains the core source code, tooling, and documentation for developers building with {name}.")
        elif "React" in tech_list or "Next.js" in tech_list or project_type == "Frontend App":
            summary_parts.append("It is intended for frontend developers interested in modern web infrastructure.")
        elif "Python" in tech_list or project_type == "Backend API":
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

    except Exception as e:
        import httpx
        error_msg = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Repository not found or is private.")
            elif e.response.status_code in [403, 429]:
                raise HTTPException(status_code=429, detail="GitHub API rate limit exceeded. Please try again later.")
            error_msg = f"GitHub API error: {e.response.status_code}"
        elif isinstance(e, httpx.TimeoutException):
            raise HTTPException(status_code=504, detail="GitHub API request timed out.")

        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing repository: {error_msg}"
        )