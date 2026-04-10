"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Play } from "lucide-react";

import { getWorkspaceFeatureChatRoute } from "@/lib/workspace-feature-routes";
import { cn } from "@/lib/utils";
import { useFeaturesStore } from "@/stores/features";

interface CompileFeatureButtonProps {
  workspaceId: string;
  featureId?: string;
  params?: Record<
    string,
    string | number | boolean | Array<string | number | boolean> | null | undefined
  >;
  label?: string;
  className?: string;
  disabled?: boolean;
  onBeforeRun?: () => Promise<void> | void;
  onError?: (message: string | null) => void;
}

export function CompileFeatureButton({
  workspaceId,
  featureId = "compile_export",
  params = {},
  label = "一键编译",
  className,
  disabled = false,
  onBeforeRun,
  onError,
}: CompileFeatureButtonProps) {
  const router = useRouter();
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClick = async () => {
    const feature = getFeatureById(featureId);
    onError?.(null);
    setIsSubmitting(true);

    try {
      await onBeforeRun?.();

      const chatRoute = getWorkspaceFeatureChatRoute(workspaceId, featureId, {
        ...(feature?.defaultSkillId ? { skill: feature.defaultSkillId } : {}),
        ...params,
      });
      if (!chatRoute) {
        throw new Error("当前工作区没有可用的编译入口。");
      }

      router.push(chatRoute);
    } catch (error) {
      onError?.(
        error instanceof Error ? error.message : "编译入口跳转失败"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || isSubmitting}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl bg-[var(--brand-navy)] px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60",
        className
      )}
    >
      {isSubmitting ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Play className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}
