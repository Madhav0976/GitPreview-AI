"use client"

import { useState, useEffect } from 'react'
import { resolvePreviewUrl } from '@/lib/preview'

interface StaticPreviewModalProps {
  isOpen: boolean
  onClose: () => void
  previewUrl: string | null
  repoName: string
  status: string
  blockers: string[]
}

type DeviceMode = 'desktop' | 'tablet' | 'mobile'

export default function StaticPreviewModal({
  isOpen,
  onClose,
  previewUrl,
  repoName,
  status,
  blockers,
}: StaticPreviewModalProps) {
  const [device, setDevice] = useState<DeviceMode>('desktop')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [iframeKey, setIframeKey] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const isReady = status === 'READY' && !!previewUrl
  const fullUrl = resolvePreviewUrl(previewUrl)

  useEffect(() => {
    if (isOpen) {
      setLoading(true)
      setError(null)
      setIframeKey((prev) => prev + 1)
    }
  }, [isOpen, previewUrl])

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown)
    }
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  function handleReload() {
    setLoading(true)
    setError(null)
    setIframeKey((prev) => prev + 1)
  }

  function getViewportWidth() {
    switch (device) {
      case 'mobile':
        return 'w-[375px]'
      case 'tablet':
        return 'w-[768px]'
      case 'desktop':
      default:
        return 'w-full'
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-2 sm:p-4">
      <div
        className={`flex flex-col bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden transition-all duration-300 ${
          isFullscreen
            ? 'w-full h-full rounded-none'
            : 'w-full max-w-6xl h-[90vh]'
        }`}
      >
        {/* Top Header Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/90 px-4 py-3 text-white">
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
            <h3 className="text-sm font-semibold truncate">
              Preview: <span className="text-slate-300">{repoName}</span>
            </h3>
            {previewUrl && (
              <span className="hidden sm:inline-block text-xs font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                {previewUrl.split('/').pop()}
              </span>
            )}
          </div>

          {/* Viewport Toggles (only when ready) */}
          {isReady && (
            <div className="flex items-center bg-slate-800/80 rounded-lg p-0.5 border border-slate-700/60 text-xs">
              <button
                type="button"
                onClick={() => setDevice('desktop')}
                className={`px-2.5 py-1 rounded-md transition ${
                  device === 'desktop'
                    ? 'bg-blue-600 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
                title="Desktop View (100%)"
              >
                Desktop
              </button>
              <button
                type="button"
                onClick={() => setDevice('tablet')}
                className={`px-2.5 py-1 rounded-md transition ${
                  device === 'tablet'
                    ? 'bg-blue-600 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
                title="Tablet View (768px)"
              >
                Tablet
              </button>
              <button
                type="button"
                onClick={() => setDevice('mobile')}
                className={`px-2.5 py-1 rounded-md transition ${
                  device === 'mobile'
                    ? 'bg-blue-600 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
                title="Mobile View (375px)"
              >
                Mobile
              </button>
            </div>
          )}

          {/* Control Actions */}
          <div className="flex items-center gap-2">
            {isReady && (
              <button
                type="button"
                onClick={handleReload}
                className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
                title="Reload preview"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
              title="Close modal (Esc)"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Viewport Area */}
        <div className="relative flex-1 bg-slate-900 flex items-center justify-center p-2 sm:p-4 overflow-hidden">
          {isReady ? (
            <div
              className={`relative h-full ${getViewportWidth()} bg-white rounded-lg shadow-xl overflow-hidden transition-all duration-300 border border-slate-700/50`}
            >
              {loading && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-white/90 backdrop-blur-xs">
                  <div className="h-8 w-8 animate-spin rounded-full border-3 border-blue-600 border-t-transparent"></div>
                  <p className="mt-3 text-xs font-medium text-slate-600">Loading static preview...</p>
                </div>
              )}

              {error ? (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-white p-6 text-center">
                  <div className="h-10 w-10 rounded-full bg-red-100 text-red-600 flex items-center justify-center mb-3">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <h4 className="text-sm font-semibold text-slate-900">Preview Load Error</h4>
                  <p className="mt-1 text-xs text-slate-500 max-w-sm">{error}</p>
                  <button
                    type="button"
                    onClick={handleReload}
                    className="mt-4 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-md transition"
                  >
                    Try Again
                  </button>
                </div>
              ) : null}

              {/* STRICTLY SANDBOXED IFRAME: NEVER ALLOW SAME ORIGIN OR TOP NAVIGATION */}
              <iframe
                key={iframeKey}
                src={fullUrl}
                title={`Live Preview of ${repoName}`}
                className="w-full h-full border-0 bg-white"
                sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
                loading="eager"
                referrerPolicy="no-referrer"
                onLoad={() => setLoading(false)}
                onError={() => {
                  setLoading(false)
                  setError('Failed to load preview asset from repository.')
                }}
              />
            </div>
          ) : (
            <div className="max-w-md w-full bg-slate-950 border border-slate-800 rounded-2xl p-6 text-center shadow-xl">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-400 mb-4">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-white">Static Preview Unavailable</h4>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                {blockers.length > 0
                  ? blockers[0]
                  : 'This repository does not have a detectable static HTML entry point or requires a build pipeline.'}
              </p>
              {blockers.length > 1 && (
                <ul className="mt-3 text-left bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-1">
                  {blockers.slice(1).map((b, idx) => (
                    <li key={idx} className="text-xs text-slate-400 list-disc list-inside">
                      {b}
                    </li>
                  ))}
                </ul>
              )}
              <button
                type="button"
                onClick={onClose}
                className="mt-5 w-full py-2 px-4 rounded-lg bg-slate-800 text-white text-xs font-medium hover:bg-slate-700 transition"
              >
                Close View
              </button>
            </div>
          )}
        </div>

        {/* Security & Isolation Footer Notice */}
        <div className="px-4 py-2 border-t border-slate-800 bg-slate-950 text-[11px] text-slate-400 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span>Isolated Sandbox: <code className="font-mono text-slate-300">allow-scripts allow-forms allow-popups</code> (opaque null origin; no-same-origin)</span>
          </div>
          <span className="text-slate-400">Zero backend execution • Read-only proxy</span>
        </div>
      </div>
    </div>
  )
}
