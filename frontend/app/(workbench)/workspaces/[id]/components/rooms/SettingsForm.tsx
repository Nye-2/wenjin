"use client";

import { useState, useEffect } from "react";
import { listModels, type Model } from "@/lib/api";
import { authorizedFetch } from "@/lib/api/client";
import type { WriteMode } from "@/lib/change-set-view";
import {
  normalizeWriteMode,
  WriteModeSelector,
} from "../review-changes/WriteModeSelector";

interface SettingsFormProps {
  workspaceId: string;
}

interface WorkspaceSettings {
  name: string;
  auto_compact_threshold: number;
  default_model: string;
  write_mode?: WriteMode | null;
}

export function SettingsForm({ workspaceId }: SettingsFormProps) {
  const [name, setName] = useState("");
  const [autoCompactThreshold, setAutoCompactThreshold] = useState(0.8);
  const [defaultModel, setDefaultModel] = useState("");
  const [writeMode, setWriteMode] = useState<WriteMode>("auto_draft");
  const [models, setModels] = useState<Model[]>([]);
  const [modelsError, setModelsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listModels("chat")
      .then((data) => {
        if (cancelled) return;
        setModels(data.models);
        const defaultOption = data.models.find((model) => model.is_default) ?? data.models[0];
        if (defaultOption) {
          setDefaultModel((current) => current || defaultOption.name);
        }
      })
      .catch(() => {
        if (!cancelled) setModelsError(true);
      });
    authorizedFetch(`/api/workspaces/${workspaceId}/settings`)
      .then((res) => {
        if (!res.ok) throw new Error("设置加载失败");
        return res.json();
      })
      .then((data: WorkspaceSettings) => {
        if (!cancelled) {
          if (data.name) setName(data.name);
          if (data.auto_compact_threshold != null)
            setAutoCompactThreshold(data.auto_compact_threshold);
          if (data.default_model) setDefaultModel(data.default_model);
          setWriteMode(normalizeWriteMode(data.write_mode));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const settings: WorkspaceSettings = {
        name,
        auto_compact_threshold: autoCompactThreshold,
        default_model: defaultModel,
        write_mode: writeMode,
      };
      const res = await authorizedFetch(`/api/workspaces/${workspaceId}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error("设置保存失败");
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "设置保存失败",
      );
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 12px",
    borderRadius: "var(--wjn-radius-md)",
    border: "1px solid rgba(20, 20, 30, 0.08)",
    background: "var(--wjn-surface-raised)",
    fontSize: 13,
    fontFamily: "var(--wjn-font-sans)",
    color: "var(--wjn-text)",
    outline: "none",
  };

  if (loading) {
    return (
      <div
        style={{
          padding: 16,
          color: "var(--wjn-text-muted)",
          textAlign: "center",
          fontSize: 13,
        }}
      >
        正在加载设置...
      </div>
    );
  }

  const modelOptions = models.some((model) => model.name === defaultModel)
    ? models
    : defaultModel
      ? [
          {
            name: defaultModel,
            display_name: `${defaultModel}（当前设置）`,
            provider: "",
            max_tokens: 0,
            supports_thinking: false,
            supports_reasoning_effort: false,
            supports_vision: false,
          } satisfies Model,
          ...models,
        ]
      : models;

  return (
    <div data-testid="settings-form" style={{ padding: "16px", overflowY: "auto", flex: 1 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Workspace name */}
        <div>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-text-secondary)",
              marginBottom: 6,
            }}
          >
            工作区名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="我的工作区"
            data-testid="settings-name"
            style={inputStyle}
          />
        </div>

        {/* Auto-compact threshold */}
        <div>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-text-secondary)",
              marginBottom: 6,
            }}
          >
            上下文整理阈值
          </label>
          <input
            type="number"
            value={autoCompactThreshold}
            onChange={(e) => setAutoCompactThreshold(parseFloat(e.target.value))}
            min={0}
            max={1}
            step={0.1}
            data-testid="settings-compact-threshold"
            style={inputStyle}
          />
        </div>

        {/* Default model */}
        <div>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-text-secondary)",
              marginBottom: 6,
            }}
          >
            默认模型
          </label>
          <select
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            data-testid="settings-default-model"
            disabled={modelOptions.length === 0}
            style={{
              ...inputStyle,
              cursor: "pointer",
            }}
          >
            {modelOptions.length === 0 ? (
              <option value="">暂无可用模型</option>
            ) : (
              modelOptions.map((model) => (
              <option key={model.name} value={model.name}>
                {model.display_name}
              </option>
              ))
            )}
          </select>
          {modelsError && (
            <div style={{ marginTop: 6, fontSize: 12, color: "var(--wjn-review)" }}>
              模型目录加载失败，将保留当前设置。
            </div>
          )}
        </div>

        {/* Write mode */}
        <div>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-text-secondary)",
              marginBottom: 6,
            }}
          >
            写入模式
          </label>
          <WriteModeSelector value={writeMode} onChange={setWriteMode} disabled={saving} />
          <div style={{ marginTop: 7, fontSize: 12, color: "var(--wjn-text-muted)", lineHeight: 1.45 }}>
            设置会影响后续新启动的运行；已经启动的运行会保留启动时的模式快照。
          </div>
        </div>

        {/* Save button */}
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          data-testid="settings-save"
          style={{
            padding: "10px 20px",
            borderRadius: "var(--wjn-radius-md)",
            border: "none",
            background: "var(--wjn-blue)",
            color: "#fff",
            fontSize: 14,
            fontWeight: 600,
            fontFamily: "var(--wjn-font-sans)",
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.6 : 1,
            alignSelf: "flex-start",
          }}
        >
          {saving ? "正在保存..." : "保存设置"}
        </button>

        {saved && (
          <div
            style={{ color: "var(--wjn-success)", fontSize: 13 }}
            data-testid="settings-saved"
          >
            设置已保存
          </div>
        )}

        {error && (
          <div
            style={{ color: "var(--wjn-error)", fontSize: 13 }}
            data-testid="settings-error"
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
