'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { createTask } from '@/lib/api';

type SourceMode = 'local' | 'github';

export default function NewTaskPage() {
  const router = useRouter();
  const [sourceMode, setSourceMode] = useState<SourceMode>('local');
  const [repositoryPath, setRepositoryPath] = useState('');
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [task, setTask] = useState('');
  const [branchName, setBranchName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await createTask({
        repository_path: sourceMode === 'local' ? repositoryPath : undefined,
        repository_url: sourceMode === 'github' ? repositoryUrl : undefined,
        task,
        branch_name: branchName || undefined,
      });
      router.push(`/tasks/${res.task_id}`);
    } catch (err: any) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <div className="page-shell mx-auto max-w-3xl p-5 sm:p-8">
      <p className="eyebrow">Agent workspace</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Start a new task</h1>
      <p className="mt-2 max-w-xl text-sm text-muted">Give the pipeline a repository and a crisp outcome. BuildMind AI will plan, implement, test, and pause for your review.</p>

      <form onSubmit={handleSubmit} className="surface mt-8 space-y-6 rounded-2xl p-5 sm:p-7">
        <div>
          <label className="block text-sm font-semibold mb-2">Repository</label>
          <div className="flex gap-2 mb-2">
            <button
              type="button"
              onClick={() => setSourceMode('local')}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                sourceMode === 'local' ? 'button-primary font-semibold' : 'border border-border bg-white/[0.03] text-muted'
              }`}
            >
              Local path
            </button>
            <button
              type="button"
              onClick={() => setSourceMode('github')}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                sourceMode === 'github' ? 'button-primary font-semibold' : 'border border-border bg-white/[0.03] text-muted'
              }`}
            >
              GitHub URL
            </button>
          </div>
          {sourceMode === 'local' ? (
            <input
              required
              value={repositoryPath}
              onChange={(e) => setRepositoryPath(e.target.value)}
              placeholder="/path/to/my-fastapi-project"
              className="w-full rounded-lg border border-border bg-black/20 px-3 py-2.5 text-sm mono focus:outline-none focus:border-cyan-200/50"
            />
          ) : (
            <input
              required
              value={repositoryUrl}
              onChange={(e) => setRepositoryUrl(e.target.value)}
              placeholder="https://github.com/you/your-repo.git"
              className="w-full rounded bg-panel border border-border px-3 py-2 text-sm mono focus:outline-none focus:border-accent"
            />
          )}
          <p className="text-xs text-muted mt-1">
            CodePilot copies (or clones) this into an isolated workspace — your original repository
            is never modified directly.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Task description</label>
          <textarea
            required
            rows={4}
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder='e.g. "Add JWT authentication with login, protected /users/me endpoint and unit tests."'
            className="w-full rounded-lg border border-border bg-black/20 px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-200/50"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Branch name (optional)</label>
            <input
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              placeholder="codepilot/task-..."
              className="w-full rounded-lg border border-border bg-black/20 px-3 py-2.5 text-sm mono focus:outline-none focus:border-cyan-200/50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Model</label>
            <input
              disabled
              value="Configured via backend .env"
              className="w-full rounded-lg border border-border bg-black/20 px-3 py-2.5 text-sm text-muted"
            />
            <p className="text-xs text-muted mt-1">See Settings for the active provider/model.</p>
          </div>
        </div>

        {error && <p className="text-danger text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="button-primary rounded-lg px-4 py-2.5 text-sm font-bold disabled:opacity-50"
        >
          {submitting ? 'Starting…' : 'Start CodePilot'}
        </button>
      </form>
    </div>
  );
}
