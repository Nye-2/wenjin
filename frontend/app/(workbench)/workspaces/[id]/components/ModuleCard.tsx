"use client";

import { useRouter } from "next/navigation";
import {
  FlaskConical,
  BookOpen,
  Search,
  PenTool,
  BarChart3,
  FileText,
  type LucideIcon,
} from "lucide-react";
import type { ModuleStatus } from "@/stores/dashboard";

const iconMap: Record<string, LucideIcon> = {
  flask: FlaskConical,
  book: BookOpen,
  search: Search,
  pen: PenTool,
  chart: BarChart3,
  file: FileText,
};

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  blue: { bg: "bg-blue-50 dark:bg-blue-950/30", border: "border-blue-200 dark:border-blue-800", text: "text-blue-700 dark:text-blue-300" },
  emerald: { bg: "bg-emerald-50 dark:bg-emerald-950/30", border: "border-emerald-200 dark:border-emerald-800", text: "text-emerald-700 dark:text-emerald-300" },
  amber: { bg: "bg-amber-50 dark:bg-amber-950/30", border: "border-amber-200 dark:border-amber-800", text: "text-amber-700 dark:text-amber-300" },
  purple: { bg: "bg-purple-50 dark:bg-purple-950/30", border: "border-purple-200 dark:border-purple-800", text: "text-purple-700 dark:text-purple-300" },
  rose: { bg: "bg-rose-50 dark:bg-rose-950/30", border: "border-rose-200 dark:border-rose-800", text: "text-rose-700 dark:text-rose-300" },
  cyan: { bg: "bg-cyan-50 dark:bg-cyan-950/30", border: "border-cyan-200 dark:border-cyan-800", text: "text-cyan-700 dark:text-cyan-300" },
};

interface Feature {
  id: string;
  name: string;
  description: string;
  icon: string;
  color?: string;
  panel?: string | null;
}

interface ModuleCardProps {
  workspaceId: string;
  feature: Feature;
  moduleStatus?: ModuleStatus;
  route: string;
}

export function ModuleCard({
  workspaceId,
  feature,
  moduleStatus,
  route,
}: ModuleCardProps) {
  const router = useRouter();
  const Icon = iconMap[feature.icon] || FileText;
  const colors = colorMap[feature.color || "blue"];
  const status = moduleStatus?.status || "not_started";

  const actionLabel =
    feature.panel === null
      ? "管理 →"
      : status === "completed"
        ? "查看结果 →"
        : status === "in_progress"
          ? "继续 →"
          : "开始 →";

  return (
    <button
      onClick={() => router.push(`/workspaces/${workspaceId}/${route}`)}
      className={`${colors.bg} ${colors.border} border rounded-xl p-5 text-left hover:shadow-md transition-all cursor-pointer w-full group`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-5 h-5 ${colors.text}`} />
        <h3 className="font-semibold text-[var(--text-primary)]">
          {feature.name}
        </h3>
      </div>
      <p className="text-sm text-[var(--text-secondary)] mb-3 line-clamp-2">
        {feature.description}
      </p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-muted)]">
          {renderSummary(feature.id, moduleStatus?.summary)}
        </span>
        <span className={`text-xs font-medium ${colors.text} group-hover:translate-x-1 transition-transform`}>
          {actionLabel}
        </span>
      </div>
    </button>
  );
}

function renderSummary(
  moduleId: string,
  summary?: Record<string, unknown>
): string {
  if (!summary) return "未开始";
  switch (moduleId) {
    case "deep_research":
      return summary.ideas_count
        ? `${summary.ideas_count} 个研究创意`
        : "未开始";
    case "literature_management":
      return summary.total ? `${summary.total} 篇文献` : "暂无文献";
    case "thesis_writing":
      return summary.outline_done ? "大纲已完成" : "未开始";
    case "figure_generation":
      return summary.figures_count ? `${summary.figures_count} 个图表` : "未开始";
    case "compile_export":
      return summary.last_compile ? "已编译" : "未编译";
    case "opening_research":
      return summary.reports_count ? `${summary.reports_count} 份报告` : "未开始";
    default:
      return "未开始";
  }
}
