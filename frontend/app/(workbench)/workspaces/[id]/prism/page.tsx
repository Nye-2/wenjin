"use client";

import { use, useEffect, useState } from "react";

import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { getWorkspacePrismSurface } from "@/lib/api/workspace";
import type { WorkspacePrismSurfaceResponse } from "@/lib/api/types";
import { SurfaceSwitch } from "../components/SurfaceSwitch";

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
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
              : "Unable to load workspace Prism surface",
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
        ) : (
          <PrismSurfaceState
            message={error ?? "Loading Prism manuscript surface..."}
            tone={error ? "error" : "loading"}
          />
        )}
      </div>
    </div>
  );
}

function PrismSurfaceState({
  message,
  tone,
}: {
  message: string;
  tone: "loading" | "error";
}) {
  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)] px-6">
      <div
        className="rounded-[var(--v2-radius-lg)] border px-4 py-3 text-sm"
        style={{
          borderColor:
            tone === "error"
              ? "rgba(220, 38, 38, 0.18)"
              : "var(--v2-border-soft)",
          background:
            tone === "error"
              ? "rgba(220, 38, 38, 0.06)"
              : "var(--v2-surface-card)",
          color:
            tone === "error"
              ? "var(--v2-status-error)"
              : "var(--v2-text-secondary)",
          boxShadow: "var(--v2-shadow-soft)",
        }}
      >
        {message}
      </div>
    </div>
  );
}
