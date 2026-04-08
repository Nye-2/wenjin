"use client";

import { useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getWorkspaceFeatureChatRoute } from "@/lib/workspace-feature-routes";

export default function WorkspaceFeatureRedirect() {
  const router = useRouter();
  const params = useParams<{ id: string; featureId: string }>();
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const workspaceId = params.id;
  const featureId = params.featureId;
  const redirectedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const routeKey = `${workspaceId}:${featureId}:${searchParamString}`;
    if (redirectedKeyRef.current === routeKey) {
      return;
    }

    const queryParams: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (key !== "feature") {
        queryParams[key] = value;
      }
    });

    const chatRoute = getWorkspaceFeatureChatRoute(workspaceId, featureId, queryParams);
    redirectedKeyRef.current = routeKey;
    if (chatRoute) {
      router.replace(chatRoute);
    } else {
      router.replace(`/workspaces/${workspaceId}`);
    }
  }, [featureId, router, searchParamString, searchParams, workspaceId]);

  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]">
      <Loader2 className="h-6 w-6 animate-spin text-[var(--accent-primary)]" />
    </div>
  );
}
