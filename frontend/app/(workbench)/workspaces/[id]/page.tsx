"use client";

import {
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
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
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import type { WorkspaceCapability } from "@/lib/api/types";

const SETTINGS_ROOMS = new Set<string>([
  "decisions",
  "memory",
  "settings",
]);

type SettingsTab = "memory" | "decisions" | "settings";

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
  const splitRatio = useWorkbenchLayoutStore((state) => state.splitRatio);
  const isWorkbenchFullscreen = useWorkbenchLayoutStore(
    (state) => state.isWorkbenchFullscreen,
  );
  const setSplitRatio = useWorkbenchLayoutStore((state) => state.setSplitRatio);
  const resetSplitRatio = useWorkbenchLayoutStore(
    (state) => state.resetSplitRatio,
  );
  const splitRootRef = useRef<HTMLDivElement>(null);

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

  const handleResizePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (isWorkbenchFullscreen) {
        return;
      }
      event.preventDefault();
      const root = splitRootRef.current;
      if (!root) {
        return;
      }

      const updateRatio = (clientX: number) => {
        const rect = root.getBoundingClientRect();
        if (rect.width <= 0) {
          return;
        }
        setSplitRatio((clientX - rect.left) / rect.width);
      };

      const originalCursor = document.body.style.cursor;
      const originalUserSelect = document.body.style.userSelect;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      updateRatio(event.clientX);

      const handlePointerMove = (moveEvent: PointerEvent) => {
        updateRatio(moveEvent.clientX);
      };
      const handlePointerUp = () => {
        document.body.style.cursor = originalCursor;
        document.body.style.userSelect = originalUserSelect;
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [isWorkbenchFullscreen, setSplitRatio],
  );

  // Map topbar room selection to panels
  const settingsOpen = activeRoom != null && SETTINGS_ROOMS.has(activeRoom);
  const settingsTab: SettingsTab =
    settingsOpen && SETTINGS_ROOMS.has(activeRoom!)
      ? (activeRoom as SettingsTab)
      : "memory";

  return (
    <div className="wjn-shell-bg flex h-full min-h-0 flex-col text-[var(--wjn-text)]">
      <SurfaceSwitch workspaceId={id} active="workbench" />
      <RoomsTopbar
        workspaceId={id}
        data-testid="rooms-topbar"
        activeRoom={activeRoom}
        onRoomSelect={setActiveRoom}
      />
      <div
        ref={splitRootRef}
        className="relative flex min-h-0 flex-1"
        data-testid="workbench-split-root"
      >
        {!isWorkbenchFullscreen ? (
          <>
            <div
              data-testid="chat-region"
              style={{
                width: `${splitRatio * 100}%`,
                minWidth: 320,
                maxWidth: "72%",
                height: "100%",
                minHeight: 0,
                borderRight: "1px solid var(--wjn-line)",
              }}
            >
              <ChatPanel
                workspaceId={id}
                workspaceName={workspace?.name}
                typeConfig={typeConfig ?? undefined}
                features={features}
                className="h-full"
                data-testid="chat-panel"
              />
            </div>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="调整对话与工作台宽度"
              data-testid="workbench-resizer"
              onPointerDown={handleResizePointerDown}
              onDoubleClick={resetSplitRatio}
              title="拖拽调整宽度，双击恢复默认"
              style={{
                width: 8,
                flex: "0 0 8px",
                cursor: "col-resize",
                background:
                  "linear-gradient(90deg, rgba(15,23,42,0.02), rgba(15,23,42,0.075), rgba(15,23,42,0.02))",
                borderLeft: "1px solid rgba(15, 23, 42, 0.045)",
                borderRight: "1px solid rgba(15, 23, 42, 0.045)",
                zIndex: 2,
              }}
            />
          </>
        ) : null}
        <div
          data-testid="workbench-region"
          style={{
            flex: 1,
            minWidth: 0,
            height: "100%",
            minHeight: 0,
          }}
        >
          <LiveWorkflowPanel
            workspaceId={id}
            typeConfig={typeConfig ?? undefined}
            features={features}
            className="h-full"
            data-testid="workflow-panel"
          />
        </div>

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

        {/* Settings page also covers decisions and memory */}
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
