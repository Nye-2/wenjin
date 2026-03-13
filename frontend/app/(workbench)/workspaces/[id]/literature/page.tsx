"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, Plus, Search, Filter } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useLiteratureStore } from "@/stores/literature";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export default function LiteraturePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();
  const { items, total, coreCount, isLoading, fetchLiterature } = useLiteratureStore();
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (workspaceId) {
      fetchLiterature(workspaceId);
    }
  }, [workspaceId, fetchLiterature]);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-14 flex items-center justify-between px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <div className="flex items-center gap-4">
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
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <BookOpen className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--text-primary)]">
                文献管理
              </h1>
              <p className="text-xs text-[var(--text-muted)]">
                管理研究参考文献
              </p>
            </div>
          </div>
        </div>

        <button className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors">
          <Plus className="w-4 h-4" />
          添加文献
        </button>
      </header>

      {/* Stats Bar */}
      <div className="flex items-center gap-6 px-6 py-3 bg-[var(--bg-surface)] border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-[var(--text-primary)]">{total}</span>
          <span className="text-sm text-[var(--text-muted)]">篇文献</span>
        </div>
        <div className="w-px h-6 bg-[var(--border-default)]" />
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-amber-600">{coreCount}</span>
          <span className="text-sm text-[var(--text-muted)]">篇核心文献</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 px-6 py-3 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder="搜索文献..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        <button className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]">
          <Filter className="w-4 h-4" />
          筛选
        </button>
      </div>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full"
            />
          </div>
        ) : items.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            <BookOpen className="w-16 h-16 text-emerald-500 mx-auto mb-4 opacity-50" />
            <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
              暂无文献
            </h2>
            <p className="text-[var(--text-secondary)] mb-6">
              添加文献或从 Deep Research 导入
            </p>
          </motion.div>
        ) : (
          <div className="space-y-3">
            {items.map((lit, idx) => (
              <motion.div
                key={lit.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="p-4 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl hover:border-emerald-500/30 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-medium text-[var(--text-primary)] mb-1">
                      {lit.title}
                    </h3>
                    <p className="text-sm text-[var(--text-muted)]">
                      {lit.authors.join(", ")} · {lit.year || "未知年份"}
                    </p>
                  </div>
                  {lit.is_core && (
                    <span className="px-2 py-1 text-xs bg-amber-500/10 text-amber-600 rounded">
                      核心
                    </span>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
