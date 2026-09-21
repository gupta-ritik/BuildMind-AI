'use client';

import { useState } from 'react';
import type { TaskResponse } from '@/lib/types';

interface Props {
  task: TaskResponse;
  onApprove: () => Promise<void>;
  onReject: () => Promise<void>;
  onRequestChanges: () => Promise<void>;
}

export default function ApprovalPanel({ task, onApprove, onReject, onRequestChanges }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  if (task.status !== 'awaiting_approval') return null;

  const run = async (action: string, fn: () => Promise<void>) => {
    setBusy(action);
    try {
      await fn();
    } catch (error) {
      setBusy(null);
      throw error;
    }
  };

  const filesChanged = task.code_changes.length;
  const linesAdded = task.code_changes.reduce(
    (sum, c) => sum + c.diff.split('\n').filter((l) => l.startsWith('+') && !l.startsWith('+++')).length,
    0
  );
  const linesRemoved = task.code_changes.reduce(
    (sum, c) => sum + c.diff.split('\n').filter((l) => l.startsWith('-') && !l.startsWith('---')).length,
    0
  );
  const latestTest = task.test_results[task.test_results.length - 1];

  return (
    <div className="rounded border border-warn/40 bg-warn/5 p-4 space-y-3">
      <h3 className="font-semibold text-warn">Human approval required</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-muted">
        <span>Files changed</span>
        <span className="text-right text-white">{filesChanged}</span>
        <span>Lines added</span>
        <span className="text-right text-success">+{linesAdded}</span>
        <span>Lines removed</span>
        <span className="text-right text-danger">-{linesRemoved}</span>
        {latestTest && (
          <>
            <span>Tests</span>
            <span className="text-right text-white">
              {latestTest.passed} passed, {latestTest.failed} failed
            </span>
          </>
        )}
        {task.review_result && (
          <>
            <span>Code review</span>
            <span className="text-right text-white capitalize">
              {task.review_result.status.replace('_', ' ')}
            </span>
          </>
        )}
      </div>

      {task.review_result && task.review_result.issues.length > 0 && (
        <div className="text-sm">
          <p className="text-warn font-medium mb-1">Outstanding issues:</p>
          <ul className="list-disc list-inside text-muted space-y-0.5">
            {task.review_result.issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          disabled={!!busy}
          onClick={() => run('approve', onApprove)}
          className="px-3 py-1.5 rounded bg-success/20 text-success text-sm font-medium hover:bg-success/30 disabled:opacity-50"
        >
          {busy === 'approve' ? 'Approving…' : 'Approve & Create PR'}
        </button>
        <button
          disabled={!!busy}
          onClick={() => run('changes', onRequestChanges)}
          className="px-3 py-1.5 rounded bg-warn/20 text-warn text-sm font-medium hover:bg-warn/30 disabled:opacity-50"
        >
          {busy === 'changes' ? 'Sending…' : 'Request Changes'}
        </button>
        <button
          disabled={!!busy}
          onClick={() => run('reject', onReject)}
          className="px-3 py-1.5 rounded bg-danger/20 text-danger text-sm font-medium hover:bg-danger/30 disabled:opacity-50"
        >
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </button>
      </div>
    </div>
  );
}
