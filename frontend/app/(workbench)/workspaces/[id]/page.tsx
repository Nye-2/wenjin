"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar, type RoomKey } from "./components/RoomsTopbar";
import { AutoCompactToast } from "./components/AutoCompactToast";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { DocumentsDrawer } from "./components/rooms/DocumentsDrawer";
import { RunsDrawer } from "./components/rooms/RunsDrawer";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { SurfaceSwitch } from "./components/SurfaceSwitch";
import { getWorkspace } from "@/lib/api/workspace";
import { authorizedFetch } from "@/lib/api/client";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-suggestions";
import type { WorkspaceCapability } from "@/lib/api/types";

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
  const searchParams = useSearchParams();
  const roomSeed = readRoomRouteSeed(searchParams);
  const [roomState, setRoomState] = useState<{
    routeRoom: RoomKey | null;
    activeRoom: RoomKey | null;
  }>(() => ({
    routeRoom: roomSeed.room,
    activeRoom: roomSeed.room,
  }));
  const activeRoom =
    roomState.routeRoom === roomSeed.room ? roomState.activeRoom : roomSeed.room;
  const setActiveRoom = useCallback(
    (room: RoomKey | null) => {
      setRoomState({
        routeRoom: roomSeed.room,
        activeRoom: room,
      });
    },
    [roomSeed.room],
  );
  const [compactToastVisible, setCompactToastVisible] = useState(false);
  const [workspace, setWorkspace] = useState<{
    name: string;
    type: string;
  } | null>(null);
  const [features, setFeatures] = useState<WorkspaceCapability[]>([]);

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
        const mapped: WorkspaceCapability[] = (data.items ?? []).map((c) => ({
          id: c.id as string,
          name: (c.display_name as string) ?? (c.id as string) ?? "",
          description:
            (c.description as string) ||
            (c.intent_description as string) ||
            "",
          icon: ((c.ui_meta as Record<string, unknown> | undefined)?.icon as string) ?? "",
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
    <div className="flex h-full min-h-0 flex-col">
      <SurfaceSwitch workspaceId={id} active="workbench" />
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
          features={features}
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
          initialQuery={activeRoom === "library" ? roomSeed.query : null}
          focusItemId={activeRoom === "library" ? roomSeed.itemId : null}
          onClose={() => setActiveRoom(null)}
        />
        <DocumentsDrawer
          workspaceId={id}
          open={activeRoom === "documents"}
          initialQuery={activeRoom === "documents" ? roomSeed.query : null}
          focusItemId={activeRoom === "documents" ? roomSeed.itemId : null}
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

function readRequestedRoom(
  searchParams: ReturnType<typeof useSearchParams>,
): RoomKey | null {
  const value = searchParams?.get("room")?.trim().toLowerCase();
  if (
    value === "library" ||
    value === "documents" ||
    value === "decisions" ||
    value === "memory" ||
    value === "runs" ||
    value === "tasks" ||
    value === "sandbox" ||
    value === "settings"
  ) {
    return value;
  }
  return null;
}

function readRoomRouteSeed(
  searchParams: ReturnType<typeof useSearchParams>,
): { room: RoomKey | null; itemId: string | null; query: string | null } {
  return {
    room: readRequestedRoom(searchParams),
    itemId: readTrimmedParam(searchParams, "item_id") ?? readTrimmedParam(searchParams, "artifact_id"),
    query: readTrimmedParam(searchParams, "query"),
  };
}

function readTrimmedParam(
  searchParams: ReturnType<typeof useSearchParams>,
  key: string,
): string | null {
  const value = searchParams?.get(key);
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}
