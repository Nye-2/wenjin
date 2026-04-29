"use client";

import { useState } from "react";
import {
  BookOpen,
  FileText,
  History,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

interface KnowledgeRailProps {
  workspaceId: string;
  className?: string;
}

type RailTab = "papers" | "artifacts" | "activity" | "memory";

const tabs: { id: RailTab; label: string; icon: React.ElementType }[] = [
  { id: "papers", label: "文献", icon: BookOpen },
  { id: "artifacts", label: "产物", icon: FileText },
  { id: "activity", label: "历史", icon: History },
  { id: "memory", label: "记忆", icon: BrainCircuit },
];

export function KnowledgeRail({ workspaceId, className }: KnowledgeRailProps) {
  const [activeTab, setActiveTab] = useState<RailTab>("papers");
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <div
        className={cn(
          "flex h-full w-12 flex-col items-center border-r border-[var(--border-default)] bg-[var(--bg-elevated)] py-3",
          className
        )}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setCollapsed(false);
              }}
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
    <div
      className={cn(
        "flex h-full w-60 flex-col border-r border-[var(--border-default)] bg-[var(--bg-elevated)]",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          工作空间资产
        </span>
        <button
          onClick={() => setCollapsed(true)}
          className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-muted)]"
          title="收起"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="relative flex border-b border-[var(--border-subtle)]">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function RailTabContent({ tab, workspaceId }: { tab: RailTab; workspaceId: string }) {
  // TODO: 接入实际数据
  return (
    <div className="flex flex-col gap-1">
      <div className="rounded-lg px-2 py-3 text-center text-xs text-[var(--text-muted)]">
        {tab === "papers" && "文献库内容将在此展示"}
        {tab === "artifacts" && "历史产物将在此展示"}
        {tab === "activity" && "Activity 时间线将在此展示"}
        {tab === "memory" && "Workspace 记忆将在此展示"}
      </div>
    </div>
  );
}
