"use client";

import { useEffect, useState, useCallback } from "react";
import {
  listTasks,
  createTask,
  deleteTask,
  updateTaskStatus,
  type WorkspaceTask,
} from "@/lib/api/v2/tasks";

interface TasksDrawerProps {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<WorkspaceTask["status"], string> = {
  pending: "var(--v2-text-secondary)",
  in_progress: "var(--v2-status-running)",
  completed: "var(--v2-status-success)",
  cancelled: "var(--v2-text-tertiary)",
};

const STATUS_BG: Record<WorkspaceTask["status"], string> = {
  pending: "rgba(100, 100, 120, 0.08)",
  in_progress: "rgba(139, 92, 246, 0.1)",
  completed: "rgba(34, 197, 94, 0.1)",
  cancelled: "rgba(100, 100, 120, 0.06)",
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
      setError(err instanceof Error ? err.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems]);

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
      setError("Failed to create task");
    }
  }

  async function handleDelete(taskId: string) {
    try {
      await deleteTask(workspaceId, taskId);
      setItems((prev) => prev.filter((item) => item.id !== taskId));
    } catch {
      setError("Failed to delete task");
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
      setError("Failed to update task status");
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
        width: 400,
        background: "rgba(255, 255, 255, 0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderLeft: "1px solid rgba(20, 20, 30, 0.08)",
        boxShadow: "0 8px 32px rgba(20, 20, 30, 0.08)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--v2-font-sans)",
        fontSize: 13,
      }}
      data-testid="tasks-drawer"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontWeight: 600,
              fontSize: 15,
              color: "var(--v2-text-primary)",
            }}
          >
            Tasks
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            data-testid="add-task-btn"
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 18,
              color: "var(--v2-accent-purple-700)",
              lineHeight: 1,
              padding: 4,
            }}
          >
            +
          </button>
          <button
            onClick={handleClose}
            data-testid="drawer-close"
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 16,
              color: "var(--v2-text-tertiary)",
              lineHeight: 1,
              padding: 4,
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Add task form */}
      {showAddForm && (
        <div
          style={{
            padding: "12px 16px",
            borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
            display: "flex",
            gap: 8,
          }}
          data-testid="add-task-form"
        >
          <input
            type="text"
            placeholder="Task title..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            data-testid="add-task-input"
            style={{
              flex: 1,
              padding: "8px 12px",
              borderRadius: "var(--v2-radius-md)",
              border: "1px solid rgba(20, 20, 30, 0.08)",
              background: "var(--v2-glass-bg)",
              fontSize: 13,
              fontFamily: "var(--v2-font-sans)",
              color: "var(--v2-text-primary)",
              outline: "none",
            }}
          />
          <button
            onClick={handleAdd}
            data-testid="add-task-submit"
            style={{
              border: "none",
              background: "var(--v2-accent-purple-700)",
              color: "white",
              borderRadius: "var(--v2-radius-md)",
              padding: "8px 16px",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "var(--v2-font-sans)",
              fontWeight: 500,
            }}
          >
            Add
          </button>
        </div>
      )}

      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="Search tasks..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="drawer-search"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px 12px",
            borderRadius: "var(--v2-radius-md)",
            border: "1px solid rgba(20, 20, 30, 0.08)",
            background: "var(--v2-glass-bg)",
            fontSize: 13,
            fontFamily: "var(--v2-font-sans)",
            color: "var(--v2-text-primary)",
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
              color: "var(--v2-text-tertiary)",
            }}
            data-testid="drawer-loading"
          >
            Loading tasks...
          </div>
        )}

        {error && (
          <div
            style={{
              textAlign: "center",
              padding: "16px",
              color: "var(--v2-status-error)",
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
              color: "var(--v2-text-tertiary)",
            }}
            data-testid="drawer-empty"
          >
            No tasks found
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="task-item"
              style={{
                background: "var(--v2-glass-bg)",
                borderRadius: "var(--v2-radius-md)",
                border: "1px solid rgba(20, 20, 30, 0.06)",
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
                      color: "var(--v2-text-primary)",
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
                      onClick={() => handleToggleStatus(item)}
                      data-testid="task-status-toggle"
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
                        fontFamily: "var(--v2-font-sans)",
                      }}
                    >
                      {item.status.replace("_", " ")}
                    </button>
                    {item.priority != null && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "var(--v2-text-tertiary)",
                        }}
                      >
                        P{item.priority}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(item.id)}
                  data-testid="item-delete"
                  style={{
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    color: "var(--v2-text-tertiary)",
                    fontSize: 12,
                    padding: "2px 4px",
                    flexShrink: 0,
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
