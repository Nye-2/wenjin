"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  FileText,
  Lightbulb,
  BookOpen,
  SearchCheck,
  ListChecks,
  FileCode,
  ClipboardList,
  CheckCircle,
  Target,
} from "lucide-react";
import type { Artifact } from "@/stores/workspace";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";

const artifactIcons: Record<string, React.ElementType> = {
  hypothesis: Lightbulb,
  literature: BookOpen,
  deep_research_report: SearchCheck,
  literature_review: BookOpen,
  framework_outline: ListChecks,
  outline: ListChecks,
  opening_report: ClipboardList,
  feasibility_analysis: CheckCircle,
  thesis_chapter: FileText,
  gap_analysis: Target,
  figure: FileCode,
  research_ideas: Lightbulb,
  paper_draft: FileText,
  default: FileText,
};

const artifactColors: Record<string, string> = {
  hypothesis: "text-amber-500",
  literature: "text-blue-500",
  deep_research_report: "text-sky-500",
  literature_review: "text-blue-500",
  framework_outline: "text-purple-500",
  outline: "text-purple-500",
  opening_report: "text-amber-500",
  feasibility_analysis: "text-green-500",
  thesis_chapter: "text-purple-500",
  gap_analysis: "text-red-500",
  figure: "text-cyan-500",
  research_ideas: "text-amber-500",
  paper_draft: "text-emerald-500",
  default: "text-slate-500",
};

interface RecentArtifactsProps {
  artifacts: Artifact[];
}

export function RecentArtifacts({ artifacts }: RecentArtifactsProps) {
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);

  if (artifacts.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--text-muted)]">
        <FileText className="w-10 h-10 mx-auto mb-2 opacity-50" />
        <p className="text-sm">暂无产出物</p>
      </div>
    );
  }

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 7) return `${diffDays} 天前`;
    return date.toLocaleDateString("zh-CN");
  };

  return (
    <>
      <div className="space-y-2">
        {artifacts.slice(0, 5).map((artifact, index) => {
          const Icon = artifactIcons[artifact.type] || artifactIcons.default;
          const colorClass = artifactColors[artifact.type] || artifactColors.default;

          return (
            <motion.button
              type="button"
              key={artifact.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => setSelectedArtifact(artifact)}
              className="flex w-full items-center gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-left transition-colors hover:bg-[var(--bg-muted)]"
            >
              <div className={`p-2 rounded-lg bg-[var(--bg-elevated)]`}>
                <Icon className={`w-4 h-4 ${colorClass}`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                  {artifact.title || `未命名 ${artifact.type}`}
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  {artifact.type.replace(/_/g, " ")} · {formatTime(artifact.created_at)}
                </p>
              </div>
            </motion.button>
          );
        })}
      </div>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null);
          }
        }}
      />
    </>
  );
}
