"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { PenTool } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
  FeatureWorkbenchShell,
  TaskFeedbackBanner,
  TaskRuntimePanel,
} from "@/components/workspace";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readString,
  readStringList,
} from "@/lib/artifact-utils";

const SECTION_OPTIONS = [
  { value: "abstract", label: "摘要" },
  { value: "introduction", label: "引言" },
  { value: "related_work", label: "相关工作" },
  { value: "methodology", label: "方法" },
  { value: "experiments", label: "实验" },
  { value: "results", label: "结果分析" },
  { value: "discussion", label: "讨论" },
  { value: "conclusion", label: "结论" },
];

export default function SciWritingPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const paperTitleSeed = searchParams.get("paper_title");
  const sectionTypeSeed = searchParams.get("section_type");
  const targetWordsSeed = searchParams.get("target_words");
  const contextArtifactIdsSeed = searchParams.get("context_artifact_ids");

  const [paperTitle, setPaperTitle] = useState(() => paperTitleSeed || "");
  const [sectionType, setSectionType] = useState(() =>
    SECTION_OPTIONS.some((option) => option.value === sectionTypeSeed)
      ? (sectionTypeSeed as string)
      : "introduction"
  );

  useEffect(() => {
    if (workspace && !paperTitle) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setPaperTitle((workspace.description || workspace.name || "").toString().trim());
    }
  }, [workspace, paperTitle]);
  const [targetWords, setTargetWords] = useState(() => {
    const parsed = Number(targetWordsSeed);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1200;
  });
  const [contextArtifactIds, setContextArtifactIds] = useState(
    () => contextArtifactIdsSeed || ""
  );

  useEffect(() => {
    if (paperTitleSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setPaperTitle(paperTitleSeed);
    }
  }, [paperTitleSeed]);

  useEffect(() => {
    if (SECTION_OPTIONS.some((option) => option.value === sectionTypeSeed)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setSectionType(sectionTypeSeed as string);
    }
  }, [sectionTypeSeed]);

  useEffect(() => {
    const parsed = Number(targetWordsSeed);
    if (Number.isFinite(parsed) && parsed > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTargetWords(parsed);
    }
  }, [targetWordsSeed]);

  useEffect(() => {
    if (contextArtifactIdsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setContextArtifactIds(contextArtifactIdsSeed);
    }
  }, [contextArtifactIdsSeed]);

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "writing",
  });
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
    isLoading: isModelLoading,
    loadError: modelLoadError,
  } = useModelSelection({
    purpose: "writing",
    persistenceKey: `workspace:${workspaceId}:model:writing`,
  });

  const sectionHint = useMemo(() => {
    const current = SECTION_OPTIONS.find((option) => option.value === sectionType);
    return current?.label || "章节";
  }, [sectionType]);

  const parseArtifactIds = (): string[] => {
    return contextArtifactIds
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const latestDraftArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["paper_draft"]),
    [artifacts]
  );
  const latestDraftResult = useMemo(
    () => getArtifactContentRecord(latestDraftArtifact) ?? latestTaskResult,
    [latestDraftArtifact, latestTaskResult]
  );
  const latestDraftContent = readString(latestDraftResult?.content);
  const latestDraftSectionTitle =
    readString(latestDraftResult?.section_title) ?? sectionHint;
  const latestDraftReferences = readStringList(latestDraftResult?.references, 3);
  const latestDraftWordCount =
    typeof latestDraftResult?.word_count === "number"
      ? latestDraftResult.word_count
      : null;

  useEffect(() => {
    const latestPaperTitle = readString(latestDraftResult?.paper_title);
    if (latestPaperTitle && !paperTitle) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest writing input when route seed is absent
      setPaperTitle(latestPaperTitle);
    }
  }, [latestDraftResult, paperTitle]);

  useEffect(() => {
    const latestSectionType = readString(latestDraftResult?.section_type);
    if (
      latestSectionType &&
      !sectionTypeSeed &&
      SECTION_OPTIONS.some((option) => option.value === latestSectionType)
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest section when route seed is absent
      setSectionType(latestSectionType);
    }
  }, [latestDraftResult, sectionTypeSeed]);

  useEffect(() => {
    const latestTargetWords =
      typeof latestDraftResult?.target_words === "number"
        ? latestDraftResult.target_words
        : null;
    if (latestTargetWords && !targetWordsSeed) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest target words when route seed is absent
      setTargetWords(latestTargetWords);
    }
  }, [latestDraftResult, targetWordsSeed]);

  const resultViewModel: WorkspaceResultViewModel = useMemo(
    () => createWorkspaceResultViewModel({
      summary: latestDraftResult
        ? `最近一次已生成 ${latestDraftSectionTitle} 草稿，可继续在知识区查看完整内容并迭代写作。`
        : `当前为 SCI ${sectionHint}写作工作区。执行后将生成可编辑的 paper_draft 产出，并沉淀到知识区。`,
      sections: [
        {
          title: "本次写作参数",
          content: describeFields([
            ["标题", paperTitle],
            ["章节", sectionHint],
            ["目标字数", targetWords],
          ]),
        },
        {
          title: "上下文注入",
          content:
            contextArtifactIds.trim().length > 0
              ? `已配置上下文 artifact IDs：${contextArtifactIds}`
              : "未配置上下文 artifact，建议先完成文献检索与论文分析。",
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始执行写作任务。",
          }),
        },
        {
          title: "最近草稿",
          content: latestDraftResult
            ? [
                describeFields([
                  ["章节", latestDraftSectionTitle],
                  ["字数", latestDraftWordCount],
                ]),
                latestDraftReferences.length > 0
                  ? `参考文献：${latestDraftReferences.join("、")}`
                  : null,
                latestDraftContent
                  ? `内容片段：${latestDraftContent.slice(0, 120)}${latestDraftContent.length > 120 ? "..." : ""}`
                  : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次生成的草稿摘要。",
        },
      ],
      nextActions: [
        "补充/确认标题与章节参数后执行写作。",
        "将关键检索与分析产出作为上下文注入。",
        "生成后在知识区继续迭代编辑并进入后续章节写作。",
      ],
      outputLanguage: "en",
    }),
    [
      sectionHint,
      paperTitle,
      targetWords,
      contextArtifactIds,
      status,
      error,
      latestDraftResult,
      latestDraftSectionTitle,
      latestDraftWordCount,
      latestDraftReferences,
      latestDraftContent,
    ]
  );

  const handleWrite = async () => {
    if (!paperTitle.trim()) return;
    const ids = parseArtifactIds();
    await run({
      paper_title: paperTitle.trim(),
      section_type: sectionType,
      target_words: targetWords,
      context_artifact_ids: ids.length > 0 ? ids : undefined,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="论文写作"
      description="生成 SCI 章节草稿并沉淀为可编辑 artifact"
      icon={PenTool}
      iconBgClass="bg-amber-500/10"
      iconClass="text-amber-600 dark:text-amber-400"
      sidebarTitle="写作参数"
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">论文标题</label>
              <input
                type="text"
                placeholder="输入论文标题"
                value={paperTitle}
                onChange={(event) => setPaperTitle(event.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">章节类型</label>
              <select
                value={sectionType}
                onChange={(event) => setSectionType(event.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              >
                {SECTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">目标字数</label>
              <input
                type="number"
                min={200}
                step={100}
                value={targetWords}
                onChange={(event) => setTargetWords(Number(event.target.value) || 1200)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                上下文 Artifact ID（可选）
              </label>
              <textarea
                placeholder="可输入多个 ID，逗号或空格分隔"
                value={contextArtifactIds}
                onChange={(event) => setContextArtifactIds(event.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <ModelSelector
              id="sci-writing-model"
              label="生成模型"
              models={availableModels}
              selectedModel={selectedModel}
              onChange={setSelectedModel}
              isLoading={isModelLoading}
              loadError={modelLoadError}
              disabled={isRunning}
            />

            <button
              className={cn(
                "w-full py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleWrite}
              disabled={isRunning}
            >
              {isRunning ? "生成中..." : "生成草稿"}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleWrite}
            />
        </div>
      }
    >
      <TaskRuntimePanel
        runtime={runtime}
        isRunning={isRunning}
        status={status}
        error={error}
        title="论文写作运行面板"
        emptyDescription="执行后，这里会显示上下文加载、草稿生成和整理产物的过程。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
