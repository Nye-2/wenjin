"use client";

import { use, useEffect, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar, type RoomKey } from "./components/RoomsTopbar";
import { AutoCompactToast } from "./components/AutoCompactToast";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { DocumentsDrawer } from "./components/rooms/DocumentsDrawer";
import { RunsDrawer } from "./components/rooms/RunsDrawer";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { getWorkspace } from "@/lib/api/workspace";
import { authorizedFetch } from "@/lib/api/client";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-suggestions";
import type { WorkspaceFeature } from "@/lib/api/types";

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
  const [workspace, setWorkspace] = useState<{
    name: string;
    type: string;
  } | null>(null);
  const [features, setFeatures] = useState<WorkspaceFeature[]>([]);

  useEffect(() => {
    let cancelled = false;
    getWorkspace(id)
      .then(async (w) => {
        if (cancelled) return;
        setWorkspace({ name: w.name, type: w.type });
        const res = await authorizedFetch(
          `/api/capabilities?workspace_type=${encodeURIComponent(w.type)}`
        );
        if (!res.ok) {
          return;
        }
        const data = (await res.json()) as {
          items?: Array<Record<string, unknown>>;
        };
        if (cancelled) return;
        const mapped: WorkspaceFeature[] = (data.items ?? []).map((c) => ({
          id: c.id as string,
          name: (c.display_name as string) ?? (c.id as string) ?? "",
          description:
            (c.description as string) ||
            (c.intent_description as string) ||
            "",
          icon: "",
          agent: "",
          agentLabel: "",
          stages: [],
        }));
        setFeatures(mapped);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id]);

  const typeConfig = workspace
    ? WORKSPACE_TYPE_CONFIG[workspace.type as keyof typeof WORKSPACE_TYPE_CONFIG]
    : null;

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
          workspaceName={workspace?.name}
          typeConfig={typeConfig ?? undefined}
          className="w-[42%] border-r"
          data-testid="chat-panel"
        />
        <LiveWorkflowPanel
          workspaceId={id}
          typeConfig={typeConfig ?? undefined}
          features={features}
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
