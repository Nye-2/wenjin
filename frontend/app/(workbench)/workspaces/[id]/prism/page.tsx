"use client";

import { use, useEffect, useState } from "react";

import { useOptionalI18n } from "@/components/i18n-provider";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import { getWorkspacePrismSurface } from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { SurfaceSwitch } from "../components/SurfaceSwitch";

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const i18n = useOptionalI18n();
  const t = i18n?.t;
  const [surface, setSurface] = useState<WorkspacePrismSurfaceResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSurface(null);
    setError(null);

    getWorkspacePrismSurface(id)
      .then((nextSurface) => {
        if (!cancelled) {
          setSurface(nextSurface);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to open Prism manuscript surface",
          );
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
          <LatexEditorShell projectId={surface.latex_project_id} />
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
