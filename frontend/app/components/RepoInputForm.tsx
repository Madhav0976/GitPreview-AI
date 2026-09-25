"use client"

import { useState, useEffect, useRef } from 'react'
import { analyzeRepo, normalizeGitHubRepoUrl } from '@/lib/api'
import type { AnalyzeRequest, AnalysisResponse } from '@/lib/types'
import Dashboard from './Dashboard'

const loadingMessages = [
  "Analyzing repository...",
  "Fetching repository metadata...",
  "Detecting technologies...",
  "Analyzing project structure...",
  "Generating summary...",
];

export interface ExampleRepo {
  url: string;
  label: string;
  tag: string;
  highlight?: boolean;
}

export const EXAMPLE_REPOS: ExampleRepo[] = [
  {
    url: 'https://github.com/shahriar-tasnim/shahriar-tasnim.github.io',
    label: 'shahriar-tasnim.github.io',
    tag: 'Static Preview',
    highlight: true,
  },
  {
    url: 'https://github.com/vercel/next.js',
    label: 'vercel/next.js',
    tag: 'Next.js',
  },
  {
    url: 'https://github.com/facebook/react',
    label: 'facebook/react',
    tag: 'React',
  },
  {
    url: 'https://github.com/tiangolo/fastapi',
    label: 'tiangolo/fastapi',
    tag: 'Python / API',
  },
];

function LoadingSkeleton({ stepMessage, isColdStart }: { stepMessage: string; isColdStart: boolean }) {
  return (
    <div
      data-testid="analysis-loading-skeleton"
      className="mt-8 space-y-6 animate-pulse"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-3 w-full max-w-md">
            <div className="h-8 w-56 rounded-xl bg-slate-200" />
            <div className="h-4 w-36 rounded-lg bg-slate-100" />
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-4 py-1.5 text-xs font-semibold text-blue-700 border border-blue-100">
            <span className="h-2 w-2 rounded-full bg-blue-600 animate-ping" />
            {stepMessage}
          </span>
        </div>
        {isColdStart && (
          <p className="mt-4 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200/80 rounded-xl px-3.5 py-2 inline-block">
            Waking up backend service (Render cold start may take 15–30s)...
          </p>
        )}
        <div className="mt-6 h-20 w-full rounded-2xl bg-slate-100" />
        <div className="mt-6 flex flex-wrap gap-6">
          <div className="h-5 w-20 rounded-lg bg-slate-200" />
          <div className="h-5 w-20 rounded-lg bg-slate-200" />
          <div className="h-5 w-24 rounded-lg bg-slate-200" />
          <div className="h-5 w-20 rounded-lg bg-slate-200" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2 h-28" />
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2 h-36" />
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm h-48" />
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm h-48" />
      </div>
    </div>
  );
}

