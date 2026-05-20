"use client";

import { use, useEffect, useState } from "react";

import { useOptionalI18n } from "@/components/i18n-provider";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import {
  ensureWorkspacePrismProject,
  getWorkspacePrismSurface,
} from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { SurfaceSwitch } from "../components/SurfaceSwitch";

type PrismSurfaceLoadState = {
  workspaceId: string;
  surface: WorkspacePrismSurfaceResponse | null;
  error: string | null;
};

function readHttpStatus(error: unknown): number | null {
  if (!error || typeof error !== "object") {
    return null;
  }
  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === "number" ? response.status : null;
}

async function loadWorkspacePrismSurface(
  workspaceId: string,
): Promise<WorkspacePrismSurfaceResponse> {
  try {
    return await getWorkspacePrismSurface(workspaceId);
  } catch (error) {
    if (readHttpStatus(error) !== 404) {
      throw error;
    }
    await ensureWorkspacePrismProject(workspaceId);
    return await getWorkspacePrismSurface(workspaceId);
  }
}

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const i18n = useOptionalI18n();
  const t = i18n?.t;
  const [loadState, setLoadState] = useState<PrismSurfaceLoadState>({
    workspaceId: id,
    surface: null,
    error: null,
  });

  const surface = loadState.workspaceId === id ? loadState.surface : null;
  const error = loadState.workspaceId === id ? loadState.error : null;

  useEffect(() => {
    let cancelled = false;

    loadWorkspacePrismSurface(id)
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
  }, [id]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SurfaceSwitch workspaceId={id} active="prism" />
      <div className="min-h-0 flex-1">
        {surface?.latex_project_id ? (
          <LatexEditorShell projectId={surface.latex_project_id} workspaceId={id} />
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
              "No Prism manuscript is bound yet"
            }
            description={
              t?.("workspaceSurfaces.prismEmptyDescription") ??
              "Start a manuscript-writing task from Workbench to create the primary project."
            }
          />
        ) : (
          <WorkspaceSurfaceState
            tone="loading"
            title={
              t?.("workspaceSurfaces.prismLoadingTitle") ??
              "Opening Prism manuscript surface"
            }
            description={
              t?.("workspaceSurfaces.prismLoadingDescription") ??
              "Loading the workspace manuscript project and pending writes."
            }
          />
        )}
      </div>
    </div>
  );
}
