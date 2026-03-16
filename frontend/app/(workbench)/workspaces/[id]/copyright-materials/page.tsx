"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, ClipboardList, FolderCheck } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { cn } from "@/lib/utils";

export default function CopyrightMaterialsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [softwareName, setSoftwareName] = useState("");
  const [version, setVersion] = useState("V1.0");
  const [applicantName, setApplicantName] = useState("");
  const [completionDate, setCompletionDate] = useState("");
  const [highlights, setHighlights] = useState("");
  const [targetPlatforms, setTargetPlatforms] = useState("");
  const [sourceModules, setSourceModules] = useState("");

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "copyright_materials",
  });

  useEffect(() => {
    if (!workspace) return;
    if (!softwareName) {
      setSoftwareName(workspace.name || "");
    }
    if (!applicantName) {
      setApplicantName("待确认申请主体");
    }
  }, [workspace, softwareName, applicantName]);

  const handleGenerate = async () => {
    if (!softwareName.trim()) return;
    await run({
      software_name: softwareName.trim(),
      version: version.trim() || "V1.0",
      applicant_name: applicantName.trim() || undefined,
      completion_date: completionDate.trim() || undefined,
      highlights: highlights.trim() || undefined,
      target_platforms: targetPlatforms.trim() || undefined,
      source_modules: sourceModules.trim() || undefined,
    });
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
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
          <div className="p-2 rounded-lg bg-violet-500/10">
            <ClipboardList className="w-5 h-5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              材料准备
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              生成软件著作权登记材料清单与核对项
            </p>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-96 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            基础信息
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                软件名称 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={softwareName}
                onChange={(e) => setSoftwareName(e.target.value)}
                placeholder="输入软件全称..."
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                版本号
              </label>
              <input
                type="text"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="例如：V1.0"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                申请主体
              </label>
              <input
                type="text"
                value={applicantName}
                onChange={(e) => setApplicantName(e.target.value)}
                placeholder="单位或个人名称"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                开发完成日期
              </label>
              <input
                type="text"
                value={completionDate}
                onChange={(e) => setCompletionDate(e.target.value)}
                placeholder="例如：2026-03-13"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                功能亮点（逗号分隔）
              </label>
              <input
                type="text"
                value={highlights}
                onChange={(e) => setHighlights(e.target.value)}
                placeholder="例如：实时分析,报告导出,权限控制"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                目标平台（逗号分隔）
              </label>
              <input
                type="text"
                value={targetPlatforms}
                onChange={(e) => setTargetPlatforms(e.target.value)}
                placeholder="例如：Web,Desktop,Server"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                代码模块（逗号分隔）
              </label>
              <input
                type="text"
                value={sourceModules}
                onChange={(e) => setSourceModules(e.target.value)}
                placeholder="例如：登录鉴权,数据处理,报表导出"
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50"
              />
            </div>

            <button
              className={cn(
                "w-full py-2.5 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors font-medium",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成材料清单"}
            </button>

            {error && (
              <p className="text-xs text-red-500 mt-1">{error}</p>
            )}
            {status && !error && (
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                {status}
              </p>
            )}
          </div>
        </aside>

        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center max-w-md">
              <FolderCheck className="w-16 h-16 text-violet-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                软著材料清单生成
              </h2>
              <p className="text-[var(--text-secondary)] mb-4">
                系统将输出申请表、源代码页、说明书、权属证明和核对清单，帮助你快速完成提交前准备。
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
