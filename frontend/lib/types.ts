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
