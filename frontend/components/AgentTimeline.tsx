'use client';

import { AGENT_LABELS, AGENT_PIPELINE, TaskEvent } from '@/lib/types';

interface AgentState {
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration?: number;
}

export function computeAgentStates(
  events: TaskEvent[],
  nodeDurations: Record<string, number> = {}
): Record<string, AgentState> {
  const states: Record<string, AgentState> = {};
  for (const name of AGENT_PIPELINE) states[name] = { status: 'pending' };

  for (const event of events) {
    if (!event.agent) continue;
    if (event.type === 'agent_started') {
      states[event.agent] = { status: 'running' };
    } else if (event.type === 'agent_completed') {
      states[event.agent] = {
        status: event.status === 'failed' ? 'failed' : 'completed',
        duration: event.duration_seconds,
      };
    }
  }

  for (const [agent, duration] of Object.entries(nodeDurations)) {
    if (states[agent]?.status !== 'failed') {
      states[agent] = { status: 'completed', duration };
    }
  }
  return states;
}

const ICONS: Record<AgentState['status'], string> = {
  pending: '○',
  running: '◐',
  completed: '✓',
  failed: '✗',
};

const COLORS: Record<AgentState['status'], string> = {
  pending: 'text-muted',
  running: 'text-accent animate-pulse',
  completed: 'text-success',
  failed: 'text-danger',
};

export default function AgentTimeline({
  events,
  nodeDurations,
}: {
  events: TaskEvent[];
  nodeDurations?: Record<string, number>;
}) {
  const states = computeAgentStates(events, nodeDurations);

  return (
    <div className="space-y-1">
      {AGENT_PIPELINE.map((agent) => {
        const state = states[agent];
        return (
          <div
            key={agent}
            className="flex items-center justify-between rounded px-3 py-2 bg-panel border border-border"
          >
            <div className="flex items-center gap-2">
              <span className={`${COLORS[state.status]} font-mono`}>{ICONS[state.status]}</span>
              <span className="text-sm">{AGENT_LABELS[agent] ?? agent}</span>
            </div>
            {state.duration !== undefined && (
              <span className="text-xs text-muted mono">{state.duration.toFixed(2)}s</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
