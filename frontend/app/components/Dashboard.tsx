import type { AnalysisResponse } from '@/lib/types'

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

export default function Dashboard({ data }: { data: AnalysisResponse }) {
  const { metadata, folderAnalysis } = data;
  
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
