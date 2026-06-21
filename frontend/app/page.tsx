import RepoInputForm from './components/RepoInputForm'

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="mb-12 space-y-4 text-center">
          <p className="inline-flex rounded-full bg-slate-900 px-4 py-1.5 text-sm font-semibold tracking-wide text-white shadow-sm">
            GitPreview AI
          </p>
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Understand GitHub repositories instantly
          </h1>
          <p className="mx-auto max-w-2xl text-lg text-slate-600">
            Paste a GitHub repository URL and get a fast summary of the project structure, core technologies, and entry points.
          </p>
        </header>

        <RepoInputForm />
      </div>
    </main>
  )
}
