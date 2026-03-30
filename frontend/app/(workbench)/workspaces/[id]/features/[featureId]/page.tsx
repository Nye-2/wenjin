"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getWorkspaceFeatureChatRoute } from "@/lib/workspace-feature-routes";

export default function WorkspaceFeatureRedirect() {
  const router = useRouter();
  const params = useParams<{ id: string; featureId: string }>();
  const searchParams = useSearchParams();
  const workspaceId = params.id;
  const featureId = params.featureId;

  useEffect(() => {
    const queryParams: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (key !== "feature" && key !== "skill") {
        queryParams[key] = value;
      }
    });

    const chatRoute = getWorkspaceFeatureChatRoute(workspaceId, featureId, queryParams);
    if (chatRoute) {
      router.replace(chatRoute);
    } else {
      router.replace(`/workspaces/${workspaceId}`);
    }
  }, [router, workspaceId, featureId, searchParams]);

  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]">
      <Loader2 className="h-6 w-6 animate-spin text-[var(--accent-primary)]" />
    </div>
  );
}
