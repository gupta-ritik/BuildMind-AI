import Link from 'next/link';

export default function ProjectsPage() {
  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-xl font-semibold mb-4">Projects</h1>
      <div className="rounded border border-border bg-panel p-6 text-sm text-muted space-y-3">
        <p>
          The <code className="mono">Project</code> and <code className="mono">Repository</code>{' '}
          database models exist (see <code className="mono">backend/app/db/models.py</code>), but
          the API doesn't expose project CRUD endpoints yet — every task today is created directly
          against a repository path or URL, without being grouped into a project first.
        </p>
        <p>
          For now, browse tasks from the{' '}
          <Link href="/dashboard" className="text-accent hover:underline">
            Dashboard
          </Link>{' '}
          or start a new one directly.
        </p>
        <Link
          href="/tasks/new"
          className="inline-block px-3 py-1.5 rounded bg-accent text-white text-sm font-medium hover:bg-accent/80"
        >
          + New Task
        </Link>
      </div>
    </div>
  );
}
