"use client";

import { useRunUiStore } from "@/stores/run-ui-store";

interface RoomsTopbarProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
  activeRoom?: string | null;
  onRoomSelect?: (room: RoomKey | null) => void;
}

const ROOMS = [
  { key: "library", label: "Library", icon: "\u{1F4DA}" },
  { key: "documents", label: "Documents", icon: "\u{1F4C4}" },
  { key: "decisions", label: "Decisions", icon: "✅" },
  { key: "memory", label: "Memory", icon: "\u{1F9E0}" },
  { key: "runs", label: "Runs", icon: "⚡" },
  { key: "tasks", label: "Tasks", icon: "\u{1F4CB}" },
  { key: "sandbox", label: "Sandbox", icon: "\u{1F52C}" },
  { key: "settings", label: "Settings", icon: "⚙️" },
] as const;

export type RoomKey = (typeof ROOMS)[number]["key"];

export function RoomsTopbar({
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
      className={className}
      style={{
        height: 48,
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        gap: 4,
        background: "rgba(255, 255, 255, 0.7)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
        fontSize: 13,
      }}
    >
      <span
        style={{
          fontWeight: 600,
          color: "var(--v2-text-primary)",
          marginRight: 16,
        }}
      >
        Workspace
      </span>
      {ROOMS.map((room) => (
        <button
          key={room.key}
          title={room.label}
          aria-label={room.label}
          onClick={() =>
            onRoomSelect?.(activeRoom === room.key ? null : room.key)
          }
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 32,
            height: 32,
            borderRadius: 8,
            border:
              activeRoom === room.key
                ? "1px solid var(--v2-accent-purple-300)"
                : "none",
            background:
              activeRoom === room.key
                ? "var(--v2-accent-purple-100)"
                : "transparent",
            cursor: "pointer",
            fontSize: 14,
            transition: "background 150ms cubic-bezier(0.16, 1, 0.3, 1)",
          }}
          onMouseEnter={(e) => {
            if (activeRoom !== room.key) {
              e.currentTarget.style.background = "rgba(20, 20, 30, 0.06)";
            }
          }}
          onMouseLeave={(e) => {
            if (activeRoom !== room.key) {
              e.currentTarget.style.background = "transparent";
            }
          }}
        >
          {room.icon}
          {room.key === "runs" && activeRunId ? (
            <span
              data-testid="runs-active-dot"
              style={{
                position: "absolute",
                top: 5,
                right: 5,
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "var(--v2-accent-purple-700)",
                boxShadow: "0 0 0 2px rgba(255,255,255,0.9)",
              }}
            />
          ) : null}
          {room.key === "runs" && !activeRunId && completedCount > 0 ? (
            <span
              data-testid="runs-completed-badge"
              style={{
                position: "absolute",
                top: 2,
                right: 2,
                minWidth: 14,
                height: 14,
                borderRadius: 7,
                padding: "0 3px",
                background: "var(--v2-status-success-deep)",
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
      ))}
    </div>
  );
}
