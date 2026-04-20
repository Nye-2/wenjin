// frontend/components/workspace/ArtifactLibrary.tsx

"use client";

import { motion } from "framer-motion";
import {
  FileText,
  BookOpen,
  BarChart3,
  Download,
  File,
  ChevronRight,
  SearchCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspaceStore, Artifact } from "@/stores/workspace";

// Icon映射
const artifactIconMap: Record<string, LucideIcon> = {
  outline: FileText,
  abstract: FileText,
  deep_research_report: SearchCheck,
  literature_review: BookOpen,
  chapter: FileText,
  figure: BarChart3,
  table: BarChart3,
  research_idea: FileText,
  methodology: FileText,
  framework_outline: FileText,
  results_analysis: BarChart3,
  conclusion: FileText,
  note: File,
};

// 颜色映射
const artifactColorMap: Record<string, string> = {
  outline: "text-purple-500 bg-purple-500/10",
  abstract: "text-blue-500 bg-blue-500/10",
  deep_research_report: "text-sky-500 bg-sky-500/10",
  literature_review: "text-emerald-500 bg-emerald-500/10",
  chapter: "text-amber-500 bg-amber-500/10",
  figure: "text-rose-500 bg-rose-500/10",
  table: "text-cyan-500 bg-cyan-500/10",
};

interface ArtifactLibraryProps {
  onSelectArtifact: (artifact: Artifact) => void;
  onExport?: () => void;
  embedded?: boolean;
}

export function ArtifactLibrary({
  onSelectArtifact,
  onExport,
  embedded = false,
}: ArtifactLibraryProps) {
  const artifacts = useWorkspaceStore((state) => state.artifacts);

  // 按类型分组并排序
  const groupedArtifacts = artifacts.reduce((acc, artifact) => {
    const type = artifact.type || "default";
    if (!acc[type]) acc[type] = [];
    acc[type].push(artifact);
    return acc;
  }, {} as Record<string, Artifact[]>);

  // 显示顺序（可扩展）
  const typeOrder = [
    "outline",
    "abstract",
    "deep_research_report",
    "literature_review",
    "methodology",
    "chapter",
    "figure",
    "table",
    "results_analysis",
    "conclusion",
    "note",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div
        className={cn(
          "border-b border-[var(--border-default)]",
          embedded ? "px-3 py-3" : "px-4 py-4"
        )}
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          证据与成果
        </h3>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {artifacts.length} 项已沉淀内容
        </p>
      </div>

      {/* 成果列表 */}
      <div className={cn("flex-1 overflow-y-auto", embedded ? "p-1.5" : "p-2")}>
        {artifacts.length === 0 ? (
          <div className="text-center py-8 text-[var(--text-muted)]">
            <File className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-xs">还没有沉淀成果</p>
            <p className="text-xs">继续主线任务后，结果会汇总到这里</p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* 按顺序显示 */}
            {typeOrder.map((type) => {
              const items = groupedArtifacts[type];
              if (!items || items.length === 0) return null;

              const Icon = artifactIconMap[type] || File;
              const colorClass =
                artifactColorMap[type] ||
                "text-[var(--text-muted)] bg-[var(--bg-surface)]";

              return items.map((artifact) => (
                <motion.button
                  key={artifact.id}
                  onClick={() => onSelectArtifact(artifact)}
                  className={cn(
                    "w-full flex items-center gap-3 rounded-2xl px-3 py-3",
                    "text-left hover:bg-[var(--bg-surface)] transition-colors"
                  )}
                  whileHover={{ x: 2 }}
                >
                  <div className={cn("p-1.5 rounded-lg", colorClass)}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--text-primary)] truncate">
                      {artifact.title || type}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">{type}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                </motion.button>
              ));
            })}

            {/* 其他未分类类型 */}
            {Object.entries(groupedArtifacts)
              .filter(([type]) => !typeOrder.includes(type))
              .map(([type, items]) =>
                items.map((artifact) => (
                  <motion.button
                    key={artifact.id}
                    onClick={() => onSelectArtifact(artifact)}
                  className={cn(
                      "w-full flex items-center gap-3 rounded-2xl px-3 py-3",
                      "text-left hover:bg-[var(--bg-surface)] transition-colors"
                    )}
                    whileHover={{ x: 2 }}
                  >
                    <div className="p-1.5 rounded-lg text-[var(--text-muted)] bg-[var(--bg-surface)]">
                      <File className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[var(--text-primary)] truncate">
                        {artifact.title || type}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">{type}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                  </motion.button>
                ))
              )}
          </div>
        )}
      </div>

      {/* 导出按钮 */}
      {onExport && artifacts.length > 0 && (
        <div className="p-3 border-t border-[var(--border-default)]">
          <button
            onClick={onExport}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-[var(--brand-navy)] to-[var(--brand-teal)] px-4 py-3 text-sm font-medium text-white transition-colors hover:opacity-95"
          >
            <Download className="w-4 h-4" />
            导出PDF
          </button>
        </div>
      )}
    </div>
  );
}
