"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { useOptionalI18n } from "@/components/i18n-provider";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { WorkspaceSurfaceState } from "@/components/workspace/WorkspaceSurfaceState";
import { getLatexProject } from "@/lib/api/latex";

export default function LatexProjectPage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const i18n = useOptionalI18n();
  const t = i18n?.t;
  const projectId = params?.projectId ?? "";
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!projectId) {
      return;
    }

    getLatexProject(projectId)
      .then((project) => {
        if (cancelled) {
          return;
        }
        if (
          project.workspace_id &&
          (project.surface_role ?? "primary_manuscript") === "primary_manuscript"
        ) {
          setRedirecting(true);
          router.replace(`/workspaces/${project.workspace_id}/prism`);
        }
      })
      .catch(() => {
        // Let LatexEditorShell keep its existing not-found/error handling.
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, router]);

  if (redirecting) {
    return (
      <WorkspaceSurfaceState
        tone="loading"
        className="h-screen"
        title={
          t?.("workspaceSurfaces.legacyRedirectTitle") ??
          "Opening workspace Prism"
        }
        description={
          t?.("workspaceSurfaces.legacyRedirectDescription") ??
          "This manuscript now belongs to a workspace. Taking you to the workspace-owned surface."
        }
      />
    );
  }

  return <LatexEditorShell projectId={projectId} />;
}
