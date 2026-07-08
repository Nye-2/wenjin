"use client";

import {
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useSearchParams } from "next/navigation";
import { PanelRightOpen } from "lucide-react";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { AutoCompactToast } from "./components/AutoCompactToast";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { RunsDrawer } from "./components/rooms/RunsDrawer";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { WorkspaceChrome } from "./components/shell/WorkspaceChrome";
import {
  WorkspaceHubDrawer,
  type WorkspaceHubRoomKey,
} from "./components/shell/WorkspaceHubDrawer";
import { useWorkspaceChromeCounts } from "./components/shell/useWorkspaceChromeCounts";
import { getWorkspace, getWorkspaceFeatures } from "@/lib/api/workspace";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-type-config";
import { useExecutionStore } from "@/stores/execution-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import type { WorkspaceCapability } from "@/lib/api/types";

const SETTINGS_ROOMS = new Set<string>([
  "decisions",
  "settings",
]);
const MIN_SPLIT_PERCENT = 28;
const MAX_SPLIT_PERCENT = 72;
const SPLIT_KEYBOARD_STEP = 0.02;
const SPLIT_KEYBOARD_LARGE_STEP = 0.1;

type SettingsTab = "decisions" | "settings";
type RoomKey = WorkspaceHubRoomKey;
type MobileSurface = "chat" | "run" | "review";