export default function RepoInputForm() {
  const [repoUrl, setRepoUrl] = useState('')
  const [analyzedRepoUrl, setAnalyzedRepoUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [isColdStart, setIsColdStart] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [copiedUrl, setCopiedUrl] = useState(false)
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    let interval: NodeJS.Timeout;
    let coldStartTimer: NodeJS.Timeout;
    if (loading) {
      setLoadingStep(0);
      setIsColdStart(false);
      interval = setInterval(() => {
        setLoadingStep((prev) => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
      }, 2500);
      coldStartTimer = setTimeout(() => {
        setIsColdStart(true);
      }, 5000);
    } else {
      setLoadingStep(0);
      setIsColdStart(false);
    }
    return () => {
      clearInterval(interval);
      clearTimeout(coldStartTimer);
    };
  }, [loading]);

  async function runRepositoryAnalysis(rawTargetUrl: string) {
    // Prevent duplicate submissions while already loading
    if (loading) return;

    const trimmed = rawTargetUrl.trim();

    // Immediately clear previous result & error so stale Dashboard is never shown during loading or on failure (UX-03)
    setError(null);
    setResult(null);
    setAnalyzedRepoUrl('');
    setCopiedUrl(false);

    if (!trimmed) {
      setError('Please enter a GitHub repository URL.');
      return;
    }

    const normalizedUrl = normalizeGitHubRepoUrl(trimmed);
    if (!normalizedUrl) {
      setError(
        'Invalid GitHub repository URL. Please provide a valid link (e.g. https://github.com/owner/repo or owner/repo).'
      );
      return;
    }

    setRepoUrl(normalizedUrl);
    const payload: AnalyzeRequest = { repoUrl: normalizedUrl };
    setLoading(true);

    try {
      const response = await analyzeRepo(payload);
      setAnalyzedRepoUrl(normalizedUrl);
      setResult(response);
    } catch (err: any) {
      setResult(null);
      setAnalyzedRepoUrl('');
      const msg: string = err.message || '';
      // Map specific backend errors to user-friendly messages
      if (msg.toLowerCase().includes('rate limit')) {
        setError('GitHub API rate limit exceeded. Please try again later.');
      } else if (msg.toLowerCase().includes('not found') || msg.toLowerCase().includes('private')) {
        setError('Repository not found. Please check the URL or ensure the repository is public.');
      } else if (msg.toLowerCase().includes('timed out') || msg.toLowerCase().includes('timeout')) {
        setError(msg);
      } else if (msg.toLowerCase().includes('github api') || msg.toLowerCase().includes('unable to fetch')) {
        setError('Unable to fetch repository data from GitHub. Please try again.');
      } else if (msg.toLowerCase().includes('invalid github')) {
        setError('Invalid GitHub repository URL.');
      } else {
        setError(msg || 'Something went wrong while analyzing the repository.');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runRepositoryAnalysis(repoUrl);
  }

  function handleExampleClick(url: string) {
    if (loading) return;
    setRepoUrl(url);
    void runRepositoryAnalysis(url);
  }

  function handleReset() {
    if (copyTimeoutRef.current) {
      clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = null;
    }
    setCopiedUrl(false);
    setRepoUrl('');
    setAnalyzedRepoUrl('');
    setResult(null);
    setError(null);
  }

  function handleCopyUrl() {
    const target = analyzedRepoUrl || normalizeGitHubRepoUrl(repoUrl) || repoUrl.trim();
    if (!target) return;

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
          .writeText(target)
          .then(() => {
            setCopiedUrl(true);
            if (copyTimeoutRef.current) {
              clearTimeout(copyTimeoutRef.current);
            }
            copyTimeoutRef.current = setTimeout(() => {
              setCopiedUrl(false);
              copyTimeoutRef.current = null;
            }, 2000);
          })
          .catch(() => {});
      }
    } catch {
      // Ignore clipboard permission failures gracefully without unhandled rejection
    }
  }

  return (
    <div className="mt-8 space-y-8">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-w-2xl mx-auto">
          <label className="sr-only" htmlFor="repoUrl">
            GitHub repository URL
          </label>
          <input
            id="repoUrl"
            type="text"
            inputMode="url"
            placeholder="https://github.com/owner/repository or owner/repository"
            value={repoUrl}
            onChange={(event) => setRepoUrl(event.target.value)}
            className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-5 py-4 text-slate-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-200"
          />

          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 py-3 font-semibold text-white shadow-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <div className="flex flex-col items-center">
                <div className="flex items-center gap-2">
                  <svg
                    className="h-5 w-5 animate-spin"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      className="opacity-25"
                    />
                    <path
                      fill="currentColor"
                      className="opacity-75"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  <span>Analyzing...</span>
                </div>
                <span className="text-xs text-blue-200 mt-1 font-medium">
                  {loadingMessages[loadingStep]}
                </span>
                {isColdStart && (
                  <span className="text-xs text-blue-100 mt-0.5 font-normal">
                    Waking up backend service (cold start may take 15–30s)...
                  </span>
                )}
              </div>
            ) : (
              "Analyze Repository"
            )}
          </button>
        </form>

        {/* Quick-Try Example Repositories (UX-02) */}
        <div className="mt-5 pt-5 border-t border-slate-100 max-w-2xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2.5 text-center sm:text-left">
            Instant Examples (Click to Analyze):
          </p>
          <div className="flex flex-wrap justify-center sm:justify-start gap-2">
            {EXAMPLE_REPOS.map((ex) => (
              <button
                key={ex.url}
                type="button"
                disabled={loading}
                onClick={() => handleExampleClick(ex.url)}
                className={`inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-medium border transition disabled:opacity-50 disabled:cursor-not-allowed ${
                  ex.highlight
                    ? 'bg-emerald-50/70 text-emerald-900 border-emerald-200 hover:bg-emerald-100/80'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                }`}
              >
                <span className="font-semibold">{ex.label}</span>
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                    ex.highlight
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-200/80 text-slate-600'
                  }`}
                >
                  {ex.tag}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border-l-4 border-red-500 bg-red-50 p-6 shadow-sm mx-auto max-w-2xl">
          <h3 className="text-lg font-semibold text-red-800 mb-1">Analysis Failed</h3>
          <p className="text-red-700">{error}</p>
        </div>
      ) : null}

      {loading ? (
        <LoadingSkeleton
          stepMessage={loadingMessages[loadingStep]}
          isColdStart={isColdStart}
        />
      ) : null}

      {!result && !loading && !error ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm mx-auto max-w-2xl">
          <h2 className="text-xl font-semibold text-slate-900">
            Paste a GitHub repository URL or select an example above to begin.
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Try the <span className="font-semibold text-emerald-700">Static Preview</span> example to test live sandboxed rendering in your browser.
          </p>
        </div>
      ) : null}

      {!loading && result ? (
        <div className="space-y-6">
          <div className="flex justify-end gap-3 px-2">
            <button
              type="button"
              onClick={handleCopyUrl}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-sm border transition ${
                copiedUrl
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              {copiedUrl ? '✓ Copied!' : '📋 Copy URL'}
            </button>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-red-600 shadow-sm border border-slate-200 hover:bg-red-50 transition"
            >
              🔄 Start Over
            </button>
          </div>
          <Dashboard data={result} repoUrl={analyzedRepoUrl} />
        </div>
      ) : null}
    </div>
  )
}


