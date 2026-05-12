"use client";

import { useEffect, useState, useCallback } from "react";
import {
  listSandboxExecutions,
  executeSandbox,
  type SandboxExecution,
} from "@/lib/api/v2/sandbox";

interface SandboxConsoleProps {
  workspaceId: string;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SandboxConsole({ workspaceId }: SandboxConsoleProps) {
  const [history, setHistory] = useState<SandboxExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("python");
  const [running, setRunning] = useState(false);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSandboxExecutions(workspaceId);
      setHistory(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load executions",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  async function handleRun() {
    if (!code.trim()) return;
    setRunning(true);
    setError(null);
    try {
      const result = await executeSandbox(workspaceId, code, language);
      setHistory((prev) => [result, ...prev]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to execute code",
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div data-testid="sandbox-console" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Editor area */}
      <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            data-testid="sandbox-language"
            style={{
              padding: "6px 10px",
              borderRadius: "var(--v2-radius-sm)",
              border: "1px solid rgba(20, 20, 30, 0.08)",
              background: "var(--v2-glass-bg)",
              fontSize: 13,
              fontFamily: "var(--v2-font-sans)",
              color: "var(--v2-text-primary)",
              outline: "none",
              cursor: "pointer",
            }}
          >
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
          </select>
          <button
            onClick={handleRun}
            disabled={running}
            data-testid="sandbox-run"
            style={{
              padding: "6px 16px",
              borderRadius: "var(--v2-radius-sm)",
              border: "none",
              background: "var(--v2-accent-purple-700)",
              color: "#fff",
              fontSize: 13,
              fontWeight: 600,
              fontFamily: "var(--v2-font-sans)",
              cursor: running ? "not-allowed" : "pointer",
              opacity: running ? 0.6 : 1,
            }}
          >
            {running ? "Running..." : "Run"}
          </button>
        </div>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder={`// Enter ${language} code here...`}
          data-testid="sandbox-editor"
          rows={6}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "10px 12px",
            borderRadius: "var(--v2-radius-md)",
            border: "1px solid rgba(20, 20, 30, 0.08)",
            background: "#1E1E2E",
            color: "#CDD6F4",
            fontSize: 13,
            fontFamily: "var(--v2-font-mono)",
            lineHeight: 1.5,
            resize: "vertical",
            outline: "none",
          }}
        />
      </div>

      {error && (
        <div
          style={{ textAlign: "center", padding: "8px 16px", color: "var(--v2-status-error)" }}
          data-testid="sandbox-error"
        >
          {error}
        </div>
      )}

      {/* History */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "var(--v2-text-tertiary)",
            marginBottom: 8,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Execution History
        </div>

        {loading && (
          <div
            style={{ textAlign: "center", padding: "24px 0", color: "var(--v2-text-tertiary)" }}
            data-testid="sandbox-loading"
          >
            Loading history...
          </div>
        )}

        {!loading && history.length === 0 && (
          <div
            style={{ textAlign: "center", padding: "24px 0", color: "var(--v2-text-tertiary)" }}
            data-testid="sandbox-empty"
          >
            No executions yet
          </div>
        )}

        {history.map((exec) => (
          <div
            key={exec.id}
            data-testid="sandbox-execution"
            style={{
              background: "var(--v2-glass-bg)",
              borderRadius: "var(--v2-radius-md)",
              border: "1px solid rgba(20, 20, 30, 0.06)",
              padding: 12,
              marginBottom: 8,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 6,
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span
                  style={{
                    display: "inline-block",
                    padding: "1px 8px",
                    borderRadius: 10,
                    fontSize: 11,
                    fontWeight: 500,
                    color:
                      exec.status === "completed"
                        ? "var(--v2-status-success-deep)"
                        : "var(--v2-status-error)",
                    background:
                      exec.status === "completed"
                        ? "rgba(22, 163, 74, 0.1)"
                        : "rgba(220, 38, 38, 0.1)",
                  }}
                >
                  {exec.status}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--v2-text-tertiary)",
                  }}
                >
                  {exec.language}
                </span>
              </div>
              <span
                style={{ fontSize: 11, color: "var(--v2-text-tertiary)" }}
              >
                {formatTime(exec.created_at)}
              </span>
            </div>
            <pre
              style={{
                background: "#1E1E2E",
                borderRadius: "var(--v2-radius-sm)",
                padding: "8px 10px",
                margin: 0,
                fontSize: 12,
                fontFamily: "var(--v2-font-mono)",
                color: "#CDD6F4",
                overflow: "auto",
                maxHeight: 120,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {exec.output}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
