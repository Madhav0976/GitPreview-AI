export interface AnalyzeRequest {
  repoUrl: string
}

export interface ScoreResponse {
  documentation: number
  structure: number
  maintainability: number
  overall: number
}

export interface AnalysisResponse {
  repoName: string
  description: string
  stars: number
  license: string | null
  primaryLanguage: string | null
  technologies: string[]
  projectType: string | null
  entryPoints: string[]
  importantFiles: string[]
  folderTree: Array<Record<string, unknown>>
  scores: ScoreResponse
  explanations: Record<string, string>
}
