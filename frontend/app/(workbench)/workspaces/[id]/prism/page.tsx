"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import {
  ensureWorkspacePrismProject,
  getWorkspace,
  getWorkspacePrismSurface,
} from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-type-config";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { PrismContextRail } from "./PrismContextRail";
import { PrismWorkspaceShell } from "./PrismWorkspaceShell";
import { WorkspaceChrome } from "../components/shell/WorkspaceChrome";
import {
  WorkspaceHubDrawer,
  type WorkspaceHubRoomKey,
} from "../components/shell/WorkspaceHubDrawer";
import { useWorkspaceChromeCounts } from "../components/shell/useWorkspaceChromeCounts";

type PrismSurfaceLoadState = {
  workspaceId: string;
  surface: WorkspacePrismSurfaceResponse | null;
  error: string | null;
};

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loadState, setLoadState] = useState<PrismSurfaceLoadState>({
    workspaceId: id,
    surface: null,
    error: null,
  });
  const [workspace, setWorkspace] = useState<{
    name: string;
    type: string;
  } | null>(null);
  const [hubOpen, setHubOpen] = useState(false);
  const [surfaceRefreshToken, setSurfaceRefreshToken] = useState(0);
  const prismRefreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[id]?.prism ?? 0,
  );

  const surface = loadState.workspaceId === id ? loadState.surface : null;
  const error = loadState.workspaceId === id ? loadState.error : null;
  const initialFileId = searchParams?.get("file_id")?.trim() || null;
  const visualMissionId = searchParams?.get("visual_mission_id")?.trim() || null;
  const visualReviewItemId = searchParams?.get("visual_review_item_id")?.trim() || null;
  const visualInsertionSource = visualMissionId && visualReviewItemId
    ? { missionId: visualMissionId, sourceReviewItemId: visualReviewItemId }
    : null;
  const typeConfig = workspace
    ? WORKSPACE_TYPE_CONFIG[workspace.type as keyof typeof WORKSPACE_TYPE_CONFIG]
    : null;
  const { pendingReviewCount, missionStatus, completedRunCount, summaryState } =
    useWorkspaceChromeCounts(id, `${prismRefreshCounter}:${surfaceRefreshToken}`);

  const refreshSurface = useCallback(() => {
    setSurfaceRefreshToken((token) => token + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadSurface() {
      await ensureWorkspacePrismProject(id);
      return getWorkspacePrismSurface(id);
    }

    loadSurface()
      .then((nextSurface) => {
        if (!cancelled) {
          setLoadState({
            workspaceId: id,
            surface: nextSurface,
            error: null,
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadState({
            workspaceId: id,
            surface: null,
            error:
              err instanceof Error
                ? err.message
                : "无法打开 Prism 主稿面，请稍后重试。",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id, prismRefreshCounter, surfaceRefreshToken]);

  useEffect(() => {
    let cancelled = false;
    getWorkspace(id)
      .then((nextWorkspace) => {
        if (!cancelled) {
          setWorkspace({
            name: nextWorkspace.name,
            type: nextWorkspace.type,
          });
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id]);

  const openWorkbenchRoom = useCallback(
    (room: WorkspaceHubRoomKey) => {
      router.push(`/workspaces/${id}?room=${room}`);
    },
    [id, router],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceChrome
        workspaceId={id}
        workspaceName={workspace?.name}
        workspaceTypeLabel={typeConfig?.title}
        activeSurface="prism"
        pendingReviewCount={pendingReviewCount}
        missionStatus={missionStatus}
        missionSummaryState={summaryState}
        onOpenHub={() => setHubOpen(true)}
      />
      <WorkspaceHubDrawer
        open={hubOpen}
        activeRoom={null}
        pendingReviewCount={pendingReviewCount}
        completedRunCount={completedRunCount}
        onClose={() => setHubOpen(false)}
        onRoomSelect={openWorkbenchRoom}
      />
      <div className="min-h-0 flex-1 overflow-hidden">
        {surface ? (
          <div
            data-testid="prism-studio-shell"
            className="wjn-prism-studio flex h-full min-h-0 flex-col"
          >
            <PrismContextRail surface={surface} />
            <PrismWorkspaceShell
              workspaceId={id}
              surface={surface}
              initialFileId={initialFileId}
              visualInsertionSource={visualInsertionSource}
              onSurfaceChanged={refreshSurface}
            />
          </div>
        ) : error ? (
          <WorkspaceSurfaceState
            tone="error"
            title="无法打开 Prism 主稿台"
            description={error}
          />
        ) : (
          <WorkspaceSurfaceState
            tone="loading"
            title="正在打开 Prism 主稿台"
            description="正在载入工作区绑定的主稿项目与待确认写入状态。"
          />
        )}
      </div>
    </div>
  );
}
