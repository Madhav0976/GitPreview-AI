export interface AnalyzeRequest {
  repoUrl: string
}

export interface RepositoryMetadata {
  owner: string;
  name: string;
  description: string | null;
  stars: number;
  forks: number;
  license: string | null;
  defaultBranch: string;
  languages: Record<string, number>;
  technologies: string[];
  projectType: string | null;
  summary: string | null;
}

export interface FolderAnalysis {
  entryPoints: string[];
  importantFiles: string[];
  folderSummary: string[];
}

export interface AnalysisResponse {
  metadata: RepositoryMetadata;
  folderAnalysis: FolderAnalysis;
}

export type PreviewFeasibilityStatus =
  | 'READY'
  | 'NEEDS_ENV'
  | 'NEEDS_EXTERNAL_SERVICE'
  | 'UNSUPPORTED'
  | 'UNKNOWN'
  | string;

export interface RunAnalysisResult {
  runtime: string | null;
  packageManager: string | null;
  installCommand: string | null;
  buildCommand: string | null;
  startCommand: string | null;
  expectedPort: number | null;
  requiredEnvVars: string[];
  detectedEnvFiles: string[];
  externalServices: string[];
  category: string;
  feasibility: PreviewFeasibilityStatus;
  blockers: string[];
  entryPoint: string | null;
  workingDirectory: string | null;
}

export interface RunAnalysisResponse {
  owner: string;
  repo: string;
  defaultBranch: string;
  analysis: RunAnalysisResult;
}

