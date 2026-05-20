"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  getMcpConfig,
  updateMcpConfig,
  type McpConfigResponse,
  type McpServerConfigInput,
} from "@/lib/api";

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const responseData = (error as { response?: { data?: unknown } }).response?.data;
    if (responseData && typeof responseData === "object" && "detail" in responseData) {
      const detail = (responseData as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

function formatJsonDraft(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseMcpServersDraft(draft: string): Record<string, McpServerConfigInput> {
  const parsed = JSON.parse(draft || "{}") as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP 配置必须是一个 JSON 对象，key 为 server 名称。");
  }
  return parsed as Record<string, McpServerConfigInput>;
}

export default function AdminMcpPage() {
  const [mcpConfig, setMcpConfig] = useState<McpConfigResponse | null>(null);
  const [mcpDraft, setMcpDraft] = useState("{}");
  const [mcpDraftBaseline, setMcpDraftBaseline] = useState("{}");
  const [mcpDraftError, setMcpDraftError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadConfig = async () => {
      setIsLoading(true);
      try {
        const res = await getMcpConfig();
        if (!cancelled) {
          const formattedDraft = formatJsonDraft(res.mcp_servers ?? {});
          setMcpConfig(res);
          setMcpDraft(formattedDraft);
          setMcpDraftBaseline(formattedDraft);
          setMcpDraftError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setMcpDraftError(parseErrorMessage(err, "加载 MCP 配置失败"));
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadConfig();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const mcpServerEntries = Object.entries(mcpConfig?.mcp_servers ?? {});
  const enabledMcpCount = mcpServerEntries.filter(([, config]) => config.enabled !== false).length;
  const hasMcpChanges = mcpDraft.trim() !== mcpDraftBaseline.trim();

  let mcpDraftPreviewError: string | null = null;
  try {
    parseMcpServersDraft(mcpDraft);
  } catch (err) {
    mcpDraftPreviewError = parseErrorMessage(err, "MCP 配置 JSON 无效");
  }

  const formatMcpDraft = () => {
    try {
      const parsed = parseMcpServersDraft(mcpDraft);
      setMcpDraft(formatJsonDraft(parsed));
      setMcpDraftError(null);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "MCP 配置 JSON 无法格式化"));
    }
  };

  const restoreMcpDraft = () => {
    setMcpDraft(mcpDraftBaseline);
    setMcpDraftError(null);
  };

  const saveMcpDraft = async () => {
    let parsedServers: Record<string, McpServerConfigInput>;
    try {
      parsedServers = parseMcpServersDraft(mcpDraft);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "MCP 配置 JSON 无效"));
      return;
    }

    setMcpDraftError(null);
    setIsSaving(true);
    try {
      const nextConfig = await updateMcpConfig({ mcp_servers: parsedServers });
      const formattedDraft = formatJsonDraft(nextConfig.mcp_servers ?? {});
      setMcpConfig(nextConfig);
      setMcpDraft(formattedDraft);
      setMcpDraftBaseline(formattedDraft);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "保存 MCP 配置失败"));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="MCP 配置中心"
        description="管理外部 MCP server。编辑区只修改 mcp_servers，不会覆盖 skills 配置。"
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
        actions={
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={formatMcpDraft}
              disabled={isLoading || isSaving}
            >
              格式化 JSON
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={restoreMcpDraft}
              disabled={isSaving || !hasMcpChanges}
            >
              撤销改动
            </Button>
            <Button
              size="sm"
              onClick={() => void saveMcpDraft()}
              disabled={isSaving || !hasMcpChanges || Boolean(mcpDraftPreviewError)}
            >
              {isSaving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
              保存配置
            </Button>
          </>
        }
      />

      <section className="route-card rounded-[1.75rem] p-5">
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
            <div className="text-xs text-[var(--text-muted)]">服务数量</div>
            <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
              {mcpServerEntries.length}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
            <div className="text-xs text-[var(--text-muted)]">启用中的服务</div>
            <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
              {enabledMcpCount}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
            <div className="text-xs text-[var(--text-muted)]">当前草稿状态</div>
            <div className="mt-2 text-sm font-medium text-[var(--text-primary)]">
              {hasMcpChanges ? "有未保存改动" : "与已加载配置一致"}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              {mcpDraftPreviewError ? "JSON 需修复后才能保存" : "可直接保存并触发 runtime 热更新"}
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="mt-4 text-sm text-[var(--text-muted)] flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            正在加载 MCP 配置
          </div>
        ) : mcpServerEntries.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-[var(--border-default)] px-4 py-5 text-sm text-[var(--text-muted)]">
            当前没有配置任何 MCP 服务。可在下方 JSON 草稿中添加，例如：
            <pre className="mt-2 overflow-x-auto rounded-lg bg-[var(--bg-base)] p-3 text-[11px] text-[var(--text-secondary)]">
{`{
  "github": {
    "enabled": true,
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"]
  }
}`}
            </pre>
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-3">
            {mcpServerEntries.map(([name, server]) => (
              <div
                key={name}
                className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">{name}</h3>
                    <p className="text-xs text-[var(--text-muted)] mt-1">
                      {server.description?.trim() || "未填写说明"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-[var(--bg-muted)] px-2 py-1 text-[11px] text-[var(--text-secondary)]">
                      {server.type ?? "stdio"}
                    </span>
                    <span
                      className={`rounded-md px-2 py-1 text-[11px] ${
                        server.enabled === false
                          ? "bg-rose-500/10 text-rose-600"
                          : "bg-emerald-500/10 text-emerald-600"
                      }`}
                    >
                      {server.enabled === false ? "已禁用" : "已启用"}
                    </span>
                  </div>
                </div>
                <div className="mt-3 space-y-2 text-xs text-[var(--text-secondary)]">
                  {server.command ? <p>命令: <code>{server.command}</code></p> : null}
                  {server.url ? <p>地址: <code>{server.url}</code></p> : null}
                  {server.args?.length ? <p>参数: <code>{server.args.join(" ")}</code></p> : null}
                  {server.headers && Object.keys(server.headers).length > 0 ? (
                    <p>请求头: {Object.keys(server.headers).join(", ")}</p>
                  ) : null}
                  <p>
                    鉴权:{" "}
                    {server.oauth?.enabled === false
                      ? "已禁用"
                      : server.oauth
                        ? `已启用（${server.oauth.grant_type ?? "client_credentials"}）`
                        : "未配置"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-5 space-y-2">
          <Label htmlFor="mcp-config-draft" className="text-sm font-medium text-[var(--text-primary)]">
            MCP Server 草稿
          </Label>
          <textarea
            id="mcp-config-draft"
            value={mcpDraft}
            onChange={(event) => {
              setMcpDraft(event.target.value);
              if (mcpDraftError) {
                setMcpDraftError(null);
              }
            }}
            spellCheck={false}
            className="min-h-[320px] w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] px-4 py-3 font-mono text-xs text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--accent-primary)]"
          />
          <p className="text-[11px] text-[var(--text-muted)]">
            保存后会写入后端 `extensions_config.json`，并立即刷新 MCP runtime 与工具缓存。
          </p>
          {(mcpDraftError || mcpDraftPreviewError) && (
            <div className="rounded-lg border border-rose-300/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-600">
              {mcpDraftError ?? mcpDraftPreviewError}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
