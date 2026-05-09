"use client";

import { useState } from "react";

interface SettingsFormProps {
  workspaceId: string;
}

const MODEL_OPTIONS = [
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { value: "claude-opus-4-5", label: "Claude Opus 4.5" },
  { value: "claude-haiku-3-5", label: "Claude Haiku 3.5" },
];

interface WorkspaceSettings {
  name: string;
  auto_compact_threshold: number;
  default_model: string;
}

export function SettingsForm({ workspaceId }: SettingsFormProps) {
  const [name, setName] = useState("");
  const [autoCompactThreshold, setAutoCompactThreshold] = useState(0.8);
  const [defaultModel, setDefaultModel] = useState("claude-sonnet-4-6");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const settings: WorkspaceSettings = {
        name,
        auto_compact_threshold: autoCompactThreshold,
        default_model: defaultModel,
      };
      const res = await fetch(`/api/workspaces/${workspaceId}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error("Failed to save settings");
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save settings",
      );
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 12px",
    borderRadius: "var(--v2-radius-md)",
    border: "1px solid rgba(20, 20, 30, 0.08)",
    background: "var(--v2-glass-bg)",
    fontSize: 13,
    fontFamily: "var(--v2-font-sans)",
    color: "var(--v2-text-primary)",
    outline: "none",
  };

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
              color: "var(--v2-text-secondary)",
              marginBottom: 6,
            }}
          >
            Workspace Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Workspace"
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
              color: "var(--v2-text-secondary)",
              marginBottom: 6,
            }}
          >
            Auto-Compact Threshold
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
              color: "var(--v2-text-secondary)",
              marginBottom: 6,
            }}
          >
            Default Model
          </label>
          <select
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            data-testid="settings-default-model"
            style={{
              ...inputStyle,
              cursor: "pointer",
            }}
          >
            {MODEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          data-testid="settings-save"
          style={{
            padding: "10px 20px",
            borderRadius: "var(--v2-radius-md)",
            border: "none",
            background: "var(--v2-accent-purple-700)",
            color: "#fff",
            fontSize: 14,
            fontWeight: 600,
            fontFamily: "var(--v2-font-sans)",
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.6 : 1,
            alignSelf: "flex-start",
          }}
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>

        {saved && (
          <div
            style={{ color: "var(--v2-status-success-deep)", fontSize: 13 }}
            data-testid="settings-saved"
          >
            Settings saved successfully
          </div>
        )}

        {error && (
          <div
            style={{ color: "var(--v2-status-error)", fontSize: 13 }}
            data-testid="settings-error"
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
