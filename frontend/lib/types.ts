export interface Plan {
  goal: string;
  steps: string[];
  acceptance_criteria: string[];
  risks: string[];
}

export interface RelevantFile {
  path: string;
  reason: string;
}

export interface CodeChange {
  path: string;
  change_type: string;
  diff: string;
  explanation: string;
}

export interface TestResult {
  status: string;
  passed: number;
  failed: number;
  errors: string[];
  output: string;
  duration_seconds: number;
}

export interface ReviewResult {
  status: string;
  issues: string[];
  suggestions: string[];
}

export interface TaskResponse {
  task_id: string;
  status: string;
  plan: Plan | null;
  relevant_files: RelevantFile[];
  code_changes: CodeChange[];
  test_results: TestResult[];
  review_result: ReviewResult | null;
  approval_status: string | null;
  git_diff: string | null;
  commit_hash: string | null;
  pull_request_url: string | null;
  final_report: string | null;
  errors: string[];
  execution_logs: string[];
  node_durations: Record<string, number>;
  total_duration_seconds: number;
}

export interface TaskListItem {
  task_id: string;
  description: string;
  status: string;
  created_at: string | null;
  pull_request_url: string | null;
}

export interface TaskEvent {
  type: string;
  timestamp: number;
  agent?: string;
  duration_seconds?: number;
  status?: string;
  decision?: string;
  error?: string;
}

export const AGENT_PIPELINE = [
  'planner',
  'explorer',
  'coder',
  'tester',
  'debugger',
  'reviewer',
  'human_approval',
  'git_manager',
  'github_pr',
  'finalize_report',
] as const;

export const AGENT_LABELS: Record<string, string> = {
  planner: 'Planner',
  explorer: 'Repository Explorer',
  coder: 'Coding Agent',
  tester: 'Testing',
  debugger: 'Debugger',
  reviewer: 'Code Review',
  human_approval: 'Human Approval',
  git_manager: 'Git Manager',
  github_pr: 'GitHub PR',
  finalize_report: 'Final Report',
};
