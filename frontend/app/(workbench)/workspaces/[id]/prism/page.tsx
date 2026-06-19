"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useOptionalI18n } from "@/components/i18n-provider";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import {
  ensureWorkspacePrismProject,
  getWorkspace,
  getWorkspacePrismSurface,
} from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-suggestions";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { PrismContextRail } from "./PrismContextRail";
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

function safeCount(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const i18n = useOptionalI18n();
  const t = i18n?.t;
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
  const typeConfig = workspace
    ? WORKSPACE_TYPE_CONFIG[workspace.type as keyof typeof WORKSPACE_TYPE_CONFIG]
    : null;
  const { pendingReviewCount, activeRunCount, completedRunCount } =
    useWorkspaceChromeCounts(
      id,
      safeCount(surface?.review_summary?.pending_count),
    );

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
                : "Unable to open Prism manuscript surface",
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
        activeRunCount={activeRunCount}
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
        {surface?.latex_project_id ? (
          <div
            data-testid="prism-studio-shell"
            className="wjn-prism-studio flex h-full min-h-0 flex-col"
          >
            <PrismContextRail surface={surface} />
            <LatexEditorShell
              projectId={surface.latex_project_id}
              workspaceId={id}
              initialFileChanges={surface.file_changes ?? []}
              initialAppliedFileChanges={surface.applied_file_changes ?? []}
              onReviewStateChanged={refreshSurface}
            />
          </div>
        ) : error ? (
          <WorkspaceSurfaceState
            tone="error"
            title={
              t?.("workspaceSurfaces.prismErrorTitle") ??
              "Unable to open Prism manuscript surface"
            }
            description={error}
          />
        ) : surface ? (
          <WorkspaceSurfaceState
            tone="empty"
            title={
              t?.("workspaceSurfaces.prismEmptyTitle") ??
              "还没有绑定写作项目"
            }
            description={
              t?.("workspaceSurfaces.prismEmptyDescription") ??
              "从 Workbench 启动论文写作任务后，这里会自动打开主稿。"
            }
          />
        ) : (
          <WorkspaceSurfaceState
            tone="loading"
            title={
              t?.("workspaceSurfaces.prismLoadingTitle") ??
              "正在打开论文写作台"
            }
            description={
              t?.("workspaceSurfaces.prismLoadingDescription") ??
              "正在加载工作区主稿和待确认修改。"
            }
          />
        )}
      </div>
    </div>
  );
}
