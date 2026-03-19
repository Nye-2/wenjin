"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText, Settings } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { listArtifacts } from "@/lib/api";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
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
} from "@/lib/artifact-utils";

interface CopyrightMaterialsProfile {
  software_name?: string;
  version?: string;
}

interface CopyrightMaterialsArtifact {
  id: string;
  type: string;
  content: {
    software_profile?: CopyrightMaterialsProfile;
  };
}

export default function TechnicalDescriptionPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  // Form fields
  const [softwareName, setSoftwareName] = useState("");
  const [version, setVersion] = useState("V1.0");
  const [coreModules, setCoreModules] = useState("");
  const [deploymentArchitecture, setDeploymentArchitecture] = useState("B/S架构");
  const [databaseMiddleware, setDatabaseMiddleware] = useState("");
  const [interfaceProtocols, setInterfaceProtocols] = useState("");
  const [highlights, setHighlights] = useState("");

  // UI state
  const [isLoadingDefaults, setIsLoadingDefaults] = useState(true);

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
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

  // Load defaults from copyright_materials artifact
  useEffect(() => {
    const loadDefaults = async () => {
      setIsLoadingDefaults(true);
      try {
        // Set workspace name as default
        if (workspace && !softwareName) {
          setSoftwareName(workspace.name || "");
        }

        // Try to load copyright_materials artifact for defaults
        const response = await listArtifacts(workspaceId, "copyright_materials");
        if (response.artifacts && response.artifacts.length > 0) {
          const latestArtifact = response.artifacts[0] as CopyrightMaterialsArtifact;
          const profile = latestArtifact.content?.software_profile;
          if (profile) {
            if (profile.software_name && !softwareName) {
              setSoftwareName(profile.software_name);
            }
            if (profile.version && version === "V1.0") {
              setVersion(profile.version);
            }
          }
        }
      } catch (e) {
        console.error("Failed to load defaults:", e);
      } finally {
        setIsLoadingDefaults(false);
      }
    };

    loadDefaults();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only load defaults on mount or workspace change, not on field edits
  }, [workspaceId, workspace]);

  // Update software name when workspace changes
  useEffect(() => {
    if (workspace && !softwareName) {
      setSoftwareName(workspace.name || "");
    }
  }, [workspace, softwareName]);

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

  const latestTechnicalArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["technical_description"]),
    [artifacts]
  );
  const latestTechnicalResult = useMemo(
    () => getArtifactContentRecord(latestTechnicalArtifact) ?? latestTaskResult,
    [latestTechnicalArtifact, latestTaskResult]
  );
  const latestSoftwareProfile =
    latestTechnicalResult?.software_profile &&
    typeof latestTechnicalResult.software_profile === "object"
      ? (latestTechnicalResult.software_profile as Record<string, unknown>)
      : null;
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
          isLoading: isLoadingDefaults,
          loadingMessage: "正在读取历史材料默认值...",
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
          <div className="p-2 rounded-lg bg-indigo-500/10">
            <FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              技术说明书
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              撰写软件功能与技术实现说明
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-96 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4 flex items-center gap-2">
            <Settings className="w-4 h-4" />
            软件技术参数
          </h2>

          {isLoadingDefaults ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
              <span className="ml-2 text-sm text-[var(--text-muted)]">
                加载默认配置...
              </span>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Basic Info */}
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
          )}
        </aside>

        {/* Main Area */}
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
