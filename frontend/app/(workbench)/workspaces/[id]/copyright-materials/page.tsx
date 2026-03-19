"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, ClipboardList } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import { findLatestArtifact, getArtifactContentRecord, readString } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function CopyrightMaterialsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const [softwareName, setSoftwareName] = useState("");
  const [version, setVersion] = useState("V1.0");
  const [applicantName, setApplicantName] = useState("待确认申请主体");

  useEffect(() => {
    if (workspace && !softwareName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setSoftwareName(workspace.name || "");
    }
  }, [workspace, softwareName]);
  const [completionDate, setCompletionDate] = useState("");
  const [highlights, setHighlights] = useState("");
  const [targetPlatforms, setTargetPlatforms] = useState("");
  const [sourceModules, setSourceModules] = useState("");

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
    workspaceId,
    featureId: "copyright_materials",
  });

  const latestMaterialsArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["copyright_materials"]),
    [artifacts]
  );
  const latestMaterialsResult = useMemo(
    () => getArtifactContentRecord(latestMaterialsArtifact) ?? latestTaskResult,
    [latestMaterialsArtifact, latestTaskResult]
  );
  const softwareProfile =
    latestMaterialsResult?.software_profile &&
    typeof latestMaterialsResult.software_profile === "object"
      ? (latestMaterialsResult.software_profile as Record<string, unknown>)
      : null;
  const requiredMaterials = Array.isArray(latestMaterialsResult?.required_materials)
    ? latestMaterialsResult.required_materials
    : [];
  const reviewChecklist = Array.isArray(latestMaterialsResult?.review_checklist)
    ? latestMaterialsResult.review_checklist
    : [];
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestMaterialsResult
      ? "最近一次软著材料清单已生成，可继续补技术说明书和提交材料。"
      : "本工作区用于生成软著登记所需材料清单与核对项。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["软件名称", softwareName],
          ["版本", version],
          ["申请主体", applicantName],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始生成材料清单。",
        }),
      },
      {
        title: "最近清单结果",
        content: latestMaterialsResult
          ? [
              softwareProfile
                ? describeFields([
                    ["软件", readString(softwareProfile.software_name)],
                    ["版本", readString(softwareProfile.version)],
                  ])
                : null,
              `必备材料：${requiredMaterials.length}`,
              `核对项：${reviewChecklist.length}`,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次清单摘要。",
      },
    ],
    nextActions: [
      "确认软件基本信息后生成材料清单。",
      "补齐源代码页与主体证明材料。",
      "联动 technical-description 完成说明书主文档。",
    ],
    outputLanguage: "zh",
  });

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

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleGenerate}
            />
          </div>
        </aside>

        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full"
          >
            <WorkspaceResultPanel viewModel={resultViewModel} />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
