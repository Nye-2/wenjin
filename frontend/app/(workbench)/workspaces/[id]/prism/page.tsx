"use client";

import { use, useEffect, useState } from "react";

import { useOptionalI18n } from "@/components/i18n-provider";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import { getWorkspacePrismSurface } from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { PrismContextRail } from "./PrismContextRail";
import { SurfaceSwitch } from "../components/SurfaceSwitch";

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

    getWorkspacePrismSurface(id)
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
      <div className="grid min-h-0 flex-1 xl:grid-cols-[minmax(0,1fr)_320px]">
        {surface?.latex_project_id ? (
          <>
            <div className="min-w-0">
              <LatexEditorShell
                projectId={surface.latex_project_id}
                workspaceId={id}
                initialFileChanges={surface.file_changes ?? []}
                initialAppliedFileChanges={surface.applied_file_changes ?? []}
              />
            </div>
            <PrismContextRail surface={surface} />
          </>
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
