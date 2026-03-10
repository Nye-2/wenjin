"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Lightbulb,
  BookOpen,
  GitBranch,
  ListChecks,
  FileCode,
} from "lucide-react";
import { useWorkspaceStore, Artifact } from "@/stores/workspace";
import { cn } from "@/lib/utils";

const artifactIcons: Record<string, React.ElementType> = {
  hypothesis: Lightbulb,
  literature: BookOpen,
  outline: ListChecks,
  "research-gap": GitBranch,
  draft: FileText,
  code: FileCode,
  default: FileText,
};

const artifactColors: Record<string, string> = {
  hypothesis: "text-amber-500 bg-amber-500/10",
  literature: "text-blue-500 bg-blue-500/10",
  outline: "text-purple-500 bg-purple-500/10",
  "research-gap": "text-rose-500 bg-rose-500/10",
  draft: "text-emerald-500 bg-emerald-500/10",
  code: "text-cyan-500 bg-cyan-500/10",
  default: "text-slate-500 bg-slate-500/10",
};

interface ArtifactItemProps {
  artifact: Artifact;
  index: number;
}

function ArtifactItem({ artifact, index }: ArtifactItemProps) {
  const Icon = artifactIcons[artifact.type] || artifactIcons.default;
  const colorClass = artifactColors[artifact.type] || artifactColors.default;

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="group flex items-start gap-3 p-3 rounded-xl bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-white/10 transition-all cursor-pointer border border-transparent hover:border-white/20"
    >
      <div className={cn("p-2 rounded-lg", colorClass)}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
          {artifact.title || `Untitled ${artifact.type}`}
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 capitalize">
          {artifact.type.replace("-", " ")} &middot; {formatTime(artifact.created_at)}
        </p>
      </div>
    </motion.div>
  );
}

interface KnowledgePanelProps {
  workspaceId: string;
}

export function KnowledgePanel({ workspaceId }: KnowledgePanelProps) {
  const { artifacts, fetchArtifacts, isLoading } = useWorkspaceStore();

  useEffect(() => {
    if (workspaceId) {
      fetchArtifacts(workspaceId);
    }
  }, [workspaceId, fetchArtifacts]);

  return (
    <div className="w-[280px] h-full flex flex-col bg-[var(--glass-bg)] backdrop-blur-xl border-r border-[var(--glass-border)]">
      {/* Header */}
      <div className="p-4 border-b border-[var(--glass-border)]">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-academic-primary" />
          Knowledge
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Research artifacts timeline
        </p>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto p-3">
        <AnimatePresence mode="popLayout">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="w-6 h-6 border-2 border-academic-primary border-t-transparent rounded-full"
              />
            </div>
          ) : artifacts.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No artifacts yet
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Start a conversation to generate research artifacts
              </p>
            </div>
          ) : (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-[19px] top-0 bottom-0 w-px bg-gradient-to-b from-academic-primary/50 via-academic-secondary/30 to-transparent" />

              {/* Artifacts */}
              <div className="space-y-2">
                {artifacts.map((artifact, index) => (
                  <ArtifactItem
                    key={artifact.id}
                    artifact={artifact}
                    index={index}
                  />
                ))}
              </div>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
