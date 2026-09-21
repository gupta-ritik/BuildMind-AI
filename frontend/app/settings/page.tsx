'use client';

import { useEffect, useState } from 'react';
import { getPublicSettings } from '@/lib/api';

export default function SettingsPage() {
  const [settings, setSettings] = useState<Awaited<ReturnType<typeof getPublicSettings>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPublicSettings()
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page-shell mx-auto max-w-3xl p-5 sm:p-8">
      <p className="eyebrow">Workspace configuration</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Settings</h1>

      {error && <p className="text-danger text-sm">{error}</p>}

      {settings && (
        <div className="surface mt-8 overflow-hidden rounded-2xl divide-y divide-border">
          <Row label="LLM Provider" value={settings.llm_provider} />
          <Row label="Model" value={settings.llm_model} />
          <Row label="Max debug retries" value={String(settings.max_debug_retries)} />
          <Row label="Max review cycles" value={String(settings.max_review_cycles)} />
          <Row
            label="Docker sandbox"
            value={settings.use_docker_sandbox ? 'Enabled (falls back to subprocess if unreachable)' : 'Disabled'}
          />
          <Row
            label="GitHub integration"
            value={settings.github_configured ? 'Token configured' : 'Not configured — PR creation will be skipped'}
          />
        </div>
      )}

      <p className="text-xs text-muted mt-4">
        These are read-only, non-secret values from the backend&apos;s environment configuration
        (<code className="mono">backend/.env</code>). Change them there and restart the backend.
      </p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 px-5 py-4 text-sm sm:flex-row sm:items-center sm:justify-between">
      <span className="text-muted">{label}</span>
      <span className="mono text-cyan-100">{value}</span>
    </div>
  );
}
