"use client";

import { useEffect, useState } from "react";
import { authorizedFetch } from "@/lib/api/client";

interface NodeDetailDrawerProps {
  executionId: string;
  nodeId: string;
  onClose: () => void;
}

interface NodeDetail {
  id: string;
  label: string | null;
  status: string;
  phase_index: number | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  thinking: string | null;
  tools: Array<{ name: string; args: Record<string, unknown>; result: string }> | null;
  token_usage: { input: number; output: number } | null;
  started_at: string | null;
  completed_at: string | null;
}

type TabKey = "input" | "output" | "thinking" | "tools";

const TABS: { key: TabKey; label: string }[] = [
  { key: "input", label: "Input" },
  { key: "output", label: "Output" },
  { key: "thinking", label: "Thinking" },
  { key: "tools", label: "Tools" },
];

export function NodeDetailDrawer({
  executionId,
  nodeId,
  onClose,
}: NodeDetailDrawerProps) {
  const [data, setData] = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("input");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    authorizedFetch(`/api/executions/${executionId}/nodes/${nodeId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch node detail");
        return res.json();
      })
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message ?? "Unknown error");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [executionId, nodeId]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  return (
    <div
      style={{
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: 400,
        background: "rgba(255, 255, 255, 0.9)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderLeft: "1px solid rgba(20, 20, 30, 0.08)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms ease-out",
      }}
      data-testid="node-detail-drawer"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 20px 12px",
          borderBottom: "1px solid var(--v2-border-soft)",
        }}
      >
        <div>
          <div
            style={{
              fontWeight: 600,
              fontSize: 15,
              color: "var(--v2-text-primary)",
            }}
          >
            {loading ? "Loading..." : data?.label ?? nodeId}
          </div>
          {data && (
            <div
              style={{
                fontSize: 12,
                color: "var(--v2-text-tertiary)",
                marginTop: 2,
                fontFamily: "SF Mono, Menlo, monospace",
                fontFeatureSettings: '"tnum"',
              }}
            >
              {data.status}
              {data.phase_index != null && ` | Phase ${data.phase_index}`}
            </div>
          )}
        </div>
        <button
          onClick={handleClose}
          data-testid="drawer-close"
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            fontSize: 18,
            color: "var(--v2-text-tertiary)",
            lineHeight: 1,
            padding: 4,
          }}
        >
          ✕
        </button>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--v2-border-soft)",
          paddingLeft: 20,
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            data-testid={`tab-${tab.key}`}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              padding: "10px 16px",
              fontSize: 13,
              fontWeight: 500,
              color:
                activeTab === tab.key
                  ? "var(--v2-accent-purple-700)"
                  : "var(--v2-text-secondary)",
              borderBottom:
                activeTab === tab.key
                  ? "2px solid var(--v2-accent-purple-700)"
                  : "2px solid transparent",
              marginBottom: -1,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 20,
        }}
      >
        {loading && (
          <div
            style={{
              fontSize: 13,
              color: "var(--v2-text-tertiary)",
              textAlign: "center",
              padding: "40px 0",
            }}
            data-testid="drawer-loading"
          >
            Loading node details...
          </div>
        )}

        {error && (
          <div
            style={{
              fontSize: 13,
              color: "var(--v2-status-error)",
              textAlign: "center",
              padding: "40px 0",
            }}
            data-testid="drawer-error"
          >
            {error}
          </div>
        )}

        {data && !loading && !error && (
          <TabContent tab={activeTab} data={data} />
        )}
      </div>

      {/* Footer: token usage */}
      {data?.token_usage && (
        <div
          style={{
            padding: "10px 20px",
            borderTop: "1px solid var(--v2-border-soft)",
            fontSize: 12,
            color: "var(--v2-text-tertiary)",
            display: "flex",
            gap: 16,
            fontFamily: "SF Mono, Menlo, monospace",
            fontFeatureSettings: '"tnum"',
          }}
        >
          <span>In: {data.token_usage.input}</span>
          <span>Out: {data.token_usage.output}</span>
        </div>
      )}
    </div>
  );
}

function TabContent({ tab, data }: { tab: TabKey; data: NodeDetail }) {
  const monoStyle: React.CSSProperties = {
    fontFamily: "SF Mono, Menlo, monospace",
    fontSize: 12,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    color: "var(--v2-text-primary)",
  };

  switch (tab) {
    case "input":
      return (
        <div data-testid="tab-content-input">
          {data.input ? (
            <pre style={monoStyle}>
              {JSON.stringify(data.input, null, 2)}
            </pre>
          ) : (
            <NoData />
          )}
        </div>
      );
    case "output":
      return (
        <div data-testid="tab-content-output">
          {data.output ? (
            <pre style={monoStyle}>
              {JSON.stringify(data.output, null, 2)}
            </pre>
          ) : (
            <NoData />
          )}
        </div>
      );
    case "thinking":
      return (
        <div data-testid="tab-content-thinking">
          {data.thinking ? (
            <p
              style={{
                ...monoStyle,
                whiteSpace: "pre-wrap",
              }}
            >
              {data.thinking}
            </p>
          ) : (
            <NoData />
          )}
        </div>
      );
    case "tools":
      return (
        <div data-testid="tab-content-tools">
          {data.tools && data.tools.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {data.tools.map((tool, i) => (
                <div
                  key={i}
                  style={{
                    background: "var(--v2-glass-bg)",
                    borderRadius: "var(--v2-radius-md)",
                    padding: 12,
                  }}
                >
                  <div
                    style={{
                      fontWeight: 600,
                      fontSize: 13,
                      color: "var(--v2-accent-purple-700)",
                      marginBottom: 6,
                    }}
                  >
                    {tool.name}
                  </div>
                  <pre style={monoStyle}>
                    {JSON.stringify(tool.args, null, 2)}
                  </pre>
                  {tool.result && (
                    <div
                      style={{
                        marginTop: 8,
                        paddingTop: 8,
                        borderTop: "1px solid var(--v2-border-soft)",
                        fontSize: 12,
                        color: "var(--v2-text-secondary)",
                      }}
                    >
                      {tool.result}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <NoData />
          )}
        </div>
      );
  }
}

function NoData() {
  return (
    <div
      style={{
        fontSize: 13,
        color: "var(--v2-text-tertiary)",
        textAlign: "center",
        padding: "24px 0",
      }}
    >
      No data available
    </div>
  );
}
