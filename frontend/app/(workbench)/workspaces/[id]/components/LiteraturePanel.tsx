"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Upload,
  ExternalLink,
  Calendar,
  Users,
  BookOpen,
} from "lucide-react";
import { useWorkspaceStore, Paper } from "@/stores/workspace";
import { cn } from "@/lib/utils";

interface PaperItemProps {
  paper: Paper;
  index: number;
}

function PaperItem({ paper, index }: PaperItemProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="group p-3 rounded-xl bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-white/10 transition-all cursor-pointer border border-transparent hover:border-white/20"
    >
      {/* Title */}
      <h4 className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-2 mb-2">
        {paper.title}
      </h4>

      {/* Authors */}
      {paper.authors.length > 0 && (
        <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 mb-1">
          <Users className="w-3 h-3" />
          <span className="truncate">
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 && ` +${paper.authors.length - 3}`}
          </span>
        </div>
      )}

      {/* Year and Venue */}
      <div className="flex items-center gap-3 text-xs text-slate-400 dark:text-slate-500">
        {paper.year && (
          <div className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            <span>{paper.year}</span>
          </div>
        )}
        {paper.venue && (
          <div className="flex items-center gap-1">
            <BookOpen className="w-3 h-3" />
            <span className="truncate">{paper.venue}</span>
          </div>
        )}
      </div>

      {/* Hover actions */}
      <div className="mt-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button className="text-xs text-academic-primary hover:text-academic-primary/80 flex items-center gap-1">
          <ExternalLink className="w-3 h-3" />
          View
        </button>
      </div>
    </motion.div>
  );
}

interface LiteraturePanelProps {
  workspaceId: string;
}

export function LiteraturePanel({ workspaceId }: LiteraturePanelProps) {
  const { papers, fetchPapers, isLoading } = useWorkspaceStore();

  useEffect(() => {
    if (workspaceId) {
      fetchPapers(workspaceId);
    }
  }, [workspaceId, fetchPapers]);

  const handleUpload = () => {
    // Placeholder for upload functionality
    console.log("Upload paper - to be implemented");
  };

  return (
    <div className="w-[320px] h-full flex flex-col bg-[var(--glass-bg)] backdrop-blur-xl border-l border-[var(--glass-border)]">
      {/* Header */}
      <div className="p-4 border-b border-[var(--glass-border)]">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <FileText className="w-5 h-5 text-academic-primary" />
            Literature
          </h2>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleUpload}
            className={cn(
              "p-2 rounded-lg",
              "bg-academic-primary/10 hover:bg-academic-primary/20",
              "text-academic-primary transition-colors"
            )}
          >
            <Upload className="w-4 h-4" />
          </motion.button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          {papers.length} paper{papers.length !== 1 ? "s" : ""} in workspace
        </p>
      </div>

      {/* Papers List */}
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
          ) : papers.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No papers yet
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Upload papers to build your reference library
              </p>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleUpload}
                className={cn(
                  "mt-4 px-4 py-2 rounded-lg text-sm font-medium",
                  "bg-academic-primary/10 text-academic-primary",
                  "hover:bg-academic-primary/20 transition-colors"
                )}
              >
                <Upload className="w-4 h-4 inline mr-2" />
                Upload Paper
              </motion.button>
            </div>
          ) : (
            <div className="space-y-2">
              {papers.map((paper, index) => (
                <PaperItem key={paper.id} paper={paper} index={index} />
              ))}
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
