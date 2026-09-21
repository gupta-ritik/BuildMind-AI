const COLORS: Record<string, string> = {
  planning: 'bg-blue-500/20 text-blue-300',
  exploring: 'bg-blue-500/20 text-blue-300',
  coding: 'bg-blue-500/20 text-blue-300',
  testing: 'bg-warn/20 text-warn',
  debugging: 'bg-warn/20 text-warn',
  reviewing: 'bg-purple-500/20 text-purple-300',
  awaiting_approval: 'bg-warn/20 text-warn',
  approved: 'bg-success/20 text-success',
  rejected: 'bg-danger/20 text-danger',
  creating_pr: 'bg-blue-500/20 text-blue-300',
  completed: 'bg-success/20 text-success',
  failed: 'bg-danger/20 text-danger',
  pending: 'bg-muted/20 text-muted',
  changes_requested: 'bg-warn/20 text-warn',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] || 'bg-muted/20 text-muted';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}
