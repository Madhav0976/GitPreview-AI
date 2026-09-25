import type { AnalyzeRequest, AnalysisResponse, RunAnalysisResponse } from './types'

const DEFAULT_API_BASE = 'https://gitpreview-ai-backend.onrender.com/api'
const ANALYZE_TIMEOUT_MS = 45000
const RUN_ANALYSIS_TIMEOUT_MS = 30000

const GITHUB_OWNER_REGEX = /^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$/
const GITHUB_REPO_REGEX = /^[a-zA-Z0-9_.-]{1,100}$/
const ALLOWED_GITHUB_SUBPATHS = new Set([
  'tree',
  'blob',
  'commit',
  'commits',
  'pull',
  'pulls',
  'issues',
  'actions',
  'releases',
  'wiki',
  'discussions',
  'compare',
  'branches',
  'tags',
  'raw',
  'blame',
])

/**
 * Deterministically normalize common GitHub repository URL inputs into canonical
 * `https://github.com/owner/repo` format, or return `null` if invalid/non-GitHub.
 */
export function normalizeGitHubRepoUrl(rawInput: string): string | null {
  if (!rawInput || typeof rawInput !== 'string') {
    return null
  }

  const trimmed = rawInput.trim()
  if (!trimmed) {
    return null
  }

  let decodedLower = ''
  try {
    decodedLower = decodeURIComponent(trimmed).toLowerCase()
  } catch {
    return null
  }

  if (trimmed.includes('..') || decodedLower.includes('..')) {
    return null
  }

  let owner = ''
  let repo = ''

  // 1. Handle SSH format: git@github.com:owner/repo(.git)
  if (trimmed.startsWith('git@github.com:')) {
    const pathPart = trimmed.slice('git@github.com:'.length).replace(/^\/+|\/+$/g, '')
    const segments = pathPart.split('/').filter(Boolean)
    if (segments.length !== 2) {
      return null
    }
    owner = segments[0]
    repo = segments[1].replace(/\.git$/i, '')
  } else {
    let candidate = trimmed

    // 2. Handle shorthand `owner/repo` (no scheme, not starting with github.com)
    if (
      !/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(candidate) &&
      !candidate.toLowerCase().startsWith('github.com/') &&
      !candidate.toLowerCase().startsWith('www.github.com/')
    ) {
      const cleanShorthand = candidate.replace(/^\/+|\/+$/g, '')
      const parts = cleanShorthand.split('/').filter(Boolean)
      // Shorthand must be owner/repo (or owner/repo/tree/...) where owner has no dots (not another domain)
      if (parts.length >= 2 && !parts[0].includes('.')) {
        candidate = `https://github.com/${cleanShorthand}`
      } else {
        return null
      }
    } else if (
      candidate.toLowerCase().startsWith('github.com/') ||
      candidate.toLowerCase().startsWith('www.github.com/')
    ) {
      candidate = `https://${candidate}`
    }

    let parsed: URL
    try {
      parsed = new URL(candidate)
    } catch {
      return null
    }

    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return null
    }

    const hostname = parsed.hostname.toLowerCase()
    if (hostname !== 'github.com' && hostname !== 'www.github.com') {
      return null
    }

    const segments = parsed.pathname
      .replace(/^\/+|\/+$/g, '')
      .split('/')
      .filter(Boolean)

    if (segments.length < 2) {
      return null
    }

    if (segments.length > 2) {
      const thirdSegment = segments[2].toLowerCase()
      if (!ALLOWED_GITHUB_SUBPATHS.has(thirdSegment)) {
        return null
      }
    }

    owner = segments[0]
    repo = segments[1].replace(/\.git$/i, '')
  }

  if (!GITHUB_OWNER_REGEX.test(owner)) {
    return null
  }

  if (!GITHUB_REPO_REGEX.test(repo) || repo === '.' || repo === '..') {
    return null
  }

  return `https://github.com/${owner}/${repo}`
}

export function getApiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE).trim()
  const withoutTrailingSlash = raw.replace(/\/+$/, '')
  return withoutTrailingSlash.endsWith('/api')
    ? withoutTrailingSlash
    : `${withoutTrailingSlash}/api`
}

export async function analyzeRepo(
  payload: AnalyzeRequest,
  externalSignal?: AbortSignal
): Promise<AnalysisResponse> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS)

  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId)
      throw new DOMException('Aborted', 'AbortError')
    }
    externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const response = await fetch(`${getApiBase()}/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'API request failed')
    }

    return await response.json()
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw err
      }
      throw new Error('Request timed out while waking up the analysis server. Please try again.')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
    if (externalSignal) {
      externalSignal.removeEventListener('abort', onExternalAbort)
    }
  }
}

export async function fetchRunAnalysis(
  payload: AnalyzeRequest,
  externalSignal?: AbortSignal
): Promise<RunAnalysisResponse> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), RUN_ANALYSIS_TIMEOUT_MS)

  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId)
      throw new DOMException('Aborted', 'AbortError')
    }
    externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const response = await fetch(`${getApiBase()}/run-analysis`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Run analysis request failed')
    }

    return await response.json()
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw err
      }
      throw new Error('Run analysis timed out. Please try again.')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
    if (externalSignal) {
      externalSignal.removeEventListener('abort', onExternalAbort)
    }
  }
}


