from enum import Enum
from pydantic import BaseModel, HttpUrl, Field
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
    entryPoints: List[str] = Field(default_factory=list)
    importantFiles: List[str] = Field(default_factory=list)
    folderSummary: List[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    """Simplified response with repository metadata and folder analysis"""
    metadata: RepositoryMetadata
    folderAnalysis: FolderAnalysis = FolderAnalysis()


# ==========================================
# V2 Run Analysis Models
# ==========================================

class AppCategory(str, Enum):
    STATIC = "static"
    FRONTEND = "frontend"
    BACKEND_API = "backend API"
    FULL_STACK = "full-stack"
    CLI = "cli"
    LIBRARY = "library"
    UNKNOWN = "unknown"


class PreviewFeasibility(str, Enum):
    READY = "READY"
    NEEDS_ENV = "NEEDS_ENV"
    NEEDS_EXTERNAL_SERVICE = "NEEDS_EXTERNAL_SERVICE"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class RunAnalysisResult(BaseModel):
    """How the repository could potentially be run and previewed"""
    runtime: Optional[str] = None
    packageManager: Optional[str] = None
    installCommand: Optional[str] = None
    buildCommand: Optional[str] = None
    startCommand: Optional[str] = None
    expectedPort: Optional[int] = None
    requiredEnvVars: List[str] = Field(default_factory=list)
    detectedEnvFiles: List[str] = Field(default_factory=list)
    externalServices: List[str] = Field(default_factory=list)
    category: str = AppCategory.UNKNOWN.value
    feasibility: str = PreviewFeasibility.UNKNOWN.value
    blockers: List[str] = Field(default_factory=list)
    entryPoint: Optional[str] = None
    workingDirectory: Optional[str] = None


class RunAnalysisResponse(BaseModel):
    """Complete V2 run analysis response"""
    owner: str
    repo: str
    defaultBranch: str
    analysis: RunAnalysisResult


# ==========================================
# V2 Phase 2 Static Preview Models
# ==========================================

class PreviewDetectRequest(BaseModel):
    """Request payload for static preview detection"""
    repoUrl: HttpUrl


class PreviewDetectResponse(BaseModel):
    """Detection result for static website preview feasibility"""
    status: str  # "READY" | "UNSUPPORTED"
    category: str
    entryPoint: Optional[str] = None
    previewUrl: Optional[str] = None
    totalAssets: int = 0
    detectedAssets: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
