"use client"

import { useState, useEffect } from 'react'
import { analyzeRepo } from '@/lib/api'
import type { AnalyzeRequest, AnalysisResponse } from '@/lib/types'
import Dashboard from './Dashboard'

const loadingMessages = [
  "Analyzing repository...",
  "Fetching repository metadata...",
  "Detecting technologies...",
  "Analyzing project structure...",
  "Generating summary...",
];

export default function RepoInputForm() {
  const [repoUrl, setRepoUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (loading) {
      setLoadingStep(0);
      interval = setInterval(() => {
        setLoadingStep((prev) => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
      }, 2500);
    } else {
      setLoadingStep(0);
    }
    return () => clearInterval(interval);
  }, [loading]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // Prevent duplicate submissions
    if (loading) return;

    setError(null)
    setResult(null)

    if (!repoUrl.trim()) {
      setError('Please enter a GitHub repository URL.')
      return
    }

    if (!repoUrl.includes("github.com")) {
      setError('Invalid GitHub repository URL. Please provide a valid link (e.g. https://github.com/owner/repo).')
      return
    }

    const payload: AnalyzeRequest = { repoUrl: repoUrl.trim() }
    setLoading(true)

    try {
      const response = await analyzeRepo(payload)
      setResult(response)
    } catch (err: any) {
      const msg: string = err.message || ''
      // Map specific backend errors to user-friendly messages
      if (msg.toLowerCase().includes('rate limit')) {
        setError('GitHub API rate limit exceeded. Please try again later.')
      } else if (msg.toLowerCase().includes('not found') || msg.toLowerCase().includes('private')) {
        setError('Repository not found. Please check the URL or ensure the repository is public.')
      } else if (msg.toLowerCase().includes('timed out') || msg.toLowerCase().includes('timeout')) {
        setError('Request timed out. GitHub may be slow — please try again.')
      } else if (msg.toLowerCase().includes('github api') || msg.toLowerCase().includes('unable to fetch')) {
        setError('Unable to fetch repository data from GitHub. Please try again.')
      } else if (msg.toLowerCase().includes('invalid github')) {
        setError('Invalid GitHub repository URL.')
      } else {
        setError(msg || 'Something went wrong while analyzing the repository.')
      }
    } finally {
      setLoading(false)
    }
  }

  function handleExampleClick(url: string) {
    setRepoUrl(url);
  }

  function handleReset() {
    setRepoUrl('');
    setResult(null);
    setError(null);
  }

  function handleCopyUrl() {
    navigator.clipboard.writeText(repoUrl);
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
            type="url"
            placeholder="https://github.com/owner/repository"
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
                <span className="text-xs text-blue-200 mt-1 font-medium">{loadingMessages[loadingStep]}</span>
              </div>
            ) : (
              "Analyze Repository"
            )}
          </button>
        </form>
      </div>

      {error ? (
        <div className="rounded-2xl border-l-4 border-red-500 bg-red-50 p-6 shadow-sm mx-auto max-w-2xl">
          <h3 className="text-lg font-semibold text-red-800 mb-1">Analysis Failed</h3>
          <p className="text-red-700">{error}</p>
        </div>
      ) : null}

      {!result && !loading && !error ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm mx-auto max-w-2xl">
          <h2 className="text-xl font-semibold text-slate-900">Paste a GitHub repository URL and click Analyze.</h2>
          <div className="mt-6 text-slate-600">
            <p className="mb-3 font-medium">Try:</p>
            <ul className="space-y-2 inline-block text-left">
              <li>
                <button type="button" onClick={() => handleExampleClick('https://github.com/facebook/react')} className="text-brand-600 hover:underline">
                  https://github.com/facebook/react
                </button>
              </li>
              <li>
                <button type="button" onClick={() => handleExampleClick('https://github.com/vercel/next.js')} className="text-brand-600 hover:underline">
                  https://github.com/vercel/next.js
                </button>
              </li>
              <li>
                <button type="button" onClick={() => handleExampleClick('https://github.com/tiangolo/fastapi')} className="text-brand-600 hover:underline">
                  https://github.com/tiangolo/fastapi
                </button>
              </li>
            </ul>
          </div>
        </div>
      ) : null}

      {result ? (
        <div className="space-y-6">
          <div className="flex justify-end gap-3 px-2">
            <button
              onClick={handleCopyUrl}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm border border-slate-200 hover:bg-slate-50 transition"
            >
              📋 Copy URL
            </button>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-red-600 shadow-sm border border-slate-200 hover:bg-red-50 transition"
            >
              🔄 Start Over
            </button>
          </div>
          <Dashboard data={result} />
        </div>
      ) : null}
    </div>
  )
}
