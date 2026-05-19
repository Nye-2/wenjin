"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { getLatexProject } from "@/lib/api/latex";

export default function LatexProjectPage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
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
      <div className="flex h-screen items-center justify-center bg-[var(--bg-base)] text-sm text-[var(--v2-text-secondary)]">
        Opening workspace Prism...
      </div>
    );
  }

  return <LatexEditorShell projectId={projectId} />;
}
