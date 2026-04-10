import type { ElementType } from "react";
import {
  Bot,
  BookOpen,
  CheckCircle,
  Clock3,
  FileCode,
  FileText,
  GitBranch,
  Lightbulb,
  ListChecks,
  Loader2,
  MessageSquareText,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import type { Artifact, WorkspaceActivityItem } from "@/stores/workspace";

const artifactIcons: Record<string, ElementType> = {
  hypothesis: Lightbulb,
  literature: BookOpen,
  deep_research_report: SearchCheck,
  literature_review: BookOpen,
  framework_outline: ListChecks,
  outline: ListChecks,
  "research-gap": GitBranch,
  copyright_materials: ShieldCheck,
  technical_description: FileCode,
  patent_outline: ShieldCheck,
  prior_art_report: SearchCheck,
  background_research: BookOpen,
  paper_analysis: GitBranch,
  draft: FileText,
  paper_draft: FileText,
  code: FileCode,
  opening_report: ListChecks,
  feasibility_analysis: CheckCircle,
  thesis_chapter: FileText,
  gap_analysis: Target,
  figure: FileCode,
  research_ideas: Lightbulb,
  literature_search_results: BookOpen,
  default: FileText,
};

const artifactColors: Record<string, string> = {
  hypothesis: "text-amber-500 bg-amber-500/10",
  literature: "text-blue-500 bg-blue-500/10",
  deep_research_report: "text-sky-500 bg-sky-500/10",
  literature_review: "text-blue-500 bg-blue-500/10",
  framework_outline: "text-purple-500 bg-purple-500/10",
  outline: "text-purple-500 bg-purple-500/10",
  "research-gap": "text-rose-500 bg-rose-500/10",
  copyright_materials: "text-violet-500 bg-violet-500/10",
  technical_description: "text-indigo-500 bg-indigo-500/10",
  patent_outline: "text-amber-500 bg-amber-500/10",
  prior_art_report: "text-orange-500 bg-orange-500/10",
  background_research: "text-emerald-500 bg-emerald-500/10",
  paper_analysis: "text-fuchsia-500 bg-fuchsia-500/10",
  draft: "text-emerald-500 bg-emerald-500/10",
  paper_draft: "text-emerald-500 bg-emerald-500/10",
  code: "text-cyan-500 bg-cyan-500/10",
  opening_report: "text-amber-500 bg-amber-500/10",
  feasibility_analysis: "text-green-500 bg-green-500/10",
  thesis_chapter: "text-purple-500 bg-purple-500/10",
  gap_analysis: "text-red-500 bg-red-500/10",
  figure: "text-cyan-500 bg-cyan-500/10",
  research_ideas: "text-amber-500 bg-amber-500/10",
  literature_search_results: "text-blue-500 bg-blue-500/10",
  default: "text-slate-500 bg-slate-500/10",
};

export type ActivityFilter = "all" | WorkspaceActivityItem["kind"];

export const workspaceActivityFilterOptions: Array<{
  value: ActivityFilter;
  label: string;
}> = [
  { value: "all", label: "全部" },
  { value: "feature_task", label: "功能" },
  { value: "chat_thread", label: "对话" },
  { value: "subagent_task", label: "子代理" },
  { value: "artifact", label: "产出" },
];

export function inferActivityModuleId(item: WorkspaceActivityItem): string | null {
  if (item.feature_id) {
    return item.feature_id;
  }

  const createdBySkill =
    typeof item.metadata?.created_by_skill === "string"
      ? item.metadata.created_by_skill
      : null;
  if (!createdBySkill) {
    return null;
  }

  const tail = createdBySkill.includes(".")
    ? createdBySkill.split(".").at(-1) || createdBySkill
    : createdBySkill;
  return tail.replace(/-/g, "_");
}

export function getStatusMeta(status?: string | null): {
  label: string;
  className: string;
  icon: ElementType;
} | null {
  switch (status) {
    case "running":
    case "pending":
    case "in_progress":
      return {
        label: status === "pending" ? "排队中" : "进行中",
        className: "bg-amber-500/10 text-amber-600",
        icon: Loader2,
      };
    case "success":
    case "completed":
      return {
        label: "已完成",
        className: "bg-emerald-500/10 text-emerald-600",
        icon: CheckCircle,
      };
    case "failed":
    case "timed_out":
      return {
        label: "失败",
        className: "bg-red-500/10 text-red-600",
        icon: XCircle,
      };
    case "cancelled":
      return {
        label: "已取消",
        className: "bg-slate-500/10 text-slate-600",
        icon: Clock3,
      };
    case "draft":
    case "review":
    case "final":
      return {
        label: status,
        className: "bg-slate-500/10 text-slate-600",
        icon: FileText,
      };
    default:
      return null;
  }
}

export function getActivityMeta(
  item: WorkspaceActivityItem,
  artifact?: Artifact | null
): {
  label: string;
  icon: ElementType;
  className: string;
} {
  if (item.kind === "artifact") {
    const artifactType =
      typeof item.metadata?.artifact_type === "string"
        ? item.metadata.artifact_type
        : artifact?.type || "default";
    return {
      label: "产出",
      icon: artifactIcons[artifactType] || artifactIcons.default,
      className: artifactColors[artifactType] || artifactColors.default,
    };
  }

  if (item.kind === "feature_task") {
    return {
      label: "功能",
      icon: Sparkles,
      className: "text-blue-500 bg-blue-500/10",
    };
  }

  if (item.kind === "chat_thread") {
    return {
      label: "对话",
      icon: MessageSquareText,
      className: "text-emerald-500 bg-emerald-500/10",
    };
  }

  return {
    label: "子代理",
    icon: Bot,
    className: "text-violet-500 bg-violet-500/10",
  };
}

export function resolveSummary(item: WorkspaceActivityItem) {
  if (item.summary) {
    return item.summary;
  }

  if (item.kind === "chat_thread") {
    const count =
      typeof item.metadata?.message_count === "number"
        ? item.metadata.message_count
        : null;
    return count ? `${count} 条消息` : "会话已更新";
  }

  if (item.kind === "subagent_task") {
    return typeof item.metadata?.prompt === "string"
      ? item.metadata.prompt
      : "子代理任务";
  }

  return "最近活动";
}

export function resolveMetadataLine(
  item: WorkspaceActivityItem,
  featureName?: string,
  resolveSkillLabel?: (skillId: string | null | undefined) => string | null
) {
  if (item.kind === "feature_task") {
    return featureName || item.title;
  }

  if (item.kind === "chat_thread") {
    const skill =
      item.skill ??
      (typeof item.metadata?.skill === "string" ? item.metadata.skill : null);
    const skillName =
      item.skill_name ??
      (typeof item.metadata?.skill_name === "string"
        ? item.metadata.skill_name
        : null);
    const messageCount =
      typeof item.metadata?.message_count === "number"
        ? item.metadata.message_count
        : null;
    const detail = [
      skillName ||
        (resolveSkillLabel ? resolveSkillLabel(skill) : skill?.replace(/-/g, " ") ?? null),
      messageCount ? `${messageCount} 条消息` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return detail || "对话活动";
  }

  if (item.kind === "subagent_task") {
    return item.title || "子代理任务";
  }

  if (item.kind === "artifact") {
    const artifactType =
      typeof item.metadata?.artifact_type === "string"
        ? item.metadata.artifact_type
        : null;
    const skill =
      item.created_by_skill ??
      (typeof item.metadata?.created_by_skill === "string"
        ? item.metadata.created_by_skill
        : null);
    const skillName =
      item.created_by_skill_name ??
      (typeof item.metadata?.created_by_skill_name === "string"
        ? item.metadata.created_by_skill_name
        : null);
    return (
      [
        artifactType?.replace(/[_-]/g, " "),
        skillName || (resolveSkillLabel ? resolveSkillLabel(skill) : skill),
      ]
        .filter(Boolean)
        .join(" · ") || "工作区产出"
    );
  }

  return "活动";
}
