'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  approveTask,
  getTask,
  rejectTask,
  requestChanges,
  streamTaskEvents,
} from '@/lib/api';
import type { TaskEvent, TaskResponse } from '@/lib/types';
import StatusBadge from '@/components/StatusBadge';
import AgentTimeline from '@/components/AgentTimeline';
import DiffViewer from '@/components/DiffViewer';
import ApprovalPanel from '@/components/ApprovalPanel';

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'rejected', 'approved']);

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const taskId = params.id;

  const [task, setTask] = useState<TaskResponse | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const refreshTask = async () => {
    try {
      const t = await getTask(taskId);
      setTask(t);
      return t;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  };

  const waitForResume = async () => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const latest = await refreshTask();
      if (latest && latest.status !== 'awaiting_approval') return;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  };

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | null = null;

    (async () => {
      const initial = await refreshTask();
      if (cancelled || !initial) return;

      // Subscribe to live events regardless of current status - the
      // backend's stream endpoint itself decides whether anything is
      // actively running and closes immediately if not.
      unsubscribe = streamTaskEvents(
        taskId,
        (event) => {
          setEvents((prev) => [...prev, event]);
          if (
            event.type === 'task_paused_or_completed' ||
            event.type === 'task_error' ||
            event.type === 'agent_completed'
          ) {
            refreshTask();
          }
        },
        () => {
          // Stream closed - do a final refresh in case we missed the last write.
          refreshTask();
        }
      );
    })();

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  if (error) {
    return <p className="p-6 text-danger">{error}</p>;
  }
  if (!task) {
    return <p className="p-6 text-muted">Loading task…</p>;
  }

  const isTerminal = TERMINAL_STATUSES.has(task.status);

  return (
    <div className="p-4 grid grid-cols-12 gap-4 max-w-[1400px] mx-auto">
      {/* Left panel: repo + task description */}
      <aside className="col-span-3 space-y-3">
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold text-muted mb-2">Task</h2>
          <StatusBadge status={task.status} />
          <p className="text-sm mt-3 whitespace-pre-wrap">{task.plan?.goal ?? 'Planning…'}</p>
        </div>

        {task.plan && (
          <div className="rounded border border-border bg-panel p-4">
            <h2 className="text-sm font-semibold text-muted mb-2">Plan steps</h2>
            <ol className="list-decimal list-inside text-sm space-y-1">
              {task.plan.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </div>
        )}

        {task.relevant_files.length > 0 && (
          <div className="rounded border border-border bg-panel p-4">
            <h2 className="text-sm font-semibold text-muted mb-2">Relevant files</h2>
            <ul className="text-xs mono space-y-1">
              {task.relevant_files.map((f) => (
                <li key={f.path} title={f.reason} className="truncate text-accent">
                  {f.path}
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>

      {/* Center panel: agent timeline */}
      <section className="col-span-4 space-y-3">
        <h2 className="text-sm font-semibold text-muted">Agent execution</h2>
        <AgentTimeline events={events} nodeDurations={task.node_durations} />

        <ApprovalPanel
          task={task}
          onApprove={async () => {
            await approveTask(taskId);
            await waitForResume();
          }}
          onReject={async () => {
            await rejectTask(taskId);
            await waitForResume();
          }}
          onRequestChanges={async () => {
            await requestChanges(taskId);
            await waitForResume();
          }}
        />

        {task.final_report && (
          <div className="rounded border border-success/40 bg-success/5 p-4">
            <h3 className="font-semibold text-success mb-2">Final Report</h3>
            <pre className="mono text-xs whitespace-pre-wrap">{task.final_report}</pre>
            {task.pull_request_url && (
              <a
                href={task.pull_request_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block mt-2 text-accent hover:underline text-sm"
              >
                View Pull Request ↗
              </a>
            )}
          </div>
        )}
      </section>

      {/* Right panel: live logs */}
      <aside className="col-span-5 space-y-3">
        <h2 className="text-sm font-semibold text-muted">Logs &amp; events</h2>
        <div className="rounded border border-border bg-black/40 p-3 h-[420px] overflow-y-auto text-xs mono space-y-1">
          {task.execution_logs.map((line, i) => (
            <div key={`log-${i}`} className="text-gray-300">
              {line}
            </div>
          ))}
          {events.map((event, i) => (
            <div key={`event-${i}`} className="text-accent/80">
              [{new Date(event.timestamp * 1000).toLocaleTimeString()}] {event.type}
              {event.agent ? ` · ${event.agent}` : ''}
              {event.duration_seconds !== undefined ? ` · ${event.duration_seconds}s` : ''}
              {event.error ? ` · ${event.error}` : ''}
            </div>
          ))}
          <div ref={logsEndRef} />
          {!isTerminal && <div className="text-muted animate-pulse">● listening for live events…</div>}
        </div>

        {task.errors.length > 0 && (
          <div className="rounded border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
            {task.errors.map((err, i) => (
              <p key={i}>{err}</p>
            ))}
          </div>
        )}
      </aside>

      {/* Bottom: diff */}
      <div className="col-span-12 space-y-2 mt-2">
        <h2 className="text-sm font-semibold text-muted">
          Code changes {task.code_changes.length > 0 && `(${task.code_changes.length} files)`}
        </h2>
        {task.code_changes.length === 0 ? (
          <p className="text-muted text-sm italic">No changes yet.</p>
        ) : (
          task.code_changes.map((change) => (
            <details key={change.path} className="rounded border border-border bg-panel" open>
              <summary className="px-3 py-2 text-sm cursor-pointer mono flex items-center justify-between">
                <span>
                  {change.path}{' '}
                  <span className="text-muted text-xs">({change.change_type})</span>
                </span>
              </summary>
              <div className="p-3 pt-0">
                <p className="text-xs text-muted mb-2">{change.explanation}</p>
                <DiffViewer diff={change.diff} />
              </div>
            </details>
          ))
        )}
      </div>
    </div>
  );
}
