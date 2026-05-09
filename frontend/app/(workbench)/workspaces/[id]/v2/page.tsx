"use client";

import { use, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar, type RoomKey } from "./components/RoomsTopbar";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { DocumentsDrawer } from "./components/rooms/DocumentsDrawer";
import { RunsDrawer } from "./components/rooms/RunsDrawer";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";

export default function V2Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [activeRoom, setActiveRoom] = useState<RoomKey | null>(null);

  return (
    <div className="flex flex-col h-screen">
      <RoomsTopbar
        workspaceId={id}
        data-testid="rooms-topbar"
        activeRoom={activeRoom}
        onRoomSelect={setActiveRoom}
      />
      <div className="flex flex-1 min-h-0 relative">
        <ChatPanel
          workspaceId={id}
          className="w-[42%] border-r"
          data-testid="chat-panel"
        />
        <LiveWorkflowPanel
          workspaceId={id}
          className="flex-1"
          data-testid="workflow-panel"
        />

        {/* Room drawers */}
        <LibraryDrawer
          workspaceId={id}
          open={activeRoom === "library"}
          onClose={() => setActiveRoom(null)}
        />
        <DocumentsDrawer
          workspaceId={id}
          open={activeRoom === "documents"}
          onClose={() => setActiveRoom(null)}
        />
        <DecisionsDrawer
          workspaceId={id}
          open={activeRoom === "decisions"}
          onClose={() => setActiveRoom(null)}
        />
        <RunsDrawer
          workspaceId={id}
          open={activeRoom === "runs"}
          onClose={() => setActiveRoom(null)}
        />
        <TasksDrawer
          workspaceId={id}
          open={activeRoom === "tasks"}
          onClose={() => setActiveRoom(null)}
        />
        <SettingsPage
          workspaceId={id}
          open={activeRoom === "settings"}
          onClose={() => setActiveRoom(null)}
        />
      </div>
    </div>
  );
}

function DecisionsDrawer({
  workspaceId,
  open,
  onClose,
}: {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}) {
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
        boxShadow: "-8px 0 32px rgba(20, 20, 30, 0.06)",
        zIndex: 20,
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--v2-font-sans)",
        transform: open ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
      data-testid="decisions-drawer"
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "14px 16px",
          borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            fontSize: 14,
            color: "var(--v2-text-primary)",
          }}
        >
          Decisions
        </span>
        <button
          onClick={onClose}
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            fontSize: 18,
            color: "var(--v2-text-tertiary)",
          }}
        >
          ✕
        </button>
      </div>
      <div
        style={{
          padding: "16px",
          flex: 1,
          overflowY: "auto",
          color: "var(--v2-text-secondary)",
          fontSize: 13,
        }}
      >
        Decisions will be displayed here
      </div>
    </div>
  );
}
