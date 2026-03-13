"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText, Settings } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { executeWorkspaceFeature, listArtifacts } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";

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
  const { workspace, fetchArtifacts } = useWorkspaceStore();

  // Form fields
  const [softwareName, setSoftwareName] = useState("");
  const [version, setVersion] = useState("V1.0");
  const [coreModules, setCoreModules] = useState("");
  const [deploymentArchitecture, setDeploymentArchitecture] = useState("B/S架构");
  const [databaseMiddleware, setDatabaseMiddleware] = useState("");
  const [interfaceProtocols, setInterfaceProtocols] = useState("");
  const [highlights, setHighlights] = useState("");

  // UI state
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingDefaults, setIsLoadingDefaults] = useState(true);

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
  }, [workspaceId, workspace]);

  // Update software name when workspace changes
  useEffect(() => {
    if (workspace && !softwareName) {
      setSoftwareName(workspace.name || "");
    }
  }, [workspace, softwareName]);

  const handleGenerate = async () => {
    if (isRunning) return;
    if (!softwareName.trim()) {
      setError("请输入软件名称");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      const resp = await executeWorkspaceFeature(
        workspaceId,
        "technical_description",
        {
          software_name: softwareName.trim(),
          version: version.trim() || "V1.0",
          core_modules: coreModules.trim() || undefined,
          deployment_architecture: deploymentArchitecture.trim() || undefined,
          database_middleware: databaseMiddleware.trim() || undefined,
          interface_protocols: interfaceProtocols.trim() || undefined,
          highlights: highlights.trim() || undefined,
        }
      );

      if (resp.status === "warning" && !resp.task_id) {
        setError(resp.message || "暂时无法生成技术说明书");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        return;
      }

      setStatus("任务已提交，正在生成技术说明书...");
      const task = await pollTaskUntilTerminal(resp.task_id, {
        onProgress: (task) => {
          if (task.message) {
            setStatus(task.message);
          }
        },
      });
      if (!task) {
        setError("任务轮询超时，请稍后在工作区查看结果");
        return;
      }

      if (task.status === "success") {
        await fetchArtifacts(workspaceId);
        setStatus(task.message || "技术说明书生成完成");
      } else {
        setError(task.error || task.message || "生成技术说明书失败");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "生成技术说明书失败，请稍后重试"
      );
    } finally {
      setIsRunning(false);
    }
  };

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

              {error && (
                <p className="text-xs text-red-500 mt-2 bg-red-500/10 p-2 rounded-lg">
                  {error}
                </p>
              )}
              {status && !error && (
                <p className="text-xs text-[var(--text-secondary)] mt-2 bg-[var(--bg-elevated)] p-2 rounded-lg">
                  {status}
                </p>
              )}
            </div>
          )}
        </aside>

        {/* Main Area */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center max-w-lg">
              <FileText className="w-16 h-16 text-indigo-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                技术说明书生成
              </h2>
              <p className="text-[var(--text-secondary)] mb-4">
                填写左侧软件技术参数后点击生成，系统将自动生成符合软著登记要求的技术说明书。
              </p>
              <div className="text-left bg-[var(--bg-surface)] rounded-lg p-4 border border-[var(--border-default)]">
                <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">
                  生成的说明书包含以下章节：
                </h3>
                <ul className="text-xs text-[var(--text-muted)] space-y-1">
                  <li>1. 系统概述 - 软件整体介绍</li>
                  <li>2. 模块设计 - 核心功能模块说明</li>
                  <li>3. 数据流程 - 系统数据流转说明</li>
                  <li>4. 部署架构 - 部署方案说明</li>
                  <li>5. 安全与权限 - 安全机制说明</li>
                  <li>6. 操作步骤 - 主要操作流程</li>
                </ul>
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-4">
                提示：如果之前已生成过材料清单，系统会自动读取已填信息作为默认值。
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