const MOBILE_SURFACE_TABS: Array<{
  key: MobileSurface;
  label: string;
}> = [
  { key: "chat", label: "对话" },
  { key: "run", label: "进展" },
  { key: "review", label: "复核" },
];

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
  const [hubOpen, setHubOpen] = useState(false);
  const [workspace, setWorkspace] = useState<{
    name: string;
    type: string;
  } | null>(null);
  const [features, setFeatures] = useState<WorkspaceCapability[]>([]);
  const splitRatio = useWorkbenchLayoutStore((state) => state.splitRatio);
  const selectedRunId = useWorkbenchLayoutStore((state) => state.selectedRunId);
  const focusedRunId = useRunUiStore((state) => state.focusedRunId);
  const activeRunId = useRunUiStore((state) => state.activeRunId);
  const scopedMissionRunKey = useExecutionStore((state) => {
    const activeRecord = activeRunId
      ? state.executions.get(activeRunId)
      : null;
    const focusedRecord = focusedRunId
      ? state.executions.get(focusedRunId)
      : null;
    const selectedRecord = selectedRunId
      ? state.executions.get(selectedRunId)
      : null;
    const scopedActiveRunId =
      activeRunId &&
      (!activeRecord ||
        !activeRecord.workspace_id ||
        activeRecord.workspace_id === id)
        ? activeRunId
        : "";
    const scopedFocusedRunId =
      focusedRunId &&
      focusedRecord &&
      (!focusedRecord.workspace_id || focusedRecord.workspace_id === id)
        ? focusedRunId
        : "";
    const scopedSelectedRunId =
      selectedRunId && selectedRecord?.workspace_id === id ? selectedRunId : "";
    return [
      scopedActiveRunId,
      scopedFocusedRunId,
      scopedSelectedRunId,
    ].join("|");
  });
  const isWorkbenchFullscreen = useWorkbenchLayoutStore(
    (state) => state.isWorkbenchFullscreen,
  );
  const [isNarrowViewport, setIsNarrowViewport] = useState(false);
  const setSplitRatio = useWorkbenchLayoutStore((state) => state.setSplitRatio);
  const resetSplitRatio = useWorkbenchLayoutStore(
    (state) => state.resetSplitRatio,
  );
  const setActiveWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.setActiveWorkbenchTab,
  );
  const { pendingReviewCount, activeRunCount, completedRunCount } =
    useWorkspaceChromeCounts(id);
  const splitRootRef = useRef<HTMLDivElement>(null);
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>("chat");
  const [manualMissionPanelOpen, setManualMissionPanelOpen] = useState(false);
  const [suppressedMissionDemandKey, setSuppressedMissionDemandKey] =
    useState<string | null>(null);
  const desktopSplitRatio = splitRatio;
  const hasScopedMissionRun = scopedMissionRunKey !== "||";
  const missionDemandKey =
    activeRunCount > 0 ||
    pendingReviewCount > 0 ||
    hasScopedMissionRun
      ? [
          scopedMissionRunKey,
          activeRunCount,
          pendingReviewCount,
        ].join("|")
      : null;
  const missionPanelOpen =
    isWorkbenchFullscreen ||
    manualMissionPanelOpen ||
    (missionDemandKey !== null && suppressedMissionDemandKey !== missionDemandKey);
  const desktopMissionPanelOpen =
    !isNarrowViewport && !isWorkbenchFullscreen && missionPanelOpen;

  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setIsNarrowViewport(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    setManualMissionPanelOpen(false);
    setSuppressedMissionDemandKey(null);
  }, [id]);

  useEffect(() => {
    if (missionDemandKey !== null) {
      return;
    }
    setSuppressedMissionDemandKey(null);
  }, [missionDemandKey]);

  useEffect(() => {
    let cancelled = false;
    getWorkspace(id)
      .then(async (w) => {
        if (cancelled) return;
        setWorkspace({ name: w.name, type: w.type });
        const data = await getWorkspaceFeatures(id);
        if (cancelled) return;
        setFeatures(data.features);
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

  const handleResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (isWorkbenchFullscreen) {
        return;
      }

      const step = event.shiftKey
        ? SPLIT_KEYBOARD_LARGE_STEP
        : SPLIT_KEYBOARD_STEP;
      let nextRatio: number | null = null;
      if (event.key === "ArrowLeft") {
        nextRatio = splitRatio - step;
      } else if (event.key === "ArrowRight") {
        nextRatio = splitRatio + step;
      } else if (event.key === "Home") {
        nextRatio = MIN_SPLIT_PERCENT / 100;
      } else if (event.key === "End") {
        nextRatio = MAX_SPLIT_PERCENT / 100;
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        resetSplitRatio();
        return;
      }

      if (nextRatio === null) {
        return;
      }
      event.preventDefault();
      setSplitRatio(nextRatio);
    },
    [isWorkbenchFullscreen, resetSplitRatio, setSplitRatio, splitRatio],
  );

  const handleMobileSurfaceChange = useCallback(
    (surface: MobileSurface) => {
      setMobileSurface(surface);
      if (surface === "run") {
        setActiveWorkbenchTab("run");
      } else if (surface === "review") {
        setActiveWorkbenchTab("review");
      }
    },
    [setActiveWorkbenchTab],
  );

  const openMissionPanel = useCallback(() => {
    setManualMissionPanelOpen(true);
    setSuppressedMissionDemandKey(null);
  }, []);

  const closeMissionPanel = useCallback(() => {
    setManualMissionPanelOpen(false);
    setSuppressedMissionDemandKey(missionDemandKey);
  }, [missionDemandKey]);

  // Map topbar room selection to panels
  const settingsOpen = activeRoom != null && SETTINGS_ROOMS.has(activeRoom);
  const settingsTab: SettingsTab =
    settingsOpen && SETTINGS_ROOMS.has(activeRoom!)
      ? (activeRoom as SettingsTab)
      : "decisions";

  return (
    <div className="wjn-shell-bg flex h-full min-h-0 flex-col text-[var(--wjn-text)]">
      <WorkspaceChrome
        workspaceId={id}
        workspaceName={workspace?.name}
        workspaceTypeLabel={typeConfig?.title}
        activeSurface="workbench"
        pendingReviewCount={pendingReviewCount}
        activeRunCount={activeRunCount}
        onOpenHub={() => setHubOpen(true)}
      />
      <WorkspaceHubDrawer
        open={hubOpen}
        activeRoom={activeRoom}
        pendingReviewCount={pendingReviewCount}
        completedRunCount={completedRunCount}
        onClose={() => setHubOpen(false)}
        onRoomSelect={setActiveRoom}
      />
      <div
        ref={splitRootRef}
        className={`relative flex min-h-0 flex-1 ${isNarrowViewport ? "flex-col" : ""}`}
        data-testid="workbench-split-root"
      >
        {isNarrowViewport && !isWorkbenchFullscreen ? (
          <MobileSurfaceTabs
            activeSurface={mobileSurface}
            onChange={handleMobileSurfaceChange}
          />
        ) : null}
        {isNarrowViewport ? (
          !isWorkbenchFullscreen && mobileSurface === "chat" ? (
            <div
              data-testid="chat-region"
              style={{
                flex: 1,
                minHeight: 260,
                minWidth: 0,
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
          ) : null
        ) : !isWorkbenchFullscreen ? (
          <>
            <div
              data-testid="chat-region"
              style={{
                width: desktopMissionPanelOpen
                  ? `${desktopSplitRatio * 100}%`
                  : "100%",
                minWidth: 320,
                maxWidth: desktopMissionPanelOpen ? "72%" : "none",
                height: "100%",
                minHeight: 0,
                borderRight: desktopMissionPanelOpen
                  ? "1px solid var(--wjn-line)"
                  : "none",
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
            {desktopMissionPanelOpen ? (
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="调整对话与工作台宽度"
                aria-valuemin={MIN_SPLIT_PERCENT}
                aria-valuemax={MAX_SPLIT_PERCENT}
                aria-valuenow={Math.round(desktopSplitRatio * 100)}
                tabIndex={0}
                data-testid="workbench-resizer"
                onPointerDown={handleResizePointerDown}
                onKeyDown={handleResizeKeyDown}
                onDoubleClick={resetSplitRatio}
                title="拖拽调整宽度，方向键微调，双击或回车恢复默认"
                style={{
                  width: 8,
                  flex: "0 0 8px",
                  cursor: "col-resize",
                  background: "var(--wjn-bg-rail)",
                  borderLeft: "1px solid var(--wjn-line)",
                  borderRight: "1px solid var(--wjn-line)",
                  zIndex: 2,
                }}
              />
            ) : (
              <button
                type="button"
                aria-label="展开研究任务"
                title="展开研究任务"
                data-testid="workbench-panel-toggle"
                onClick={openMissionPanel}
                style={{
                  position: "absolute",
                  right: 12,
                  top: 10,
                  zIndex: 4,
                  height: 34,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  borderRadius: "var(--wjn-radius)",
                  border: "1px solid var(--wjn-line)",
                  background: "var(--wjn-surface-raised)",
                  color: "var(--wjn-text-secondary)",
                  boxShadow: "var(--wjn-shadow-sm)",
                  padding: "0 10px",
                  fontSize: 12.5,
                  fontWeight: 650,
                  cursor: "pointer",
                  fontFamily: "var(--wjn-font-sans)",
                }}
              >
                <PanelRightOpen size={14} aria-hidden="true" />
                <span>研究任务</span>
                {activeRunCount > 0 || pendingReviewCount > 0 ? (
                  <span
                    style={{
                      minWidth: 18,
                      height: 18,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      borderRadius: "var(--wjn-radius-pill)",
                      background: "var(--wjn-accent-soft)",
                      color: "var(--wjn-accent-strong)",
                      fontSize: 11,
                    }}
                  >
                    {Math.min(activeRunCount + pendingReviewCount, 99)}
                  </span>
                ) : null}
              </button>
            )}
          </>
        ) : null}
        {!isNarrowViewport || isWorkbenchFullscreen || mobileSurface !== "chat" ? (
          <div
            data-testid="workbench-region"
            data-panel-open={
              isNarrowViewport || isWorkbenchFullscreen || desktopMissionPanelOpen
                ? "true"
                : "false"
            }
            aria-hidden={
              !isNarrowViewport && !isWorkbenchFullscreen && !desktopMissionPanelOpen
                ? true
                : undefined
            }
            style={{
              flex: desktopMissionPanelOpen || isWorkbenchFullscreen ? 1 : "0 0 0px",
              minWidth: 0,
              width:
                !isNarrowViewport && !isWorkbenchFullscreen && !desktopMissionPanelOpen
                  ? 0
                  : undefined,
              height: isNarrowViewport && !isWorkbenchFullscreen ? undefined : "100%",
              minHeight: 0,
              overflow:
                !isNarrowViewport && !isWorkbenchFullscreen && !desktopMissionPanelOpen
                  ? "hidden"
                  : undefined,
              visibility:
                !isNarrowViewport && !isWorkbenchFullscreen && !desktopMissionPanelOpen
                  ? "hidden"
                  : undefined,
              pointerEvents:
                !isNarrowViewport && !isWorkbenchFullscreen && !desktopMissionPanelOpen
                  ? "none"
                  : undefined,
            }}
          >
            <LiveWorkflowPanel
              workspaceId={id}
              typeConfig={typeConfig ?? undefined}
              className="h-full"
              data-testid="workflow-panel"
              onClose={
                !isNarrowViewport && !isWorkbenchFullscreen
                  ? closeMissionPanel
                  : undefined
              }
            />
          </div>
        ) : null}

        {/* Room drawers */}
        <LibraryDrawer
          workspaceId={id}
          open={activeRoom === "library"}
          initialQuery={activeRoom === "library" ? roomSeed.query : null}
          focusItemId={activeRoom === "library" ? roomSeed.itemId : null}
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

        {/* Settings page covers decisions and workspace settings. */}
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

function MobileSurfaceTabs({
  activeSurface,
  onChange,
}: {
  activeSurface: MobileSurface;
  onChange: (surface: MobileSurface) => void;
}) {
  return (
    <nav
      role="tablist"
      aria-label="移动端工作区视图"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
        gap: 4,
        padding: "8px 10px",
        borderBottom: "1px solid var(--wjn-line)",
        background: "var(--wjn-surface)",
      }}
    >
      {MOBILE_SURFACE_TABS.map((tab) => {
        const active = tab.key === activeSurface;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={tab.label}
            onClick={() => onChange(tab.key)}
            style={{
              height: 34,
              borderRadius: "var(--wjn-radius)",
              border: active
                ? "1px solid var(--wjn-accent-line)"
                : "1px solid transparent",
              background: active ? "var(--wjn-accent-soft)" : "transparent",
              color: active ? "var(--wjn-accent-strong)" : "var(--wjn-text-secondary)",
              fontSize: 13,
              fontWeight: 650,
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}

function readRequestedRoom(
  searchParams: ReturnType<typeof useSearchParams>,
): RoomKey | null {
  const value = searchParams?.get("room")?.trim().toLowerCase();
  if (
    value === "library" ||
    value === "decisions" ||
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
