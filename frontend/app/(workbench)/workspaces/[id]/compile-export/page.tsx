"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText, Download, FileDown } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { cn } from "@/lib/utils";

export default function CompileExportPage() {
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
          <div className="p-2 rounded-lg bg-rose-500/10">
            <FileText className="w-5 h-5 text-rose-600 dark:text-rose-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              编译导出
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              LaTeX 编译 · 多格式导出
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Config */}
        <aside className="w-72 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            编译配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                LaTeX 模板
              </label>
              <select className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50">
                <option value="default">默认模板</option>
                <option value="ieee">IEEE 格式</option>
                <option value="acm">ACM 格式</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                编译器
              </label>
              <select className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50">
                <option value="xelatex">XeLaTeX</option>
                <option value="pdflatex">PDFLaTeX</option>
                <option value="lualatex">LuaLaTeX</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                参考文献格式
              </label>
              <select className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50">
                <option value="gbt7714">GB/T 7714</option>
                <option value="apa">APA</option>
                <option value="mla">MLA</option>
              </select>
            </div>

            <button className="w-full py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors flex items-center justify-center gap-2">
              <FileDown className="w-4 h-4" />
              编译 PDF
            </button>
          </div>

          {/* Export Options */}
          <div className="mt-6 pt-6 border-t border-[var(--border-default)]">
            <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
              导出格式
            </h3>
            <div className="space-y-2">
              {["PDF", "Word (.docx)", "LaTeX (.tex)", "Markdown"].map((format) => (
                <button
                  key={format}
                  className="w-full flex items-center gap-2 p-2 bg-[var(--bg-elevated)] rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
                >
                  <Download className="w-4 h-4" />
                  {format}
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* Main Area - PDF Preview */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center">
              <FileText className="w-16 h-16 text-rose-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                PDF 预览
              </h2>
              <p className="text-[var(--text-secondary)]">
                编译后在此处预览 PDF
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
