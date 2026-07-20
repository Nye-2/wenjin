"use client";

import { X } from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import {
  listTasks,
  createTask,
  deleteTask,
  updateTaskStatus,
  type WorkspaceTask,
} from "@/lib/api/v2/tasks";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";

interface TasksDrawerProps {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<WorkspaceTask["status"], string> = {
  pending: "var(--wjn-text-secondary)",
  in_progress: "var(--wjn-blue)",
  completed: "var(--wjn-success)",
  cancelled: "var(--wjn-text-muted)",
};

const STATUS_BG: Record<WorkspaceTask["status"], string> = {
  pending: "var(--wjn-change-neutral-soft)",
  in_progress: "var(--wjn-accent-soft)",
  completed: "var(--wjn-success-soft)",
  cancelled: "var(--wjn-change-neutral-soft)",
};

const STATUS_LABELS: Record<WorkspaceTask["status"], string> = {
  pending: "待处理",
  in_progress: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

const STATUS_CYCLE: WorkspaceTask["status"][] = [
  "pending",
  "in_progress",
  "completed",
];

function nextStatus(
  current: WorkspaceTask["status"],
): WorkspaceTask["status"] {
  const idx = STATUS_CYCLE.indexOf(current);
  if (idx === -1 || idx === STATUS_CYCLE.length - 1) return STATUS_CYCLE[0];
  return STATUS_CYCLE[idx + 1];
}

export function TasksDrawer({
  workspaceId,
  open,
  onClose,
}: TasksDrawerProps) {
  const [items, setItems] = useState<WorkspaceTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.tasks ?? 0,
  );

  useEffect(() => {
    if (open) setVisible(true);
  }, [open]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTasks(workspaceId);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务加载失败");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems, refreshCounter]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  async function handleAdd() {
    if (!newTitle.trim()) return;
    try {
      const task = await createTask(workspaceId, newTitle.trim());
      setItems((prev) => [task, ...prev]);
      setNewTitle("");
      setShowAddForm(false);
    } catch {
      setError("任务创建失败");
    }
  }

  async function handleDelete(taskId: string) {
    try {
      await deleteTask(workspaceId, taskId);
      setItems((prev) => prev.filter((item) => item.id !== taskId));
    } catch {
      setError("任务删除失败");
    }
  }

  async function handleToggleStatus(task: WorkspaceTask) {
    const next = nextStatus(task.status);
    try {
      await updateTaskStatus(workspaceId, task.id, next);
      setItems((prev) =>
        prev.map((item) =>
          item.id === task.id ? { ...item, status: next } : item,
        ),
      );
    } catch {
      setError("任务状态更新失败");
    }
  }

  const filtered = search
    ? items.filter((item) =>
        item.title.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

  if (!open) return null;

  return (
    <div
      style={{
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: "min(420px, 100%)",
        background: "var(--wjn-surface)",
        borderLeft: "1px solid var(--wjn-line)",
        boxShadow: "var(--wjn-shadow-md)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 13,
      }}
      data-testid="tasks-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="任务"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid var(--wjn-line)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontWeight: 600,
              fontSize: 15,
              color: "var(--wjn-text)",
            }}
          >
            任务
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            type="button"
            onClick={() => setShowAddForm(!showAddForm)}
            data-testid="add-task-btn"
            aria-label={showAddForm ? "收起新增任务" : "新增任务"}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 18,
              color: "var(--wjn-blue)",
              lineHeight: 1,
              padding: 4,
            }}
          >
            +
          </button>
          <button
            type="button"
            onClick={handleClose}
            data-testid="drawer-close"
            aria-label="关闭任务"
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 16,
              color: "var(--wjn-text-muted)",
              lineHeight: 1,
              padding: 4,
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Add task form */}
      {showAddForm && (
        <div
          style={{
            padding: "12px 16px",
            borderBottom: "1px solid var(--wjn-line)",
            display: "flex",
            gap: 8,
          }}
          data-testid="add-task-form"
        >
          <input
            type="text"
            placeholder="任务标题..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            data-testid="add-task-input"
            style={{
              flex: 1,
              padding: "8px 12px",
              borderRadius: "var(--wjn-radius-md)",
              border: "1px solid var(--wjn-line)",
              background: "var(--wjn-surface-raised)",
              fontSize: 13,
              fontFamily: "var(--wjn-font-sans)",
              color: "var(--wjn-text)",
              outline: "none",
            }}
          />
          <button
            type="button"
            onClick={handleAdd}
            data-testid="add-task-submit"
            style={{
              border: "none",
              background: "var(--wjn-blue)",
              color: "white",
              borderRadius: "var(--wjn-radius-md)",
              padding: "8px 16px",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "var(--wjn-font-sans)",
              fontWeight: 500,
            }}
          >
            添加
          </button>
        </div>
      )}

      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="搜索任务"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="drawer-search"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px 12px",
            borderRadius: "var(--wjn-radius-md)",
            border: "1px solid var(--wjn-line)",
            background: "var(--wjn-surface-raised)",
            fontSize: 13,
            fontFamily: "var(--wjn-font-sans)",
            color: "var(--wjn-text)",
            outline: "none",
          }}
        />
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "0 16px 16px",
        }}
      >
        {loading && (
          <div
            style={{
              textAlign: "center",
              padding: "40px 0",
              color: "var(--wjn-text-muted)",
            }}
            data-testid="drawer-loading"
          >
            正在加载任务...
          </div>
        )}

        {error && (
          <div
            style={{
              textAlign: "center",
              padding: "16px",
              color: "var(--wjn-error)",
            }}
            data-testid="drawer-error"
          >
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "40px 0",
              color: "var(--wjn-text-muted)",
            }}
            data-testid="drawer-empty"
          >
            {search ? "没有匹配的任务" : "暂无任务"}
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="task-item"
              style={{
                background: "var(--wjn-surface-raised)",
                borderRadius: "var(--wjn-radius-md)",
                border: "1px solid var(--wjn-change-neutral-soft)",
                padding: 12,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      color: "var(--wjn-text)",
                      marginBottom: 4,
                      textDecoration:
                        item.status === "completed" ? "line-through" : "none",
                    }}
                  >
                    {item.title}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => handleToggleStatus(item)}
                      data-testid="task-status-toggle"
                      aria-label={`切换任务状态：${item.title}`}
                      style={{
                        display: "inline-block",
                        padding: "2px 10px",
                        borderRadius: 10,
                        fontSize: 11,
                        fontWeight: 500,
                        color: STATUS_COLORS[item.status],
                        background: STATUS_BG[item.status],
                        border: "none",
                        cursor: "pointer",
                        fontFamily: "var(--wjn-font-sans)",
                      }}
                    >
                      {STATUS_LABELS[item.status]}
                    </button>
                    {item.priority != null && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "var(--wjn-text-muted)",
                        }}
                      >
                        P{item.priority}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(item.id)}
                  data-testid="item-delete"
                  aria-label={`删除 ${item.title}`}
                  style={{
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    color: "var(--wjn-text-muted)",
                    fontSize: 12,
                    padding: "2px 4px",
                    flexShrink: 0,
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
