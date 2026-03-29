import Link from 'next/link';
import { FileText, SearchCheck, Sparkles, Waves } from 'lucide-react';
import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type AuthMode = 'login' | 'register';

interface AuthShellProps {
  mode: AuthMode;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}

const highlights = [
  {
    icon: SearchCheck,
    title: 'Literature Discovery',
    description: 'Search, screen, and organize evidence from one workspace.',
  },
  {
    icon: FileText,
    title: 'Structured Writing',
    description: 'Move from outline to polished draft with citation context.',
  },
  {
    icon: Sparkles,
    title: 'Execution Tracking',
    description: 'Keep all artifacts, task logs, and outputs connected.',
  },
];

export function AuthShell({ mode, title, description, children, footer }: AuthShellProps) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--bg-base)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-36 left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(15,40,71,0.18),transparent_68%)]" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(59,130,196,0.14),transparent_70%)]" />
        <div className="absolute left-0 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(196,147,74,0.09),transparent_72%)]" />
      </div>

      <div className="relative mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <aside className="hidden rounded-3xl border border-[var(--glass-border)] bg-[var(--glass-bg-elevated)] p-10 shadow-[var(--glass-shadow-elevated)] backdrop-blur-md lg:flex lg:flex-col">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--border-default)] bg-white/80 px-3 py-1 text-sm font-semibold text-[var(--accent-primary)]">
            <Waves className="h-4 w-4" />
            <span className="font-serif">观澜</span>
            <span className="text-[var(--text-muted)] text-xs font-sans">Guanlan</span>
          </div>

          <div className="mt-8 space-y-4">
            <h2 className="text-4xl font-semibold tracking-tight text-[var(--text-primary)]">
              观水必观其澜。<br />立潮头处，与智同行。
            </h2>
            <p className="text-base leading-relaxed text-[var(--text-secondary)]">
              One workspace for literature search, structured drafting, and artifact management.
            </p>
          </div>

          <div className="mt-10 space-y-4">
            {highlights.map((item) => (
              <div
                key={item.title}
                className="rounded-2xl border border-[var(--border-subtle)] bg-white/70 px-4 py-3"
              >
                <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                  <item.icon className="h-4 w-4 text-[var(--accent-secondary)]" />
                  {item.title}
                </div>
                <p className="text-sm text-[var(--text-secondary)]">{item.description}</p>
              </div>
            ))}
          </div>
        </aside>

        <section className="rounded-3xl border border-[var(--border-default)] bg-[var(--bg-elevated)]/95 shadow-[var(--glass-shadow-elevated)] backdrop-blur-sm">
          <header className="space-y-5 border-b border-[var(--border-subtle)] p-6 sm:p-8">
            <div className="inline-flex w-fit items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] p-1">
              <Link
                href="/login"
                className={cn(
                  'rounded-full px-4 py-1.5 text-sm font-medium transition-colors',
                  mode === 'login'
                    ? 'bg-white text-[var(--text-primary)] shadow-sm'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                )}
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className={cn(
                  'rounded-full px-4 py-1.5 text-sm font-medium transition-colors',
                  mode === 'register'
                    ? 'bg-white text-[var(--text-primary)] shadow-sm'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                )}
              >
                Create account
              </Link>
            </div>

            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-primary)]">{title}</h1>
              <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{description}</p>
            </div>
          </header>

          <div className="space-y-6 p-6 sm:p-8">
            {children}
            <div className="border-t border-[var(--border-subtle)] pt-4 text-sm text-[var(--text-secondary)]">{footer}</div>
          </div>
        </section>
      </div>
    </div>
  );
}
