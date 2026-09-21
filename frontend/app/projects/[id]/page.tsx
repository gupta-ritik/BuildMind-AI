import Link from 'next/link';

export default async function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-xl font-semibold mb-4">Project {id}</h1>
      <div className="rounded border border-border bg-panel p-6 text-sm text-muted">
        <p>
          Project detail views aren&apos;t wired up yet — see{' '}
          <Link href="/projects" className="text-accent hover:underline">
            Projects
          </Link>{' '}
          for why. Check the{' '}
          <Link href="/dashboard" className="text-accent hover:underline">
            Dashboard
          </Link>{' '}
          for all tasks in the meantime.
        </p>
      </div>
    </div>
  );
}
