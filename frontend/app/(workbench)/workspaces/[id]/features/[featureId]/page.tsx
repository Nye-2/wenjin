"use client";

import { useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getWorkspaceFeatureChatRoute } from "@/lib/workspace-feature-routes";
import { useFeaturesStore } from "@/stores/features";

export default function WorkspaceFeatureRedirect() {
  const router = useRouter();
  const params = useParams<{ id: string; featureId: string }>();
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const workspaceId = params.id;
  const featureId = params.featureId;
  const features = useFeaturesStore((state) => state.features);
  const isFeaturesLoading = useFeaturesStore((state) => state.isLoading);
  const redirectedKeyRef = useRef<string | null>(null);
  const requestedFeaturesRef = useRef<string | null>(null);
  const fetchFeatures = useFeaturesStore((state) => state.fetchFeatures);
  const feature =
    features.find((candidate) => candidate.id === featureId) ?? null;

  useEffect(() => {
    if (!workspaceId || !featureId) {
      return;
    }

    const fallbackRouteKey = `${workspaceId}:${featureId}:missing-feature`;

    if (feature === null) {
      if (isFeaturesLoading) {
        return;
      }

      if (requestedFeaturesRef.current !== workspaceId) {
        requestedFeaturesRef.current = workspaceId;
        void fetchFeatures(workspaceId);
        return;
      }

      if (features.length === 0) {
        if (redirectedKeyRef.current === fallbackRouteKey) {
          return;
        }
        redirectedKeyRef.current = fallbackRouteKey;
        router.replace(`/workspaces/${workspaceId}`);
        return;
      }
    }

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

    const chatRoute = feature
      ? getWorkspaceFeatureChatRoute(workspaceId, featureId, {
          ...(feature.defaultSkillId ? { skill: feature.defaultSkillId } : {}),
          ...queryParams,
        })
      : null;
    redirectedKeyRef.current = routeKey;
    if (chatRoute) {
      router.replace(chatRoute);
    } else {
      router.replace(`/workspaces/${workspaceId}`);
    }
  }, [
    feature,
    featureId,
    features.length,
    fetchFeatures,
    isFeaturesLoading,
    router,
    searchParamString,
    searchParams,
    workspaceId,
  ]);

  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]">
      <Loader2 className="h-6 w-6 animate-spin text-[var(--accent-primary)]" />
    </div>
  );
}
