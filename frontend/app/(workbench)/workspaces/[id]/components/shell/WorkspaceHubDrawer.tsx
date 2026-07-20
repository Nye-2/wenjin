"use client";

import { useEffect } from "react";
import {
  BookOpen,
  CheckCircle2,
  History,
  ListTodo,
  Settings,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CountBadge } from "@/components/ui/count-badge";
import { IconButton } from "@/components/ui/icon-button";

export type WorkspaceHubRoomKey =
  | "library"
  | "decisions"
  | "missions"
  | "tasks"
  | "settings";

type WorkspaceHubRoom = {
  key: WorkspaceHubRoomKey;
  label: string;
  description: string;
  icon: LucideIcon;
  countKind?: "review" | "missions";
};

export const WORKSPACE_HUB_ROOMS: readonly WorkspaceHubRoom[] = [
  {
    key: "library",
    label: "文献资料",
    description: "论文、引用来源与检索材料",
    icon: BookOpen,
  },
  {
    key: "decisions",
    label: "确认与决策",
    description: "待确认成果、关键判断与采纳记录",
    icon: CheckCircle2,
    countKind: "review",
  },
  {
    key: "missions",
    label: "研究任务记录",
    description: "历史研究任务、过程记录与成果摘要",
    icon: History,
    countKind: "missions",
  },
  {
    key: "tasks",
    label: "任务清单",
    description: "后续事项、计划节点与待推进工作",
    icon: ListTodo,
  },
  {
    key: "settings",
    label: "工作设置",
    description: "空间配置、成员偏好与输出规范",
    icon: Settings,
  },
];

export function WorkspaceHubDrawer({
  open,
  activeRoom,
  pendingReviewCount,
  completedRunCount,
  onClose,
  onRoomSelect,
}: {
  open: boolean;
  activeRoom: WorkspaceHubRoomKey | null;
  pendingReviewCount: number;
  completedRunCount: number;
  onClose: () => void;
  onRoomSelect: (room: WorkspaceHubRoomKey) => void;
}) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div
      data-testid="workspace-hub-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      className="fixed inset-0 z-50 flex justify-end bg-[rgba(15,23,42,0.18)] backdrop-blur-[2px]"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="资料库"
        onMouseDown={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-[384px] flex-col border-l border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-[var(--wjn-shadow-lg)]"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-[-0.01em] text-[var(--wjn-text)]">
              资料库
            </h2>
            <p className="mt-1 text-xs text-[var(--wjn-text-muted)]">
              文献、成果、记录与设置
            </p>
          </div>
          <IconButton label="关闭资料库" onClick={onClose}>
            <X className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
          {WORKSPACE_HUB_ROOMS.map((room) => {
            const Icon = room.icon;
            const count = room.countKind === "review"
              ? pendingReviewCount
              : room.countKind === "missions"
                ? completedRunCount
                : 0;
            const tone = room.countKind === "review" ? "review" : "success";
            const ariaLabel = count > 0
              ? `${room.label}，${count} ${room.countKind === "review" ? "项待确认" : "项新完成"}`
              : room.label;
            const active = activeRoom === room.key;

            return (
              <button
                key={room.key}
                type="button"
                aria-label={ariaLabel}
                aria-current={active ? "page" : undefined}
                onClick={() => {
                  onRoomSelect(room.key);
                  onClose();
                }}
                className={[
                  "group flex w-full items-center gap-3 rounded-[var(--wjn-radius-lg)] border px-3 py-3 text-left transition-colors",
                  active
                    ? "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)]"
                    : "border-transparent hover:border-[var(--wjn-line)] hover:bg-[var(--wjn-surface-subtle)]",
                ].join(" ")}
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[var(--wjn-line)] bg-white text-[var(--wjn-blue)] shadow-[var(--wjn-shadow-sm)]">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-semibold text-[var(--wjn-text)]">
                    {room.label}
                    <CountBadge count={count} tone={tone} />
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-[var(--wjn-text-muted)]">
                    {room.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
