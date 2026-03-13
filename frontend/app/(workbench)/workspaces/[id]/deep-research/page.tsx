"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FlaskConical, Loader2 } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { cn } from "@/lib/utils";

export default function DeepResearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-14 flex items-center gap-4 px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => router.push(`/workspaces/${workspaceId}`)}
          className={cn(
            "p-2 rounded-lg",
            "bg-[var(--bg-surface)]",
            "hover:bg-[var(--bg-muted)]",
            "text-[var(--text-secondary)]",
            "transition-colors"
          )}
        >
          <ArrowLeft className="w-5 h-5" />
        </motion.button>

        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-blue-500/10">
            <FlaskConical className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              Deep Research
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              深度文献调研与研究创意探索
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            <FlaskConical className="w-16 h-16 text-blue-500 mx-auto mb-4 opacity-50" />
            <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
              Deep Research 工作区
            </h2>
            <p className="text-[var(--text-secondary)] mb-6 max-w-md mx-auto">
              输入研究主题，AI 将自动检索相关文献、分析研究空白、生成研究创意
            </p>
            <div className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl p-6">
              <p className="text-sm text-[var(--text-muted)]">
                功能开发中...
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
