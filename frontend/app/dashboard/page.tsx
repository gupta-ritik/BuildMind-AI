'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { listTasks } from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';
import type { TaskListItem } from '@/lib/types';

export default function DashboardPage() {
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTasks(50)
      .then((res) => setTasks(res.tasks))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page-shell mx-auto p-5 sm:p-8">
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="eyebrow">Workspace overview</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Build with momentum.</h1>
          <p className="mt-2 max-w-xl text-sm text-muted">Orchestrate planning, coding, testing, and review from one focused BuildMind AI workspace.</p>
        </div>
        <Link
          href="/tasks/new"
          className="button-primary inline-flex w-fit items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold"
        >
          <span className="text-lg leading-none">+</span> New task
        </Link>
      </div>

      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <div className="surface rounded-xl p-4"><p className="eyebrow">Active runs</p><p className="mt-3 text-2xl font-semibold">{tasks.filter((task) => !['completed', 'failed', 'rejected'].includes(task.status)).length}</p><p className="mt-1 text-xs text-muted">Currently in the pipeline</p></div>
        <div className="surface rounded-xl p-4"><p className="eyebrow">Total tasks</p><p className="mt-3 text-2xl font-semibold">{tasks.length}</p><p className="mt-1 text-xs text-muted">Across this workspace</p></div>
        <div className="surface rounded-xl p-4"><p className="eyebrow">Automation</p><p className="mt-3 text-2xl font-semibold text-success">Ready</p><p className="mt-1 text-xs text-muted">API and event stream online</p></div>
      </div>

      {loading && <p className="text-muted text-sm">Loading tasks…</p>}
      {error && (
        <p className="text-danger text-sm">
          Could not reach the backend: {error}. Is it running at{' '}
          <code className="mono">NEXT_PUBLIC_API_BASE_URL</code>?
        </p>
      )}

      {!loading && !error && tasks.length === 0 && (
        <div className="surface relative overflow-hidden rounded-2xl p-8 sm:p-12">
          <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full border border-cyan-200/10" />
          <p className="eyebrow">Start here</p>
          <h2 className="mt-3 max-w-md text-2xl font-semibold tracking-tight">Give your next change a capable co-pilot.</h2>
          <p className="mt-3 max-w-lg text-sm leading-6 text-muted">Point BuildMind AI at a repository, describe the outcome, and let the agent pipeline turn the brief into reviewed code.</p>
          <Link href="/tasks/new" className="button-primary mt-6 inline-flex rounded-lg px-4 py-2.5 text-sm font-bold">
            Create your first task
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {tasks.map((task) => (
          <Link
            key={task.task_id}
            href={`/tasks/${task.task_id}`}
            className="surface block rounded-xl p-4 transition-transform hover:-translate-y-0.5 hover:border-cyan-200/30"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium truncate max-w-md">{task.description}</p>
              <StatusBadge status={task.status} />
            </div>
            <div className="flex items-center justify-between mt-2 text-xs text-muted">
              <span className="mono">{task.task_id.slice(0, 8)}</span>
              <span>{task.created_at ? new Date(task.created_at).toLocaleString() : ''}</span>
            </div>
            {task.pull_request_url && (
              <a
                href={task.pull_request_url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-accent hover:underline mt-1 inline-block"
              >
                View PR ↗
              </a>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
