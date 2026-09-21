import type { TaskEvent, TaskListItem, TaskResponse } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function createTask(input: {
  repository_path?: string;
  repository_url?: string;
  task: string;
  branch_name?: string;
}): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return handleResponse<TaskResponse>(res);
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}`, { cache: 'no-store' });
  return handleResponse<TaskResponse>(res);
}

export async function listTasks(limit = 50): Promise<{ tasks: TaskListItem[] }> {
  const res = await fetch(`${API_BASE}/api/tasks?limit=${limit}`, { cache: 'no-store' });
  return handleResponse(res);
}

export async function approveTask(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/approve`, { method: 'POST' });
  return handleResponse<TaskResponse>(res);
}

export async function rejectTask(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/reject`, { method: 'POST' });
  return handleResponse<TaskResponse>(res);
}

export async function requestChanges(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/request-changes`, { method: 'POST' });
  return handleResponse<TaskResponse>(res);
}

export async function createPr(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/create-pr`, { method: 'POST' });
  return handleResponse<TaskResponse>(res);
}

export async function getPublicSettings(): Promise<{
  llm_provider: string;
  llm_model: string;
  max_debug_retries: number;
  max_review_cycles: number;
  use_docker_sandbox: boolean;
  github_configured: boolean;
}> {
  const res = await fetch(`${API_BASE}/api/settings/public`, { cache: 'no-store' });
  return handleResponse(res);
}

/**
 * Subscribes to a task's live event stream (real backend SSE, see
 * backend/app/api/routes.py: stream_task_events). Returns an unsubscribe
 * function. Falls back gracefully - if the EventSource errors (e.g. the
 * task already finished and the stream closed immediately), onDone still
 * fires so the UI doesn't hang waiting forever.
 */
export function streamTaskEvents(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  onDone: () => void
): () => void {
  const source = new EventSource(`${API_BASE}/api/tasks/${taskId}/stream`);

  source.onmessage = (msg) => {
    try {
      const event: TaskEvent = JSON.parse(msg.data);
      onEvent(event);
    } catch {
      // ignore malformed event
    }
  };

  source.onerror = () => {
    source.close();
    onDone();
  };

  return () => source.close();
}
