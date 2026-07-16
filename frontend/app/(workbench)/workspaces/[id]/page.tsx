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
import { PanelRightOpen } from "lucide-react";
import { useSearchParams } from "next/navigation";

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
import { LibraryDrawer } from "./components/rooms/LibraryDrawer";
import { MissionHistoryDrawer } from "./components/rooms/RunsDrawer";
import { SettingsPage } from "./components/rooms/SettingsPage";
import { TasksDrawer } from "./components/rooms/TasksDrawer";
import { WorkspaceChrome } from "./components/shell/WorkspaceChrome";
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
  const searchParams = useSearchParams();
  const roomSeed = readRoomRouteSeed(searchParams);
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
  const peekMission = useMissionUiStore((state) => state.peekMission);
  const focusMission = useMissionUiStore((state) => state.focusMission);
  const closePanel = useMissionUiStore((state) => state.closePanel);
  const clearWorkspaceFocus = useMissionUiStore((state) => state.clearWorkspaceFocus);
  const setBadgeCount = useMissionUiStore((state) => state.setBadgeCount);
  const { view, loading: missionLoading, refresh, setView } = useMissionWorkspace(
    id,
    focusedMissionId,
  );
  const missionIsGenerating = Boolean(
    view && ["created", "planning", "running"].includes(view.executionStatus),
  );
  const visibleReviewCount =
    view && !missionIsGenerating
      ? view.reviewSummary.pending + view.reviewSummary.needsMoreEvidence
      : 0;

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
  }, [clearWorkspaceFocus, id]);

  useEffect(() => {
    setBadgeCount(visibleReviewCount);
  }, [setBadgeCount, visibleReviewCount]);

  useEffect(() => {
    if (focusedMissionId && focusedMissionId !== view?.missionId) {
      void refresh(focusedMissionId);
    }
  }, [focusedMissionId, refresh, view?.missionId]);

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
  const panelOpen = Boolean(view && panelMode !== "closed");
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
    closePanel();
    setMobileSurface("chat");
  }, [closePanel]);

  const handleMissionChatAction = useCallback((action: MissionChatAction) => {
    setPendingChatAction(action);
    setMobileSurface("chat");
  }, []);

  useEffect(() => {
    if (mobileSurface !== "chat" || pendingChatAction === null) return;
    const frame = window.requestAnimationFrame(() => {
      if (pendingChatAction === "attach") {
        chatPanelRef.current?.openAttachment();
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
        pendingReviewCount={visibleReviewCount}
        missionStatus={view?.executionStatus === "waiting" ? "waiting" : view && ["created", "planning", "running"].includes(view.executionStatus) ? "running" : null}
        onOpenHub={() => setHubOpen(true)}
      />
      <WorkspaceHubDrawer
        open={hubOpen}
        activeRoom={activeRoom}
        pendingReviewCount={visibleReviewCount}
        completedRunCount={view?.executionStatus === "completed" ? 1 : 0}
        onClose={() => setHubOpen(false)}
        onRoomSelect={setActiveRoom}
      />

      {isNarrow && panelOpen ? (
        <div className="flex h-10 shrink-0 border-b border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-1" role="tablist" aria-label="工作区视图">
          <MobileTab active={mobileSurface === "chat"} label="对话" onClick={() => setMobileSurface("chat")} />
          <MobileTab active={mobileSurface === "mission"} label="研究任务" badge={visibleReviewCount} onClick={() => setMobileSurface("mission")} />
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
              className="h-full"
              data-testid="chat-panel"
              onMissionCreated={(missionId) =>
                void refresh(missionId).then((next) => {
                  if (next) peekMission(next.missionId);
                })
              }
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

        {view && panelOpen && (!isNarrow || mobileSurface === "mission" || isFullscreen) ? (
          <div className="min-w-0 flex-1" data-testid="mission-region">
            <MissionConsole
              view={view}
              compact={isNarrow}
              onClose={closeMission}
              onViewChange={setView}
              onChatAction={handleMissionChatAction}
            />
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
