import dynamic from 'next/dynamic';
import { MessageSkeleton } from '@/components/ui/skeleton';

// Lazy load KnowledgePanel
export const LazyKnowledgePanel = dynamic(
  () => import('@/app/(workbench)/workspaces/[id]/components/KnowledgePanel').then(
    (mod) => mod.KnowledgePanel
  ),
  {
    loading: () => (
      <div className="h-full rounded-3xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4">
        <MessageSkeleton />
        <MessageSkeleton />
      </div>
    ),
    ssr: false,
  }
);

// Lazy load ChatPanel
export const LazyChatPanel = dynamic(
  () => import('@/app/(workbench)/workspaces/[id]/components/ChatPanel').then(
    (mod) => mod.ChatPanel
  ),
  {
    loading: () => (
      <div className="flex-1 p-4">
        <MessageSkeleton />
        <MessageSkeleton />
        <MessageSkeleton />
      </div>
    ),
    ssr: false,
  }
);

// Lazy load LiteraturePanel
export const LazyLiteraturePanel = dynamic(
  () => import('@/app/(workbench)/workspaces/[id]/components/LiteraturePanel').then(
    (mod) => mod.LiteraturePanel
  ),
  {
    loading: () => (
      <div className="w-80 p-4 border-l border-white/10 bg-white/30 dark:bg-slate-900/30">
        <MessageSkeleton />
        <MessageSkeleton />
      </div>
    ),
    ssr: false,
  }
);
