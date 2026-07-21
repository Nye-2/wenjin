"use client";

import {
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { PanelRightOpen } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";

import type { MissionView, PrismContextRef } from "@/lib/api/mission-types";
import { getWorkspace } from "@/lib/api/workspace";
import { defaultMissionSurface } from "@/lib/mission-view";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-type-config";
import { useMissionUiStore } from "@/stores/mission-ui-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { AutoCompactToast } from "./components/AutoCompactToast";
import {
  ChatPanel,
  type ChatPanelHandle,
} from "./components/ChatPanel";
import {
  MissionConsole,
  type MissionChatAction,
} from "./components/mission-console/MissionConsole";
import { useMissionWorkspace } from "./components/mission-console/useMissionWorkspace";
import { useMissionDemandPeek } from "./components/mission-console/useMissionDemandPeek";
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { MissionHistoryDrawer } from "./components/rooms/RunsDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { WorkspaceChrome } from "./components/shell/WorkspaceChrome";
import { useWorkspaceChromeCounts } from "./components/shell/useWorkspaceChromeCounts";
import {
  WorkspaceHubDrawer,
  type WorkspaceHubRoomKey,
} from "./components/shell/WorkspaceHubDrawer";

const SETTINGS_ROOMS = new Set<string>(["decisions", "settings"]);
const MIN_SPLIT_PERCENT = 36;
const MAX_SPLIT_PERCENT = 78;

type SettingsTab = "decisions" | "settings";
type RoomKey = WorkspaceHubRoomKey;
type MobileSurface = "chat" | "mission";

export default function WorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const roomSeed = readRoomRouteSeed(searchParams);
  const missionSeed = readMissionRouteSeed(searchParams);
  const prismContextRef = useMemo(
    () => readPrismContextRef(id, searchParams),
    [id, searchParams],
  );
  const [activeRoom, setActiveRoom] = useState<RoomKey | null>(roomSeed.room);
  const [compactToastVisible, setCompactToastVisible] = useState(false);
  const [hubOpen, setHubOpen] = useState(false);
  const [workspace, setWorkspace] = useState<{ name: string; type: string } | null>(null);
  const [isNarrow, setIsNarrow] = useState(false);
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>("chat");
  const [pendingChatAction, setPendingChatAction] =
    useState<MissionChatAction | null>(null);
  const splitRootRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<ChatPanelHandle>(null);

  const splitRatio = useWorkbenchLayoutStore((state) => state.splitRatio);
  const setSplitRatio = useWorkbenchLayoutStore((state) => state.setSplitRatio);
  const resetSplitRatio = useWorkbenchLayoutStore((state) => state.resetSplitRatio);
  const isFullscreen = useWorkbenchLayoutStore((state) => state.isWorkbenchFullscreen);
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const focusedMissionId = useMissionUiStore((state) => state.focusedMissionId);
  const focusMission = useMissionUiStore((state) => state.focusMission);
  const closePanel = useMissionUiStore((state) => state.closePanel);
  const clearWorkspaceFocus = useMissionUiStore((state) => state.clearWorkspaceFocus);
  const setContinuationMission = useMissionUiStore((state) => state.setContinuationMission);
  const {
    view,
    loading: missionLoading,
    switchingMissionId,
    refresh,
    switchMission,
  } = useMissionWorkspace(id);
  const chromeRefreshKey = view
    ? `${view.missionId}:${view.stateVersion}`
    : "no-mission-view";
  const { pendingReviewCount, missionStatus, completedRunCount, summaryState } =
    useWorkspaceChromeCounts(id, chromeRefreshKey);
  const { acknowledgeCurrentDemand } = useMissionDemandPeek({
    workspaceId: id,
    view,
    loading: missionLoading,
  });

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setIsNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    clearWorkspaceFocus();
    setMobileSurface("chat");
    if (missionSeed.missionId) {
      focusMission(missionSeed.missionId, missionSeed.surface);
      setMobileSurface("mission");
    }
  }, [clearWorkspaceFocus, focusMission, id, missionSeed.missionId, missionSeed.surface]);

  useEffect(() => {
    if (focusedMissionId && focusedMissionId !== view?.missionId) {
      const previousMissionId = view?.missionId ?? null;
      let active = true;
      void switchMission(focusedMissionId).then((accepted) => {
        if (
          !active ||
          accepted ||
          useMissionUiStore.getState().focusedMissionId !== focusedMissionId
        ) {
          return;
        }
        if (previousMissionId) {
          focusMission(previousMissionId, useMissionUiStore.getState().surface);
        } else {
          closePanel();
        }
      });
      return () => {
        active = false;
      };
    }
  }, [closePanel, focusMission, focusedMissionId, switchMission, view?.missionId]);

  useEffect(() => {
    let cancelled = false;
    getWorkspace(id)
      .then((item) => {
        if (cancelled) return;
        setWorkspace({ name: item.name, type: item.type });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [id]);

  const typeConfig = workspace
    ? WORKSPACE_TYPE_CONFIG[workspace.type as keyof typeof WORKSPACE_TYPE_CONFIG]
    : undefined;
  const focusedView =
    !focusedMissionId || focusedMissionId === view?.missionId ? view : null;
  const panelOpen = Boolean(
    panelMode !== "closed" && (focusedMissionId || focusedView),
  );
  const settingsOpen = activeRoom != null && SETTINGS_ROOMS.has(activeRoom);
  const settingsTab: SettingsTab = settingsOpen ? (activeRoom as SettingsTab) : "decisions";

  const openMission = useCallback(() => {
    if (!view) return;
    focusMission(
      view.missionId,
      view.attentionRequest ? "progress" : defaultMissionSurface(view),
    );
    setMobileSurface("mission");
  }, [focusMission, view]);

  const closeMission = useCallback(() => {
    acknowledgeCurrentDemand();
    closePanel();
    setMobileSurface("chat");
  }, [acknowledgeCurrentDemand, closePanel]);

  const handleMissionChatAction = useCallback((action: MissionChatAction) => {
    if (view) setContinuationMission(view.missionId);
    setPendingChatAction(action);
    setMobileSurface("chat");
  }, [setContinuationMission, view]);

  const focusAcceptedMission = useCallback((acceptedView: MissionView) => {
    focusMission(
      acceptedView.missionId,
      acceptedView.attentionRequest
        ? "progress"
        : defaultMissionSurface(acceptedView),
    );
    setMobileSurface("mission");
  }, [focusMission]);

  const handleMissionCreated = useCallback((missionId: string) => {
    const revealAfterSwitch = useMissionUiStore.getState().panelMode !== "closed";
    void switchMission(missionId, {
      retainOnFailure: true,
      onAccepted(acceptedView) {
        if (revealAfterSwitch) focusAcceptedMission(acceptedView);
      },
    });
  }, [focusAcceptedMission, switchMission]);

  const handleMissionTarget = useCallback(async (missionId: string) => {
    if (missionId === view?.missionId) {
      return Boolean(await refresh(missionId));
    }
    return Boolean(await switchMission(missionId, {
      retainOnFailure: true,
      onAccepted: focusAcceptedMission,
    }));
  }, [focusAcceptedMission, refresh, switchMission, view?.missionId]);

  const clearPrismContext = useCallback(() => {
    router.replace(`/workspaces/${encodeURIComponent(id)}`);
  }, [id, router]);

  useEffect(() => {
    if (mobileSurface !== "chat" || pendingChatAction === null) return;
    const frame = window.requestAnimationFrame(() => {
      if (pendingChatAction === "attach") {
        chatPanelRef.current?.openAttachment();
      } else if (pendingChatAction === "continue") {
        chatPanelRef.current?.prefillComposer("请从已保存进度继续完成这个任务，并先说明将从哪里接着推进。");
      } else {
        chatPanelRef.current?.focusComposer();
      }
      setPendingChatAction(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mobileSurface, pendingChatAction]);

  const onResizePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (isFullscreen) return;
      const root = splitRootRef.current;
      if (!root) return;
      event.preventDefault();
      const update = (clientX: number) => {
        const rect = root.getBoundingClientRect();
        if (rect.width > 0) setSplitRatio((clientX - rect.left) / rect.width);
      };
      const move = (moveEvent: PointerEvent) => update(moveEvent.clientX);
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      update(event.clientX);
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [isFullscreen, setSplitRatio],
  );

  const onResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 0.08 : 0.02;
      if (event.key === "ArrowLeft") setSplitRatio(splitRatio - step);
      else if (event.key === "ArrowRight") setSplitRatio(splitRatio + step);
      else if (event.key === "Home") setSplitRatio(MIN_SPLIT_PERCENT / 100);
      else if (event.key === "End") setSplitRatio(MAX_SPLIT_PERCENT / 100);
      else if (event.key === "Enter" || event.key === " ") resetSplitRatio();
      else return;
      event.preventDefault();
    },
    [resetSplitRatio, setSplitRatio, splitRatio],
  );

  return (
    <div className="wjn-shell-bg flex h-full min-h-0 flex-col text-[var(--wjn-text)]">
      <WorkspaceChrome
        workspaceId={id}
        workspaceName={workspace?.name}
        workspaceTypeLabel={typeConfig?.title}
        activeSurface="workbench"
        pendingReviewCount={pendingReviewCount}
        missionStatus={missionStatus}
        missionSummaryState={summaryState}
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

      {isNarrow && panelOpen ? (
        <div className="flex h-10 shrink-0 border-b border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-1" role="tablist" aria-label="工作区视图">
          <MobileTab active={mobileSurface === "chat"} label="对话" onClick={() => setMobileSurface("chat")} />
          <MobileTab active={mobileSurface === "mission"} label="研究任务" badge={pendingReviewCount} onClick={() => setMobileSurface("mission")} />
        </div>
      ) : null}

      <div ref={splitRootRef} className="relative flex min-h-0 flex-1" data-testid="workbench-split-root">
        {(!isNarrow || mobileSurface === "chat") && !isFullscreen ? (
          <div className="min-w-0" data-testid="chat-region" style={{ width: !isNarrow && panelOpen ? `${splitRatio * 100}%` : "100%" }}>
            <ChatPanel
              ref={chatPanelRef}
              workspaceId={id}
              workspaceName={workspace?.name}
              typeConfig={typeConfig}
              prismContextRef={prismContextRef}
              onPrismContextConsumed={clearPrismContext}
              className="h-full"
              data-testid="chat-panel"
              onMissionCreated={handleMissionCreated}
            />
          </div>
        ) : null}

        {!isNarrow && panelOpen && !isFullscreen ? (
          <div
            role="separator"
            aria-label="调整对话与任务面板宽度"
            aria-orientation="vertical"
            tabIndex={0}
            onPointerDown={onResizePointerDown}
            onKeyDown={onResizeKeyDown}
            onDoubleClick={resetSplitRatio}
            className="w-1 shrink-0 cursor-col-resize bg-[var(--wjn-line)] hover:bg-[var(--wjn-accent-line)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)]"
          />
        ) : null}

        {panelOpen && (!isNarrow || mobileSurface === "mission" || isFullscreen) ? (
          <div className="min-w-0 flex-1" data-testid="mission-region">
            {focusedView ? (
              <MissionConsole
                view={focusedView}
                compact={isNarrow}
                onClose={closeMission}
                onMissionTarget={handleMissionTarget}
                onChatAction={handleMissionChatAction}
              />
            ) : (
              <MissionSwitchPlaceholder
                loading={missionLoading || switchingMissionId === focusedMissionId}
              />
            )}
          </div>
        ) : null}

        {!panelOpen && view && !missionLoading ? (
          <button
            type="button"
            onClick={openMission}
            aria-label="打开研究任务"
            title="打开研究任务"
            className="absolute right-3 top-3 z-20 flex h-9 w-9 items-center justify-center rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-accent-strong)]"
          >
            <PanelRightOpen size={16} />
          </button>
        ) : null}
      </div>

      <SettingsPage workspaceId={id} open={settingsOpen} defaultTab={settingsTab} onClose={() => setActiveRoom(null)} />
      <LibraryDrawer workspaceId={id} open={activeRoom === "library"} onClose={() => setActiveRoom(null)} />
      <TasksDrawer workspaceId={id} open={activeRoom === "tasks"} onClose={() => setActiveRoom(null)} />
      <MissionHistoryDrawer workspaceId={id} open={activeRoom === "missions"} onClose={() => setActiveRoom(null)} />
      <AutoCompactToast workspaceId={id} visible={compactToastVisible} onDismiss={() => setCompactToastVisible(false)} />
    </div>
  );
}

function MissionSwitchPlaceholder({ loading }: { loading: boolean }) {
  return (
    <aside
      className="flex h-full min-w-0 flex-col border-l border-[var(--wjn-line)] bg-[var(--wjn-surface)]"
      aria-label="研究任务"
      aria-busy={loading}
      data-testid="mission-switch-placeholder"
    >
      <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center">
        <div>
          <div className="mx-auto h-5 w-5 animate-spin rounded-full border-2 border-[var(--wjn-line)] border-t-[var(--wjn-accent)] motion-reduce:animate-none" />
          <p className="mt-3 text-sm font-medium text-[var(--wjn-text)]" role="status">
            正在打开研究任务
          </p>
          <p className="mt-1 text-xs text-[var(--wjn-text-secondary)]">
            获取到对应任务后会一次性切换内容。
          </p>
        </div>
      </div>
    </aside>
  );
}

function MobileTab({ active, label, badge, onClick }: { active: boolean; label: string; badge?: number; onClick(): void }) {
  return (
    <button type="button" role="tab" aria-selected={active} onClick={onClick} className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--wjn-radius)] text-xs font-medium ${active ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]" : "text-[var(--wjn-text-secondary)]"}`}>
      {label}{badge ? <span className="rounded-full bg-[var(--wjn-review-soft)] px-1.5 text-[10px] text-[var(--wjn-review)]">{badge}</span> : null}
    </button>
  );
}

