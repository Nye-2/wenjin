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
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspaceStore, Artifact } from "@/stores/workspace";

// Icon映射
const artifactIconMap: Record<string, LucideIcon> = {
  outline: FileText,
  abstract: FileText,
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
  literature_review: "text-emerald-500 bg-emerald-500/10",
  chapter: "text-amber-500 bg-amber-500/10",
  figure: "text-rose-500 bg-rose-500/10",
  table: "text-cyan-500 bg-cyan-500/10",
};

interface ArtifactLibraryProps {
  onSelectArtifact: (artifact: Artifact) => void;
  onExport?: () => void;
}

export function ArtifactLibrary({
  onSelectArtifact,
  onExport,
}: ArtifactLibraryProps) {
  const { artifacts } = useWorkspaceStore();

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
      <div className="px-4 py-3 border-b border-[var(--border-default)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          成果库
        </h3>
        <p className="text-xs text-[var(--text-muted)] mt-0.5">
          {artifacts.length} 个成果
        </p>
      </div>

      {/* 成果列表 */}
      <div className="flex-1 overflow-y-auto p-2">
        {artifacts.length === 0 ? (
          <div className="text-center py-8 text-[var(--text-muted)]">
            <File className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-xs">暂无成果</p>
            <p className="text-xs">开始对话以生成内容</p>
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
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg",
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
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg",
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
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent-primary)] text-white text-sm font-medium hover:bg-[var(--accent-primary)]/90 transition-colors"
          >
            <Download className="w-4 h-4" />
            导出PDF
          </button>
        </div>
      )}
    </div>
  );
}
