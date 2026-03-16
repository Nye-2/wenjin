"use client";

import { useRouter } from "next/navigation";
import {
  FlaskConical,
  BookOpen,
  Search,
  PenTool,
  BarChart3,
  FileText,
  ListChecks,
  AlertCircle,
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
  list: ListChecks,
};

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  blue: { bg: "bg-blue-50 dark:bg-blue-950/30", border: "border-blue-200 dark:border-blue-800", text: "text-blue-700 dark:text-blue-300" },
  emerald: { bg: "bg-emerald-50 dark:bg-emerald-950/30", border: "border-emerald-200 dark:border-emerald-800", text: "text-emerald-700 dark:text-emerald-300" },
  amber: { bg: "bg-amber-50 dark:bg-amber-950/30", border: "border-amber-200 dark:border-amber-800", text: "text-amber-700 dark:text-amber-300" },
  purple: { bg: "bg-purple-50 dark:bg-purple-950/30", border: "border-purple-200 dark:border-purple-800", text: "text-purple-700 dark:text-purple-300" },
  rose: { bg: "bg-rose-50 dark:bg-rose-950/30", border: "border-rose-200 dark:border-rose-800", text: "text-rose-700 dark:text-rose-300" },
  cyan: { bg: "bg-cyan-50 dark:bg-cyan-950/30", border: "border-cyan-200 dark:border-cyan-800", text: "text-cyan-700 dark:text-cyan-300" },
  violet: { bg: "bg-violet-50 dark:bg-violet-950/30", border: "border-violet-200 dark:border-violet-800", text: "text-violet-700 dark:text-violet-300" },
  indigo: { bg: "bg-indigo-50 dark:bg-indigo-950/30", border: "border-indigo-200 dark:border-indigo-800", text: "text-indigo-700 dark:text-indigo-300" },
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
  const colors = colorMap[feature.color || "blue"] ?? colorMap.blue;
  const status = moduleStatus?.status || "not_started";
  const hasRoute = Boolean(route);

  const actionLabel =
    feature.panel === null
      ? "管理 →"
      : status === "failed"
        ? "重试 →"
        : status === "completed"
          ? "查看结果 →"
          : status === "in_progress"
            ? "继续 →"
            : "开始 →";

  const handleClick = () => {
    if (hasRoute) {
      router.push(`/workspaces/${workspaceId}/${route}`);
    } else {
      // 没有专属路由时退回 workspace 主视图，后续可按 workspace/feature 微调
      router.push(`/workspaces/${workspaceId}`);
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`${colors.bg} ${colors.border} border rounded-xl p-5 text-left hover:shadow-md transition-all cursor-pointer w-full group`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-5 h-5 ${colors.text}`} />
        <h3 className="font-semibold text-[var(--text-primary)]">
          {feature.name}
        </h3>
        {status === "failed" && (
          <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
            <AlertCircle className="w-3.5 h-3.5" />
            失败
          </span>
        )}
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

  const num = (value: unknown): number => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : 0;
    }
    return 0;
  };

  const bool = (value: unknown): boolean => value === true;

  switch (moduleId) {
    case "deep_research":
      return num(summary.ideas_count)
        ? `${num(summary.ideas_count)} 个研究创意`
        : "未开始";
    case "literature_management":
      return num(summary.total) ? `${num(summary.total)} 篇文献` : "暂无文献";
    case "thesis_writing":
      return bool(summary.outline_done) ? "大纲已完成" : "未开始";
    case "figure_generation":
      return num(summary.figures_count) ? `${num(summary.figures_count)} 个图表` : "未开始";
    case "compile_export":
      if (!summary.last_compile) return "未编译";
      if (summary.compile_status === "success") return "已编译";
      if (summary.compile_status === "failed") return "最近编译失败";
      return "已生成编译稿";
    case "opening_research":
      return num(summary.reports_count) ? `${num(summary.reports_count)} 份报告` : "未开始";
    case "literature_search":
      return num(summary.results_count)
        ? `${num(summary.results_count)} 条检索结果`
        : "未开始";
    case "paper_analysis":
      return num(summary.analysis_count)
        ? `${num(summary.analysis_count)} 份分析`
        : "未开始";
    case "writing":
      return num(summary.drafts_count)
        ? `${num(summary.drafts_count)} 份草稿`
        : "未开始";
    case "proposal_outline":
      return bool(summary.has_outline) || num(summary.count) > 0 || num(summary.outline_count) > 0
        ? `${num(summary.count) || num(summary.outline_count) || 1} 份大纲`
        : "未开始";
    case "background_research":
      return num(summary.count) > 0 || num(summary.research_count) > 0
        ? `${num(summary.count) || num(summary.research_count)} 份调研`
        : "未开始";
    case "copyright_materials":
      return bool(summary.has_materials) ? "已生成材料清单" : "未开始";
    case "technical_description":
      return bool(summary.has_description) ? "说明书已生成" : "未开始";
    case "patent_outline":
      return bool(summary.has_outline) ? "专利框架已生成" : "未开始";
    case "prior_art_search":
      return num(summary.reports_count) ? `${num(summary.reports_count)} 份检索报告` : "未开始";
    default:
      return "未开始";
  }
}
