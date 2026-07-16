"use client";

import { useState, useEffect } from "react";
import {
  getWorkspace,
  getWorkspaceSettings,
  listModels,
  type Model,
  updateWorkspace,
  updateWorkspaceSettings,
} from "@/lib/api";
import type { MissionReviewMode } from "@/lib/api/mission-types";
import {
  chooseReasoningEffort,
  REASONING_EFFORT_OPTIONS,
  type ReasoningEffort,
} from "@/lib/reasoning-effort";
import {
  normalizeReviewMode,
  ReviewModeSelector,
} from "../mission-console/ReviewModeSelector";

interface SettingsFormProps {
  workspaceId: string;
}

export function SettingsForm({ workspaceId }: SettingsFormProps) {
  const [name, setName] = useState("");
  const [autoCompactThreshold, setAutoCompactThreshold] = useState(0.8);
  const [defaultModel, setDefaultModel] = useState("");
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>("xhigh");
  const [reviewMode, setReviewMode] = useState<MissionReviewMode>("balanced_default");
  const [models, setModels] = useState<Model[]>([]);
  const [modelsError, setModelsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([
      listModels("chat"),
      getWorkspace(workspaceId),
      getWorkspaceSettings(workspaceId),
    ]).then(([catalogResult, workspaceResult, settingsResult]) => {
      if (cancelled) return;
      const availableModels =
        catalogResult.status === "fulfilled" ? catalogResult.value.models : [];
      const settings =
        settingsResult.status === "fulfilled" ? settingsResult.value : null;
      const selectedModel =
        availableModels.find((model) => model.name === settings?.default_model) ??
        availableModels.find((model) => model.is_default) ??
        availableModels[0];
      setModels(availableModels);
      setModelsError(catalogResult.status === "rejected");
      if (workspaceResult.status === "fulfilled") {
        setName(workspaceResult.value.name);
      }
      if (settings) {
        setAutoCompactThreshold(settings.auto_compact_threshold);
        setReviewMode(normalizeReviewMode(settings.review_mode));
      }
      setDefaultModel(selectedModel?.name ?? settings?.default_model ?? "");
      setReasoningEffort(
        chooseReasoningEffort(
          selectedModel?.capability_profile.reasoning_efforts ?? [],
          settings?.reasoning_effort,
        ),
      );
      if (workspaceResult.status === "rejected" || settingsResult.status === "rejected") {
        setError("部分工作区设置加载失败");
      }
      setLoading(false);
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
      await Promise.all([
        updateWorkspace(workspaceId, { name }),
        updateWorkspaceSettings(workspaceId, {
          auto_compact_threshold: autoCompactThreshold,
          default_model: defaultModel,
          reasoning_effort: reasoningEffort,
          review_mode: reviewMode,
        }),
      ]);
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
            generation_api: null,
            capability_profile_version: "unavailable",
            capability_profile: {
              strict_tool_calls: false,
              streaming: false,
              reasoning_efforts: [],
              vision: false,
              native_web_search: false,
            },
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
            onChange={(e) => {
              const nextModelId = e.target.value;
              const nextModel = models.find((model) => model.name === nextModelId);
              setDefaultModel(nextModelId);
              setReasoningEffort(
                chooseReasoningEffort(
                  nextModel?.capability_profile.reasoning_efforts ?? [],
                  reasoningEffort,
                ),
              );
            }}
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
            默认推理强度
          </label>
          <select
            value={reasoningEffort}
            onChange={(event) =>
              setReasoningEffort(event.target.value as ReasoningEffort)
            }
            data-testid="settings-reasoning-effort"
            disabled={
              !models
                .find((model) => model.name === defaultModel)
                ?.capability_profile.reasoning_efforts.length
            }
            style={{ ...inputStyle, cursor: "pointer" }}
          >
            {REASONING_EFFORT_OPTIONS.filter((option) =>
              (
                models.find((model) => model.name === defaultModel)
                  ?.capability_profile.reasoning_efforts ?? []
              ).includes(option.value),
            ).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
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
            确认方式
          </label>
          <ReviewModeSelector value={reviewMode} onChange={setReviewMode} disabled={saving} />
          <div style={{ marginTop: 7, fontSize: 12, color: "var(--wjn-text-muted)", lineHeight: 1.45 }}>
            设置会影响后续新任务；已经启动的任务会保留创建时的确认方式。
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