function readRoomRouteSeed(searchParams: ReturnType<typeof useSearchParams>): { room: RoomKey | null } {
  const value = searchParams.get("room");
  const valid: RoomKey[] = ["library", "decisions", "missions", "tasks", "settings"];
  return { room: valid.includes(value as RoomKey) ? (value as RoomKey) : null };
}

function readMissionRouteSeed(
  searchParams: ReturnType<typeof useSearchParams>,
): { missionId: string | null; surface: "progress" | "review" | "evidence" | "artifacts" | "trace" } {
  const missionId = searchParams.get("mission_id")?.trim() || null;
  const rawSurface = searchParams.get("mission_surface");
  const validSurfaces = ["progress", "review", "evidence", "artifacts", "trace"] as const;
  const surface = validSurfaces.includes(rawSurface as (typeof validSurfaces)[number])
    ? rawSurface as (typeof validSurfaces)[number]
    : "progress";
  return { missionId, surface };
}

function readPrismContextRef(
  workspaceId: string,
  searchParams: ReturnType<typeof useSearchParams>,
): PrismContextRef | null {
  const projectId = searchParams.get("prism_project_id")?.trim() ?? "";
  const fileId = searchParams.get("prism_file_id")?.trim() ?? "";
  const revisionRef = searchParams.get("prism_revision_ref")?.trim() ?? "";
  const selectionHash = searchParams.get("prism_selection_hash")?.trim() ?? "";
  const startValue = searchParams.get("prism_selection_byte_start")?.trim() ?? "";
  const endValue = searchParams.get("prism_selection_byte_end")?.trim() ?? "";
  const start = Number(startValue);
  const end = Number(endValue);
  if (
    !projectId ||
    !fileId ||
    !revisionRef ||
    !/^sha256:[0-9a-f]{64}$/.test(selectionHash) ||
    !/^\d+$/.test(startValue) ||
    !/^\d+$/.test(endValue) ||
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 0 ||
    end <= start
  ) {
    return null;
  }
  return {
    workspace_id: workspaceId,
    prism_project_id: projectId,
    file_id: fileId,
    base_revision_ref: revisionRef,
    selection_hash: selectionHash,
    selection_byte_range: [start, end],
  };
}
