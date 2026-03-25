"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { FileText, Settings } from "lucide-react";
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
  joinStringArrayLike,
  readString,
} from "@/lib/artifact-utils";

export default function TechnicalDescriptionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const softwareNameSeed = searchParams.get("software_name");
  const versionSeed = searchParams.get("version");
  const coreModulesSeed = searchParams.get("core_modules");
  const deploymentArchitectureSeed = searchParams.get("deployment_architecture");
  const databaseMiddlewareSeed = searchParams.get("database_middleware");
  const interfaceProtocolsSeed = searchParams.get("interface_protocols");
  const highlightsSeed = searchParams.get("highlights");

  // Form fields
  const [softwareName, setSoftwareName] = useState(() => softwareNameSeed || "");
  const [version, setVersion] = useState(() => versionSeed || "V1.0");
  const [coreModules, setCoreModules] = useState(() => coreModulesSeed || "");
  const [deploymentArchitecture, setDeploymentArchitecture] = useState(
    () => deploymentArchitectureSeed || "B/S架构"
  );
  const [databaseMiddleware, setDatabaseMiddleware] = useState(
    () => databaseMiddlewareSeed || ""
  );
  const [interfaceProtocols, setInterfaceProtocols] = useState(
    () => interfaceProtocolsSeed || ""
  );
  const [highlights, setHighlights] = useState(() => highlightsSeed || "");

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "technical_description",
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

  const latestTechnicalArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["technical_description"]),
    [artifacts]
  );
  const latestMaterialsArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["copyright_materials"]),
    [artifacts]
  );
  const latestTechnicalResult = useMemo(
    () => getArtifactContentRecord(latestTechnicalArtifact) ?? latestTaskResult,
    [latestTechnicalArtifact, latestTaskResult]
  );
  const latestMaterialsResult = useMemo(
    () => getArtifactContentRecord(latestMaterialsArtifact),
    [latestMaterialsArtifact]
  );
  const latestSoftwareProfile =
    latestTechnicalResult?.software_profile &&
    typeof latestTechnicalResult.software_profile === "object"
      ? (latestTechnicalResult.software_profile as Record<string, unknown>)
      : latestMaterialsResult?.software_profile &&
          typeof latestMaterialsResult.software_profile === "object"
        ? (latestMaterialsResult.software_profile as Record<string, unknown>)
        : null;

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
    if (coreModulesSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setCoreModules(coreModulesSeed);
    }
  }, [coreModulesSeed]);

  useEffect(() => {
    if (deploymentArchitectureSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setDeploymentArchitecture(deploymentArchitectureSeed);
    }
  }, [deploymentArchitectureSeed]);

  useEffect(() => {
    if (databaseMiddlewareSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setDatabaseMiddleware(databaseMiddlewareSeed);
    }
  }, [databaseMiddlewareSeed]);

  useEffect(() => {
    if (interfaceProtocolsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setInterfaceProtocols(interfaceProtocolsSeed);
    }
  }, [interfaceProtocolsSeed]);

  useEffect(() => {
    if (highlightsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setHighlights(highlightsSeed);
    }
  }, [highlightsSeed]);

  // Update software name when workspace changes
  useEffect(() => {
    if (workspace && !softwareName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setSoftwareName(workspace.name || "");
    }
  }, [workspace, softwareName]);

  useEffect(() => {
    const latestSoftwareName = readString(latestSoftwareProfile?.software_name);
    if (latestSoftwareName && !softwareName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest software profile when route seed is absent
      setSoftwareName(latestSoftwareName);
    }
  }, [latestSoftwareProfile, softwareName]);

  useEffect(() => {
    const latestVersion = readString(latestSoftwareProfile?.version);
    if (latestVersion && version === "V1.0" && !versionSeed) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest version when route seed is absent
      setVersion(latestVersion);
    }
  }, [latestSoftwareProfile, version, versionSeed]);

  useEffect(() => {
    const latestCoreModules = joinStringArrayLike(latestSoftwareProfile?.core_modules);
    if (latestCoreModules && !coreModules) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest modules when route seed is absent
      setCoreModules(latestCoreModules);
    }
  }, [latestSoftwareProfile, coreModules]);

  useEffect(() => {
    const latestArchitecture = readString(
      latestSoftwareProfile?.deployment_architecture
    );
    if (
      latestArchitecture &&
      deploymentArchitecture === "B/S架构" &&
      !deploymentArchitectureSeed
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest architecture when route seed is absent
      setDeploymentArchitecture(latestArchitecture);
    }
  }, [latestSoftwareProfile, deploymentArchitecture, deploymentArchitectureSeed]);

  useEffect(() => {
    const latestDatabaseMiddleware = joinStringArrayLike(
      latestSoftwareProfile?.database_middleware
    );
    if (latestDatabaseMiddleware && !databaseMiddleware) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest middleware when route seed is absent
      setDatabaseMiddleware(latestDatabaseMiddleware);
    }
  }, [latestSoftwareProfile, databaseMiddleware]);

  useEffect(() => {
    const latestInterfaceProtocols = joinStringArrayLike(
      latestSoftwareProfile?.interface_protocols
    );
    if (latestInterfaceProtocols && !interfaceProtocols) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest protocols when route seed is absent
      setInterfaceProtocols(latestInterfaceProtocols);
    }
  }, [latestSoftwareProfile, interfaceProtocols]);

  useEffect(() => {
    const latestHighlights = joinStringArrayLike(latestSoftwareProfile?.highlights);
    if (latestHighlights && !highlights) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest highlights when route seed is absent
      setHighlights(latestHighlights);
    }
  }, [latestSoftwareProfile, highlights]);

  const handleGenerate = async () => {
    if (!softwareName.trim()) return;
    await run({
      software_name: softwareName.trim(),
      version: version.trim() || "V1.0",
      core_modules: coreModules.trim() || undefined,
      deployment_architecture: deploymentArchitecture.trim() || undefined,
      database_middleware: databaseMiddleware.trim() || undefined,
      interface_protocols: interfaceProtocols.trim() || undefined,
      highlights: highlights.trim() || undefined,
      model_id: selectedModel || undefined,
    });
  };

  const latestSections =
    latestTechnicalResult?.sections &&
    typeof latestTechnicalResult.sections === "object"
      ? (latestTechnicalResult.sections as Record<string, unknown>)
      : null;
  const latestSectionNames = latestSections
    ? Object.entries(latestSections)
        .map(([key, value]) => {
          if (!value || typeof value !== "object") {
            return readString(key);
          }
          const sectionTitle = readString((value as Record<string, unknown>).title);
          return sectionTitle ?? readString(key);
        })
        .filter((item): item is string => Boolean(item))
        .slice(0, 4)
    : [];

  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestTechnicalResult
      ? "最近一次技术说明书已经生成，可直接在知识区查看完整章节并继续修订。"
      : "本工作区用于生成软著技术说明书主文档，系统会根据软件参数产出结构化说明内容。",
    sections: [
      {
        title: "当前软件信息",
        content: describeFields([
          ["软件", softwareName],
          ["版本", version],
          ["部署", deploymentArchitecture],
        ]),
      },
      {
        title: "配置完整度",
        content: describeFields([
          ["核心模块", coreModules],
          ["数据库/中间件", databaseMiddleware],
          ["接口协议", interfaceProtocols],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始生成技术说明书。",
        }),
      },
      {
        title: "最近产出",
        content: latestTechnicalResult
          ? [
              latestSoftwareProfile
                ? describeFields([
                    ["软件", readString(latestSoftwareProfile.software_name) || softwareName],
                    ["版本", readString(latestSoftwareProfile.version) || version],
                  ])
                : null,
              latestSections
                ? `章节数：${Object.keys(latestSections).length}`
                : null,
              latestSectionNames.length > 0
                ? `核心章节：${latestSectionNames.join("、")}`
                : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次生成的说明书章节摘要。",
      },
    ],
    nextActions: [
      "补齐核心模块、数据库和接口协议信息后执行生成。",
      "生成后在知识区审阅章节内容并按登记要求修订。",
      "与材料清单联动完成软著申请包准备。",
    ],
    outputLanguage: "zh",
  });

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="技术说明书"
      description="撰写软件功能与技术实现说明"
      icon={FileText}
      iconBgClass="bg-indigo-500/10"
      iconClass="text-indigo-600 dark:text-indigo-400"
      sidebarTitle="软件技术参数"
      sidebarWidthClassName="lg:w-96"
      sidebarClassName="overflow-y-auto"
      headerActions={<Settings className="h-4 w-4 text-[var(--text-muted)]" />}
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                软件名称 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                placeholder="输入软件全称..."
                value={softwareName}
                onChange={(e) => setSoftwareName(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                版本号
              </label>
              <input
                type="text"
                placeholder="例如：V1.0"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                核心模块
                <span className="text-[var(--text-muted)] ml-1">(逗号分隔)</span>
              </label>
              <input
                type="text"
                placeholder="例如：用户管理,数据处理,报表导出"
                value={coreModules}
                onChange={(e) => setCoreModules(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                部署架构
              </label>
              <select
                value={deploymentArchitecture}
                onChange={(e) => setDeploymentArchitecture(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                <option value="B/S架构">B/S架构</option>
                <option value="C/S架构">C/S架构</option>
                <option value="微服务架构">微服务架构</option>
                <option value="单体架构">单体架构</option>
                <option value="混合架构">混合架构</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                数据库/中间件
                <span className="text-[var(--text-muted)] ml-1">(逗号分隔)</span>
              </label>
              <input
                type="text"
                placeholder="例如：MySQL,Redis,RabbitMQ"
                value={databaseMiddleware}
                onChange={(e) => setDatabaseMiddleware(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                接口协议
                <span className="text-[var(--text-muted)] ml-1">(逗号分隔)</span>
              </label>
              <input
                type="text"
                placeholder="例如：HTTP/REST,WebSocket,gRPC"
                value={interfaceProtocols}
                onChange={(e) => setInterfaceProtocols(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                功能亮点
                <span className="text-[var(--text-muted)] ml-1">(逗号分隔)</span>
              </label>
              <textarea
                placeholder="例如：智能推荐,实时分析,一键导出"
                value={highlights}
                onChange={(e) => setHighlights(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none"
              />
            </div>

            <ModelSelector
              id="technical-description-model"
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
                "w-full py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成技术说明书"}
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
        title="技术说明书运行面板"
        emptyDescription="执行后，这里会显示软件画像、说明书生成和章节整理过程。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
