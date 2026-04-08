// frontend/components/workspace/QuickActions.tsx

"use client";

import { motion } from "framer-motion";
import {
  ListOrdered,
  BookOpen,
  PenTool,
  BarChart3,
  FileText,
  Download,
  Search,
  FlaskConical,
  FileEdit,
  Lightbulb,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task";
import { useFeaturesStore } from "@/stores/features";

// Icon映射表 - 将icon name string映射到组件
const iconMap: Record<string, LucideIcon> = {
  list: ListOrdered,
  book: BookOpen,
  pen: PenTool,
  chart: BarChart3,
  file: FileText,
  download: Download,
  search: Search,
  flask: FlaskConical,
  edit: FileEdit,
  lightbulb: Lightbulb,
};

// 颜色映射表
const colorMap: Record<string, string> = {
  purple: "text-purple-500",
  blue: "text-blue-500",
  emerald: "text-emerald-500",
  amber: "text-amber-500",
  cyan: "text-cyan-500",
  rose: "text-rose-500",
  indigo: "text-indigo-500",
};

interface QuickActionsProps {
  workspaceId?: string;
  onAction: (featureId: string) => void;
  featureIds?: string[];
  maxItems?: number;
}

export function QuickActions({
  workspaceId,
  onAction,
  featureIds,
  maxItems = 5,
}: QuickActionsProps) {
  const { features } = useFeaturesStore();
  const isExecuting = useTaskStore(
    (state) => state.getWorkspaceTaskState(workspaceId).isExecuting
  );
  const orderedFeatures = (() => {
    if (featureIds && featureIds.length > 0) {
      const preferredOrder = new Map(
        featureIds.map((featureId, index) => [featureId, index])
      );
      return features
        .filter((feature) => preferredOrder.has(feature.id))
        .sort(
          (left, right) =>
            (preferredOrder.get(left.id) ?? Number.MAX_SAFE_INTEGER) -
            (preferredOrder.get(right.id) ?? Number.MAX_SAFE_INTEGER)
        );
    }
    return features.slice(0, maxItems);
  })();

  const handleAction = (featureId: string) => {
    if (isExecuting) return;
    onAction(featureId);
  };

  if (orderedFeatures.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {orderedFeatures.slice(0, maxItems).map((feature) => {
        const Icon = iconMap[feature.icon] || FileText;
        const colorClass = colorMap[feature.color || ""] || "text-[var(--text-primary)]";
        const isDisabled = isExecuting;

        return (
          <motion.button
            key={feature.id}
            onClick={() => handleAction(feature.id)}
            disabled={isDisabled}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
              "border border-[var(--border-default)] transition-all duration-200",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              isDisabled
                ? "bg-[var(--bg-surface)] text-[var(--text-muted)]"
                : cn(
                    "bg-[var(--bg-surface)]",
                    "hover:bg-[var(--bg-muted)]",
                    colorClass
                  )
            )}
            whileHover={isDisabled ? {} : { scale: 1.02 }}
            whileTap={isDisabled ? {} : { scale: 0.98 }}
            title={isDisabled ? "请等待当前任务完成" : feature.description}
          >
            <Icon className="w-3.5 h-3.5" />
            {feature.name}
          </motion.button>
        );
      })}
    </div>
  );
}
