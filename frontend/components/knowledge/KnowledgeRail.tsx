"use client";

import { useEffect, useState } from "react";
import {
  BookOpen,
  FileText,
  History,
  BrainCircuit,
  ChevronRight,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getWorkspaceMemory, type MemoryEntry } from "@/lib/api";
import { useWorkspaceStore } from "@/stores/workspace";

// =============================================================================
// Types & Constants
// =============================================================================

export type RailTab = "references" | "artifacts" | "activity" | "memory";

export const RAIL_TABS: {
  id: RailTab;
  label: string;
  icon: React.ElementType;
}[] = [
  { id: "references", label: "文献", icon: BookOpen },
  { id: "artifacts", label: "产物", icon: FileText },
  { id: "activity", label: "历史", icon: History },
  { id: "memory", label: "记忆", icon: BrainCircuit },
];

// =============================================================================
// KnowledgeRailBar — Pure icon bar, no content
// =============================================================================

export interface KnowledgeRailBarProps {
  activeTab: RailTab;
  onTabChange: (tab: RailTab) => void;
  className?: string;
}

export function KnowledgeRailBar({
  activeTab,
  onTabChange,
  className,
}: KnowledgeRailBarProps) {
  return (
    <div className={cn("flex h-full w-12 flex-col items-center py-3", className)}>
      {RAIL_TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
              isActive
                ? "bg-[var(--brand-navy)]/10 text-[var(--brand-navy)]"
                : "text-[var(--text-muted)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-secondary)]"
            )}
            title={tab.label}
          >
            <Icon className="h-4 w-4" />
            {isActive && (
              <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r-full bg-[var(--brand-navy)]" />
            )}
          </button>
        );
      })}
    </div>
  );
}

// =============================================================================
// KnowledgeRailContent — Content panel with tab switching
// =============================================================================

export interface KnowledgeRailContentProps {
  activeTab: RailTab;
  onTabChange: (tab: RailTab) => void;
  onClose?: () => void;
  workspaceId: string;
  className?: string;
}

