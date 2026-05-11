"use client";

import { use, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar, type RoomKey } from "./components/RoomsTopbar";
import { AutoCompactToast } from "./components/AutoCompactToast";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { DocumentsDrawer } from "./components/rooms/DocumentsDrawer";
import { RunsDrawer } from "./components/rooms/RunsDrawer";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { useChatStream } from "@/hooks/useChatStream";

const SETTINGS_ROOMS = new Set<string>([
  "decisions",
  "memory",
  "sandbox",
  "settings",
]);

type SettingsTab = "memory" | "decisions" | "sandbox" | "settings";

export default function V2Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [activeRoom, setActiveRoom] = useState<RoomKey | null>(null);
  const [compactToastVisible, setCompactToastVisible] = useState(false);

  // Subscribe to workspace SSE events
  useChatStream(id);

  // Map topbar room selection to panels
  const settingsOpen = activeRoom != null && SETTINGS_ROOMS.has(activeRoom);
  const settingsTab: SettingsTab =
    settingsOpen && SETTINGS_ROOMS.has(activeRoom!)
      ? (activeRoom as SettingsTab)
      : "memory";

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

        {/* Settings page also covers decisions, memory, sandbox */}
        <SettingsPage
          workspaceId={id}
          open={settingsOpen}
          defaultTab={settingsTab}
          onClose={() => setActiveRoom(null)}
        />
      </div>

      {/* Auto-compact toast */}
      <AutoCompactToast
        workspaceId={id}
        visible={compactToastVisible}
        onDismiss={() => setCompactToastVisible(false)}
      />
    </div>
  );
}
