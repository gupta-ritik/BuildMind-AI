'use client';

export default function DiffViewer({ diff }: { diff: string }) {
  if (!diff || diff.trim().length === 0) {
    return <p className="text-muted text-sm italic">No diff yet.</p>;
  }

  const lines = diff.split('\n');

  return (
    <pre className="mono text-xs overflow-x-auto rounded border border-border bg-black/40 p-3 leading-relaxed">
      {lines.map((line, i) => {
        let className = 'text-gray-300';
        if (line.startsWith('+++') || line.startsWith('---')) {
          className = 'text-blue-300';
        } else if (line.startsWith('+')) {
          className = 'text-success bg-success/10';
        } else if (line.startsWith('-')) {
          className = 'text-danger bg-danger/10';
        } else if (line.startsWith('@@')) {
          className = 'text-purple-300';
        }
        return (
          <div key={i} className={className}>
            {line || '\u00A0'}
          </div>
        );
      })}
    </pre>
  );
}