export function KnowledgeRailContent({
  activeTab,
  onTabChange,
  onClose,
  workspaceId,
  className,
}: KnowledgeRailContentProps) {
  return (
    <div
      className={cn(
        "flex h-full w-60 flex-col bg-[var(--bg-elevated)]",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          工作空间资产
        </span>
        {onClose && (
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-muted)]"
            title="关闭"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="relative flex border-b border-[var(--border-subtle)]">
        {RAIL_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                "relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors",
                isActive
                  ? "text-[var(--brand-navy)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
              {isActive && (
                <span className="absolute bottom-0 h-0.5 w-6 rounded-full bg-[var(--brand-navy)]" />
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 px-2 py-2">
        <RailTabContent tab={activeTab} workspaceId={workspaceId} />
      </ScrollArea>
    </div>
  );
}

// =============================================================================
// RailTabContent — Tab content renderer (internal)
// =============================================================================

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
}

function EmptyRailState({ children }: { children: string }) {
  return (
    <div className="rounded-lg px-2 py-3 text-center text-xs leading-5 text-[var(--text-muted)]">
      {children}
    </div>
  );
}

function RailTabContent({
  tab,
  workspaceId,
}: {
  tab: RailTab;
  workspaceId: string;
}) {
  const references = useWorkspaceStore((state) => state.references);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const activities = useWorkspaceStore((state) => state.activities);
  const fetchReferences = useWorkspaceStore((state) => state.fetchReferences);
  const [memoryItems, setMemoryItems] = useState<MemoryEntry[]>([]);
  const [memoryError, setMemoryError] = useState<string | null>(null);

  useEffect(() => {
    if (tab === "references" && workspaceId && references.length === 0) {
      void fetchReferences(workspaceId);
    }
  }, [fetchReferences, references.length, tab, workspaceId]);

  useEffect(() => {
    if (tab !== "memory" || !workspaceId) {
      return;
    }
    let cancelled = false;
    void getWorkspaceMemory(workspaceId)
      .then((response) => {
        if (!cancelled) {
          setMemoryError(null);
          setMemoryItems(response.items ?? []);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setMemoryItems([]);
          setMemoryError(
            error instanceof Error ? error.message : "记忆加载失败"
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tab, workspaceId]);

  if (tab === "references") {
    if (references.length === 0) {
      return (
        <EmptyRailState>
          还没有文献。上传或检索后会在这里显示。
        </EmptyRailState>
      );
    }
    return (
      <div className="flex flex-col gap-1.5">
        {references.slice(0, 10).map((reference) => (
          <div
            key={reference.id}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-2"
          >
            <p className="line-clamp-2 text-xs font-medium leading-5 text-[var(--text-primary)]">
              {reference.title || "未命名文献"}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {[reference.year, reference.venue].filter(Boolean).join(" · ") ||
                "暂无来源信息"}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (tab === "artifacts") {
    if (artifacts.length === 0) {
      return (
        <EmptyRailState>
          还没有产物。Compute 完成后会在这里沉淀。
        </EmptyRailState>
      );
    }
    return (
      <div className="flex flex-col gap-1.5">
        {artifacts.slice(0, 10).map((artifact) => (
          <div
            key={artifact.id}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-2"
          >
            <p className="line-clamp-2 text-xs font-medium leading-5 text-[var(--text-primary)]">
              {artifact.title || artifact.type}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {artifact.type}{" "}
              {formatDate(artifact.created_at)
                ? `· ${formatDate(artifact.created_at)}`
                : ""}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (tab === "activity") {
    if (activities.length === 0) {
      return <EmptyRailState>暂无活动记录。</EmptyRailState>;
    }
    return (
      <div className="flex flex-col gap-1.5">
        {activities.slice(0, 12).map((activity) => (
          <div
            key={activity.id}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-2"
          >
            <p className="line-clamp-2 text-xs font-medium leading-5 text-[var(--text-primary)]">
              {activity.title || activity.summary || "Workspace activity"}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {activity.kind}{" "}
              {formatDate(activity.occurred_at)
                ? `· ${formatDate(activity.occurred_at)}`
                : ""}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (memoryError) {
    return <EmptyRailState>{memoryError}</EmptyRailState>;
  }
  if (memoryItems.length === 0) {
    return (
      <EmptyRailState>
        暂无长期记忆。有效偏好和稳定事实会在对话后自动沉淀。
      </EmptyRailState>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      {memoryItems.slice(0, 12).map((item, index) => (
        <div
          key={`${item.category}-${index}`}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-2"
        >
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--brand-teal)]">
            {item.category}
          </p>
          <p className="mt-1 line-clamp-3 text-xs leading-5 text-[var(--text-primary)]">
            {item.content}
          </p>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            置信度 {Math.round(item.confidence * 100)}%
          </p>
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// KnowledgeRail — Composite component (for mobile drawer, backward compat)
// =============================================================================

interface KnowledgeRailProps {
  workspaceId: string;
  className?: string;
}

export function KnowledgeRail({ workspaceId, className }: KnowledgeRailProps) {
  const [activeTab, setActiveTab] = useState<RailTab>("references");
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <div
        className={cn(
          "flex h-full w-12 flex-col items-center border-r border-[var(--border-default)] bg-[var(--bg-elevated)] py-3",
          className
        )}
      >
        <KnowledgeRailBar
          activeTab={activeTab}
          onTabChange={(tab) => {
            setActiveTab(tab);
            setCollapsed(false);
          }}
        />
        <div className="flex-1" />
        <button
          onClick={() => setCollapsed(false)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)]"
          title="展开"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <KnowledgeRailContent
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onClose={() => setCollapsed(true)}
      workspaceId={workspaceId}
      className={cn("border-r border-[var(--border-default)]", className)}
    />
  );
}
