"use client";

import { Check, CircleDot, Clock3, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { listWorkspaceMissions } from "@/lib/api/missions";
import type { MissionSummary } from "@/lib/api/mission-types";
import { formatMissionDuration, missionStatusTone } from "@/lib/mission-view";
import { useMissionUiStore } from "@/stores/mission-ui-store";

interface MissionHistoryDrawerProps {
  workspaceId: string;
  open: boolean;
  onClose(): void;
}

export function MissionHistoryDrawer({ workspaceId, open, onClose }: MissionHistoryDrawerProps) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MissionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focusMission = useMissionUiStore((state) => state.focusMission);
  const highlightedMissionId = useMissionUiStore((state) => state.highlightedMissionId);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      listWorkspaceMissions(workspaceId, query)
        .then((missions) => {
          if (!cancelled) {
            setItems(missions);
            setError(null);
          }
        })
        .catch((reason) => {
          if (!cancelled) setError(reason instanceof Error ? reason.message : "任务记录加载失败");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, query ? 180 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, query, workspaceId]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 bg-black/15" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="absolute bottom-0 right-0 top-0 flex w-full max-w-[430px] flex-col border-l border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-[var(--wjn-shadow-lg)]" aria-label="研究任务记录">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--wjn-line)] px-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold">研究任务记录</h2>
            <p className="text-[11px] text-[var(--wjn-text-muted)]">只展示完整研究任务，不包含对话轮次。</p>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭任务记录" className="flex h-8 w-8 items-center justify-center rounded-[var(--wjn-radius)] hover:bg-[var(--wjn-surface-subtle)]"><X size={15} /></button>
        </header>
        <div className="p-4 pb-2">
          <label className="flex h-9 items-center gap-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] px-3 focus-within:border-[var(--wjn-accent-line)]">
            <Search size={14} className="text-[var(--wjn-text-muted)]" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="查找研究任务" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--wjn-text-muted)]" />
          </label>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {loading && !items.length ? <p className="py-10 text-center text-xs text-[var(--wjn-text-muted)]">正在加载…</p> : null}
          {error ? <p className="py-10 text-center text-xs text-[var(--wjn-error)]">{error}</p> : null}
          {!loading && !error && !items.length ? <div className="py-14 text-center"><Clock3 size={21} className="mx-auto text-[var(--wjn-text-muted)]" /><p className="mt-3 text-sm font-medium">还没有研究任务</p><p className="mt-1 text-xs text-[var(--wjn-text-secondary)]">在对话中描述目标，问津会在需要时创建任务。</p></div> : null}
          <div className="divide-y divide-[var(--wjn-line)]">
            {items.map((item) => {
              const tone = missionStatusTone(item.executionStatus);
              return (
                <button
                  key={item.missionId}
                  type="button"
                  onClick={() => {
                    focusMission(item.missionId, item.pendingReviewCount ? "review" : "progress");
                    onClose();
                  }}
                  className={`w-full py-4 text-left ${highlightedMissionId === item.missionId ? "bg-[var(--wjn-accent-soft)]" : "hover:bg-[var(--wjn-surface-subtle)]"}`}
                >
                  <div className="flex items-start gap-3 px-2">
                    <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${tone === "success" ? "bg-[var(--wjn-success-soft)] text-[var(--wjn-success)]" : tone === "active" ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent)]" : "bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-muted)]"}`}>{tone === "success" ? <Check size={13} /> : <CircleDot size={13} />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-[var(--wjn-text)]">{item.title}</span>
                      <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--wjn-text-muted)]">
                        <span>{item.statusLabel}</span>
                        <span>{formatMissionDuration(item.durationSeconds)}</span>
                        {item.pendingReviewCount ? <span className="text-[var(--wjn-review)]">{item.pendingReviewCount} 项待确认</span> : null}
                      </span>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </aside>
    </div>
  );
}
