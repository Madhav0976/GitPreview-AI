import type { AnalyzeRequest, AnalysisResponse } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/api'

export async function analyzeRepo(payload: AnalyzeRequest): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.detail || 'API request failed');
  }

  return response.json()
}
