"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ClipboardList } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
  FeatureWorkbenchShell,
  TaskFeedbackBanner,
  TaskRuntimePanel,
} from "@/components/workspace";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  joinStringArrayLike,
  readString,
} from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function CopyrightMaterialsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const softwareNameSeed = searchParams.get("software_name");
  const versionSeed = searchParams.get("version");
  const applicantNameSeed = searchParams.get("applicant_name");
  const completionDateSeed = searchParams.get("completion_date");
  const highlightsSeed = searchParams.get("highlights");
  const targetPlatformsSeed = searchParams.get("target_platforms");
  const sourceModulesSeed = searchParams.get("source_modules");

  const [softwareName, setSoftwareName] = useState(() => softwareNameSeed || "");
  const [version, setVersion] = useState(() => versionSeed || "V1.0");
  const [applicantName, setApplicantName] = useState(
    () => applicantNameSeed || "待确认申请主体"
  );

  useEffect(() => {
    if (workspace && !softwareName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setSoftwareName(workspace.name || "");
    }
  }, [workspace, softwareName]);
  const [completionDate, setCompletionDate] = useState(
    () => completionDateSeed || ""
  );
  const [highlights, setHighlights] = useState(() => highlightsSeed || "");
  const [targetPlatforms, setTargetPlatforms] = useState(
    () => targetPlatformsSeed || ""
  );
  const [sourceModules, setSourceModules] = useState(
    () => sourceModulesSeed || ""
  );

  useEffect(() => {
    if (softwareNameSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setSoftwareName(softwareNameSeed);
    }
  }, [softwareNameSeed]);

  useEffect(() => {
    if (versionSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setVersion(versionSeed);
    }
  }, [versionSeed]);

  useEffect(() => {
    if (applicantNameSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setApplicantName(applicantNameSeed);
    }
  }, [applicantNameSeed]);

  useEffect(() => {
    if (completionDateSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setCompletionDate(completionDateSeed);
    }
  }, [completionDateSeed]);

  useEffect(() => {
    if (highlightsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setHighlights(highlightsSeed);
    }
  }, [highlightsSeed]);

  useEffect(() => {
    if (targetPlatformsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTargetPlatforms(targetPlatformsSeed);
    }
  }, [targetPlatformsSeed]);

  useEffect(() => {
    if (sourceModulesSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setSourceModules(sourceModulesSeed);
    }
  }, [sourceModulesSeed]);

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
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

  useEffect(() => {
    const latestSoftwareName = readString(softwareProfile?.software_name);
    if (latestSoftwareName && !softwareName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest software profile when route seed is absent
      setSoftwareName(latestSoftwareName);
    }
  }, [softwareProfile, softwareName]);

  useEffect(() => {
    const latestVersion = readString(softwareProfile?.version);
    if (latestVersion && version === "V1.0" && !versionSeed) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest version when route seed is absent
      setVersion(latestVersion);
    }
  }, [softwareProfile, version, versionSeed]);

  useEffect(() => {
    const latestApplicantName = readString(softwareProfile?.applicant_name);
    if (latestApplicantName && applicantName === "待确认申请主体" && !applicantNameSeed) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest applicant when route seed is absent
      setApplicantName(latestApplicantName);
    }
  }, [softwareProfile, applicantName, applicantNameSeed]);

  useEffect(() => {
    const latestCompletionDate = readString(softwareProfile?.completion_date);
    if (latestCompletionDate && !completionDate) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest completion date when route seed is absent
      setCompletionDate(latestCompletionDate);
    }
  }, [softwareProfile, completionDate]);

  useEffect(() => {
    const latestHighlights = joinStringArrayLike(softwareProfile?.highlights);
    if (latestHighlights && !highlights) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest highlights when route seed is absent
      setHighlights(latestHighlights);
    }
  }, [softwareProfile, highlights]);

  useEffect(() => {
    const latestTargetPlatforms = joinStringArrayLike(softwareProfile?.target_platforms);
    if (latestTargetPlatforms && !targetPlatforms) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest target platforms when route seed is absent
      setTargetPlatforms(latestTargetPlatforms);
    }
  }, [softwareProfile, targetPlatforms]);

  useEffect(() => {
    const latestSourceModules = joinStringArrayLike(softwareProfile?.source_modules);
    if (latestSourceModules && !sourceModules) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest source modules when route seed is absent
      setSourceModules(latestSourceModules);
    }
  }, [softwareProfile, sourceModules]);

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
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="材料准备"
      description="生成软件著作权登记材料清单与核对项"
      icon={ClipboardList}
      iconBgClass="bg-violet-500/10"
      iconClass="text-violet-600 dark:text-violet-400"
      sidebarTitle="基础信息"
      sidebarWidthClassName="lg:w-96"
      sidebarClassName="overflow-y-auto"
      sidebar={
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
      }
    >
      <TaskRuntimePanel
        runtime={runtime}
        isRunning={isRunning}
        status={status}
        error={error}
        title="软著材料运行面板"
        emptyDescription="执行后，这里会显示软件画像、材料清单和核对项。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
