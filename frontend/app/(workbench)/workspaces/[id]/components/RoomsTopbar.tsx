"use client";

import {
  BookOpen,
  CheckSquare,
  FileText,
  ListTodo,
  MemoryStick,
  Settings,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useRunUiStore } from "@/stores/run-ui-store";

interface RoomsTopbarProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
  activeRoom?: string | null;
  onRoomSelect?: (room: RoomKey | null) => void;
}

const ROOMS = [
  { key: "library", label: "文献", icon: BookOpen },
  { key: "documents", label: "文档", icon: FileText },
  { key: "decisions", label: "决策", icon: CheckSquare },
  { key: "memory", label: "记忆", icon: MemoryStick },
  { key: "runs", label: "运行", icon: Zap },
  { key: "tasks", label: "任务", icon: ListTodo },
  { key: "settings", label: "设置", icon: Settings },
] as const satisfies ReadonlyArray<{
  key: string;
  label: string;
  icon: LucideIcon;
}>;

export type RoomKey = (typeof ROOMS)[number]["key"];

export function RoomsTopbar({
  workspaceId,
  className,
  "data-testid": testId,
  activeRoom,
  onRoomSelect,
}: RoomsTopbarProps) {
  const activeRunId = useRunUiStore((state) => state.activeRunId);
  const completedCount = useRunUiStore((state) => state.completedRunIds.size);
  return (
    <div
      data-testid={testId}
      className={className ? `wjn-topbar ${className}` : "wjn-topbar"}
      style={{
        minHeight: 46,
        display: "flex",
        alignItems: "center",
        padding: "7px 16px",
        gap: 10,
        fontSize: 13,
      }}
    >
      <div className="flex min-w-[120px] items-center gap-2">
        <span
          style={{
            fontWeight: 700,
            color: "var(--wjn-text)",
          }}
        >
          Workspace
        </span>
        <span
          title={workspaceId}
          className="wjn-tabular hidden rounded border border-[var(--wjn-line)] bg-white px-1.5 py-0.5 text-[10px] text-[var(--wjn-text-muted)] md:inline-flex"
        >
          {workspaceId.slice(0, 6)}
        </span>
      </div>
      <div
        aria-hidden="true"
        style={{
          width: 1,
          height: 22,
          background: "var(--wjn-line)",
        }}
      />
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {ROOMS.map((room) => {
          const Icon = room.icon;
          const active = activeRoom === room.key;
          return (
            <button
              key={room.key}
              title={room.label}
              aria-label={room.label}
              data-active={active}
              className="wjn-nav-chip"
              onClick={() =>
                onRoomSelect?.(active ? null : room.key as RoomKey)
              }
              style={{
                position: "relative",
                cursor: "pointer",
                flex: "0 0 auto",
              }}
            >
              <Icon size={16} strokeWidth={2} aria-hidden="true" />
              <span className="hidden sm:inline">{room.label}</span>
              {room.key === "runs" && activeRunId ? (
                <span
                  data-testid="runs-active-dot"
                  style={{
                    position: "absolute",
                    top: 4,
                    right: 4,
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: "var(--wjn-accent)",
                    boxShadow: "0 0 0 2px rgba(255,255,255,0.95)",
                  }}
                />
              ) : null}
              {room.key === "runs" && !activeRunId && completedCount > 0 ? (
                <span
                  data-testid="runs-completed-badge"
                  className="wjn-tabular"
                  style={{
                    position: "absolute",
                    top: 1,
                    right: 1,
                    minWidth: 14,
                    height: 14,
                    borderRadius: 7,
                    padding: "0 3px",
                    background: "var(--wjn-success)",
                    color: "#fff",
                    fontSize: 9,
                    lineHeight: "14px",
                    fontWeight: 700,
                  }}
                >
                  {Math.min(completedCount, 9)}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <span className="hidden shrink-0 text-[11px] font-medium text-[var(--wjn-text-muted)] lg:inline">
        证据 · 审阅 · 运行记录
      </span>
    </div>
  );
}
