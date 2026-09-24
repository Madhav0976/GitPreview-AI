"use client"

import { useState, useEffect } from 'react'
import type { AnalysisResponse } from '@/lib/types'
import { detectPreview, type PreviewDetectResponse } from '@/lib/preview'
import PreviewBadge from './PreviewBadge'
import StaticPreviewModal from './StaticPreviewModal'

function getTechColor(tech: string) {
  const t = tech.toLowerCase();
  if (t.includes('react')) return 'bg-blue-100 text-blue-800 ring-blue-500/20';
  if (t.includes('typescript')) return 'bg-blue-100 text-blue-800 ring-blue-500/20';
  if (t.includes('python')) return 'bg-green-100 text-green-800 ring-green-500/20';
  if (t.includes('fastapi')) return 'bg-emerald-100 text-emerald-800 ring-emerald-500/20';
  if (t.includes('flask')) return 'bg-slate-100 text-slate-800 ring-slate-500/20';
  if (t.includes('next.js')) return 'bg-slate-800 text-white ring-slate-900/20';
  if (t.includes('node.js') || t.includes('javascript')) return 'bg-yellow-100 text-yellow-800 ring-yellow-600/20';
  return 'bg-slate-100 text-slate-800 ring-slate-500/20';
}

function formatNumber(num: number) {
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

interface DashboardProps {
  data: AnalysisResponse
  repoUrl?: string
}

export default function Dashboard({ data, repoUrl }: DashboardProps) {
  const { metadata, folderAnalysis } = data;

  const [previewData, setPreviewData] = useState<PreviewDetectResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    const targetUrl = repoUrl || `https://github.com/${metadata.owner}/${metadata.name}`;
    setPreviewLoading(true);

    detectPreview(targetUrl)
      .then((res) => setPreviewData(res))
      .catch((err) => {
        setPreviewData({
          status: 'UNSUPPORTED',
          category: metadata.projectType || 'unknown',
          entryPoint: null,
          previewUrl: null,
          totalAssets: 0,
          detectedAssets: [],
          blockers: [err.message || 'Failed to detect preview capabilities.'],
        });
      })
      .finally(() => setPreviewLoading(false));
  }, [metadata.owner, metadata.name, repoUrl, metadata.projectType]);

  const totalLangSize = Object.values(metadata.languages).reduce((a, b) => a + b, 0);
  const sortedLangs = Object.entries(metadata.languages).sort((a, b) => b[1] - a[1]);
  const validLangs = sortedLangs.filter(([_, size]) => totalLangSize > 0 && ((size / totalLangSize) * 100) >= 1);
  const topLangs = validLangs.slice(0, 5);
  const remainingLangs = sortedLangs.length - topLangs.length;

  const topFolders = folderAnalysis.folderSummary.slice(0, 8);
  const remainingFolders = folderAnalysis.folderSummary.length - 8;

  const primaryLang = sortedLangs.length > 0 ? sortedLangs[0][0] : "None";
  const repoSizeStr = totalLangSize > 5000000 ? "Large" : (totalLangSize > 500000 ? "Medium" : "Small");
  const docStatus = (
    folderAnalysis.importantFiles.some(f => f.toLowerCase().includes('readme')) ||
    folderAnalysis.folderSummary.some(f => f.toLowerCase().includes('docs'))
  ) ? "Available" : "Missing";

  const isPreviewReady = previewData?.status === 'READY';

  return (
    <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
      {/* 1. Premium Repository Header */}
      <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm lg:col-span-2 text-center sm:text-left">
        <div className="flex flex-col sm:flex-row justify-between items-center sm:items-start gap-4">
          <div className="w-full">
            <div className="flex flex-col sm:flex-row items-center sm:items-end gap-3 sm:gap-4">
              <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{metadata.name}</h1>
              {metadata.projectType && (
                <span className="mb-1 inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 ring-1 ring-inset ring-slate-200">
                  {metadata.projectType}
                </span>
              )}
            </div>
            <p className="text-sm font-medium text-slate-500 mt-2">{metadata.owner}/{metadata.name}</p>

            {metadata.summary ? (
              <div className="mt-6 rounded-2xl bg-indigo-50/40 p-5 sm:p-6 border border-indigo-100/60 relative text-left">
                <span className="absolute top-4 right-4 text-xl opacity-60">✨</span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-600 mb-2">AI Summary</h3>
                <p className="text-slate-700 leading-relaxed max-w-4xl pr-8 text-base sm:text-lg">
                  {metadata.summary}
                </p>
              </div>
            ) : metadata.description ? (
               <p className="mt-4 text-lg text-slate-700 max-w-3xl leading-relaxed">{metadata.description}</p>
            ) : null}
          </div>
        </div>
        <div className="mt-8 flex flex-wrap justify-center sm:justify-start gap-8 text-slate-600">
          <span className="flex items-center gap-2" title="Stars">
            <span className="text-xl">⭐</span> <span className="font-semibold text-slate-900">{formatNumber(metadata.stars)}</span>
          </span>
          <span className="flex items-center gap-2" title="Forks">
            <span className="text-xl">🍴</span> <span className="font-semibold text-slate-900">{formatNumber(metadata.forks)}</span>
          </span>
          <span className="flex items-center gap-2" title="License">
            <span className="text-xl">📜</span> <span className="font-medium text-slate-900">{metadata.license || 'No License'}</span>
          </span>
          <span className="flex items-center gap-2" title="Default Branch">
            <span className="text-xl">🌿</span> <span className="font-medium text-slate-900">{metadata.defaultBranch}</span>
          </span>
        </div>
      </div>

      {/* Live Static Preview Card (Phase 2 Feature) */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-7 shadow-sm lg:col-span-2">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-slate-900">Live Static Preview</h2>
              {previewLoading ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500">
                  <span className="h-2 w-2 animate-spin rounded-full border border-slate-400 border-t-transparent"></span>
                  Checking capabilities...
                </span>
              ) : (
                <PreviewBadge status={previewData?.status || 'UNKNOWN'} />
              )}
            </div>
            <p className="text-sm text-slate-500 max-w-2xl">
              {isPreviewReady
                ? `Valid HTML entry point discovered (${previewData?.entryPoint}). You can preview this static website inside an isolated, secure sandbox.`
                : previewData?.blockers && previewData.blockers.length > 0
                ? previewData.blockers[0]
                : 'Static preview is currently limited to plain HTML/CSS/JavaScript websites.'}
            </p>
          </div>

          <div>
            {isPreviewReady ? (
              <button
                type="button"
                onClick={() => setIsModalOpen(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm shadow-sm transition hover:shadow cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Open Live Preview
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 text-slate-400 font-medium text-sm cursor-not-allowed border border-slate-200"
              >
                Preview Unavailable
              </button>
            )}
          </div>
        </div>

        {/* If unsupported, show detailed blockers info */}
        {!isPreviewReady && previewData?.blockers && previewData.blockers.length > 0 && (
          <div className="mt-4 rounded-xl bg-slate-50 border border-slate-200/80 p-3.5 text-xs text-slate-600 flex items-start gap-2.5">
            <span className="text-amber-500 text-base leading-none">ℹ️</span>
            <div>
              <p className="font-semibold text-slate-700">Why is static preview unavailable?</p>
              <p className="mt-0.5">{previewData.blockers[0]}</p>
            </div>
          </div>
        )}
      </div>

      {/* Modal Viewport */}
      <StaticPreviewModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        previewUrl={previewData?.previewUrl || null}
        repoName={metadata.name}
        status={previewData?.status || 'UNSUPPORTED'}
        blockers={previewData?.blockers || []}
      />

      {/* Repository Insights Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Repository Insights</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4 text-sm">
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Project Type</span>
            <span className="text-slate-900 font-semibold">{metadata.projectType || "Library"}</span>
          </div>
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Primary Language</span>
            <span className="text-slate-900 font-semibold">{primaryLang}</span>
          </div>
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Technology Count</span>
            <span className="text-slate-900 font-semibold">{metadata.technologies.length}</span>
          </div>
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Folder Count</span>
            <span className="text-slate-900 font-semibold">{folderAnalysis.folderSummary.length}</span>
          </div>
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Documentation</span>
            <span className="text-slate-900 font-semibold">{docStatus}</span>
          </div>
          <div className="flex flex-col border-l-2 border-indigo-100 pl-3">
            <span className="text-slate-500 font-medium mb-1">Repository Size</span>
            <span className="text-slate-900 font-semibold">{repoSizeStr}</span>
          </div>
        </div>
      </div>

      {/* 2. Technologies Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900 mb-5">Technologies</h2>
        {metadata.technologies.length > 0 ? (
          <div className="flex flex-wrap gap-3">
            {metadata.technologies.map(tech => (
              <span key={tech} className={`inline-flex items-center rounded-full px-4 py-1.5 text-sm font-semibold ring-1 ring-inset ${getTechColor(tech)}`}>
                {tech}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-slate-500">No technologies detected.</p>
        )}
      </div>

      {/* 3. Languages Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900 mb-5">Languages</h2>
        {topLangs.length > 0 ? (
          <div className="space-y-5">
            {topLangs.map(([lang, size]) => {
                const percentage = totalLangSize > 0 ? ((size / totalLangSize) * 100) : 0;
                return (
                  <div key={lang}>
                    <div className="flex justify-between text-sm font-semibold text-slate-700 mb-1.5">
                      <span>{lang}</span>
                      <span className="text-slate-500">{percentage.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div className="bg-blue-500 h-2.5 rounded-full" style={{ width: `${percentage}%` }}></div>
                    </div>
                  </div>
                );
            })}
            {remainingLangs > 0 && (
              <p className="text-sm font-medium text-slate-500 pt-2 text-center border-t border-slate-100">
                +{remainingLangs} more languages
              </p>
            )}
          </div>
        ) : (
          <p className="text-slate-500">No languages detected.</p>
        )}
      </div>

      {/* 4. Entry Points Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Entry Points</h2>
        {folderAnalysis.entryPoints.length > 0 ? (
          <ul className="space-y-2 text-slate-700">
            {folderAnalysis.entryPoints.map(ep => (
              <li key={ep} className="flex items-start gap-2">
                <span className="text-blue-500 mt-1">•</span>
                <span className="font-medium">{ep}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">No entry points detected.</p>
        )}
      </div>

      {/* 5. Important Files Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Important Files</h2>
        {folderAnalysis.importantFiles.length > 0 ? (
          <ul className="space-y-2 text-slate-700">
            {folderAnalysis.importantFiles.map(f => (
              <li key={f} className="flex items-start gap-2">
                <span className="text-blue-500 mt-1">•</span>
                <span className="font-medium">{f}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">No important files detected.</p>
        )}
      </div>

      {/* 6. Folder Summary Card */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Project Structure</h2>
        {topFolders.length > 0 ? (
          <div>
            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 text-slate-700">
              {topFolders.map(folder => (
                <li key={folder} className="flex items-center gap-2">
                  <span className="text-blue-500 text-lg">📁</span>
                  <span className="font-medium truncate">{folder}</span>
                </li>
              ))}
            </ul>
            {remainingFolders > 0 && (
              <p className="text-sm font-medium text-slate-500 pt-4 mt-4 border-t border-slate-100">
                +{remainingFolders} more folders
              </p>
            )}
          </div>
        ) : (
          <p className="text-slate-500">No folders detected.</p>
        )}
      </div>
    </div>
  )
}
