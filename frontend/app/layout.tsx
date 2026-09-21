import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'BuildMind AI',
  description: 'AI-powered software engineering workspace',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell min-h-screen md:flex">
          <aside className="sidebar flex w-full shrink-0 flex-col px-4 py-5 md:min-h-screen md:w-64">
            <Link href="/dashboard" className="mb-10 flex items-center gap-3 px-2">
              <span className="brand-mark">BM</span>
              <span>
                <span className="block text-sm font-bold tracking-[0.16em]">BUILDMIND AI</span>
                <span className="mono block text-[10px] text-muted">AI SOFTWARE WORKSPACE</span>
              </span>
            </Link>
            <nav className="flex gap-1 overflow-x-auto md:flex-col">
              <Link href="/dashboard" className="nav-link whitespace-nowrap rounded-lg px-3 py-2.5 text-sm">Dashboard</Link>
              <Link href="/projects" className="nav-link whitespace-nowrap rounded-lg px-3 py-2.5 text-sm">Projects</Link>
              <Link href="/tasks/new" className="nav-link whitespace-nowrap rounded-lg px-3 py-2.5 text-sm">New task</Link>
              <Link href="/settings" className="nav-link whitespace-nowrap rounded-lg px-3 py-2.5 text-sm">Settings</Link>
            </nav>
            <div className="mt-auto hidden rounded-xl border border-border bg-white/[0.03] p-3 md:block">
              <p className="eyebrow">System status</p>
              <p className="mt-2 flex items-center gap-2 text-xs text-muted"><span className="h-2 w-2 rounded-full bg-success" /> API connected</p>
            </div>
          </aside>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
