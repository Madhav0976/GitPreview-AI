from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, List


class AnalyzeRequest(BaseModel):
    repoUrl: HttpUrl


class RepositoryMetadata(BaseModel):
    """Repository metadata from GitHub API"""
    owner: str
    name: str
    description: Optional[str]
    stars: int
    forks: int
    license: Optional[str]
    defaultBranch: str
    languages: Dict[str, int]
    technologies: List[str] = []
    projectType: Optional[str] = None
    summary: Optional[str] = None


class FolderAnalysis(BaseModel):
    entryPoints: List[str] = []
    importantFiles: List[str] = []
    folderSummary: List[str] = []


class AnalysisResponse(BaseModel):
    """Simplified response with repository metadata and folder analysis"""
    metadata: RepositoryMetadata
    folderAnalysis: FolderAnalysis
