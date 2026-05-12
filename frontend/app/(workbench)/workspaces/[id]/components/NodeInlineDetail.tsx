"use client";

import { useState } from "react";
import type { ExecutionNodeState } from "@/lib/api/types";

export interface NodeInlineDetailProps {
  state: ExecutionNodeState;
}

type TabKey = "input" | "output" | "thinking";

const TABS: { key: TabKey; label: string }[] = [
  { key: "input", label: "Input" },
  { key: "output", label: "Output" },
  { key: "thinking", label: "Thinking" },
];

export function NodeInlineDetail({ state }: NodeInlineDetailProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("output");

  const getTabContent = (): string => {
    switch (activeTab) {
      case "input":
        return state.input ? JSON.stringify(state.input, null, 2) : "";
      case "output":
        return state.output ? JSON.stringify(state.output, null, 2) : "";
      case "thinking":
        return state.thinking ?? "";
    }
  };

  const content = getTabContent();

  // Token usage bar
  const tokenUsage = state.token_usage;
  const totalTokens = tokenUsage
    ? Object.values(tokenUsage).reduce((sum, v) => sum + v, 0)
    : 0;

  return (
    <div
      style={{
        marginTop: 6,
        borderRadius: "var(--v2-radius-md)",
        background: "var(--v2-surface-soft)",
        border: "1px solid var(--v2-border-soft)",
        overflow: "hidden",
        fontFamily: "var(--v2-font-sans)",
        fontSize: 12,
        color: "var(--v2-text-primary)",
      }}
    >
      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--v2-border-soft)",
          background: "rgba(255, 255, 255, 0.5)",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: "6px 12px",
              fontSize: 11,
              fontWeight: 500,
              fontFamily: "var(--v2-font-sans)",
              color:
                activeTab === tab.key
                  ? "var(--v2-accent-purple-700)"
                  : "var(--v2-text-secondary)",
              background:
                activeTab === tab.key
                  ? "rgba(139, 92, 246, 0.06)"
                  : "transparent",
              border: "none",
              borderBottom:
                activeTab === tab.key
                  ? "2px solid var(--v2-accent-purple-700)"
                  : "2px solid transparent",
              cursor: "pointer",
              transition: "all var(--v2-duration-fast) var(--v2-ease-standard)",
              outline: "none",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content area */}
      <div
        style={{
          padding: "8px 12px",
          maxHeight: 200,
          overflow: "auto",
          background: "rgba(255, 255, 255, 0.3)",
        }}
      >
        {content ? (
          <pre
            style={{
              margin: 0,
              fontFamily: "var(--v2-font-mono)",
              fontSize: 11,
              lineHeight: 1.5,
              color: "var(--v2-text-primary)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {content}
          </pre>
        ) : (
          <span
            style={{
              fontFamily: "var(--v2-font-sans)",
              fontSize: 11,
              color: "var(--v2-text-tertiary)",
            }}
          >
            No data available
          </span>
        )}
      </div>

      {/* Token usage bar */}
      {tokenUsage && totalTokens > 0 && (
        <div
          style={{
            padding: "6px 12px",
            borderTop: "1px solid var(--v2-border-soft)",
            background: "rgba(255, 255, 255, 0.4)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              color: "var(--v2-text-secondary)",
              fontFamily: "var(--v2-font-sans)",
              flexShrink: 0,
            }}
          >
            Tokens
          </span>
          <div
            style={{
              flex: 1,
              height: 4,
              borderRadius: 2,
              background: "var(--v2-border-default)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                borderRadius: 2,
                background:
                  "linear-gradient(90deg, var(--v2-accent-purple-500), var(--v2-accent-purple-700))",
                width: `${Math.min(100, (totalTokens / 100000) * 100)}%`,
                transition: "width var(--v2-duration-medium) var(--v2-ease-standard)",
              }}
            />
          </div>
          <span
            style={{
              fontSize: 10,
              fontFamily: "var(--v2-font-mono)",
              color: "var(--v2-text-secondary)",
              flexShrink: 0,
            }}
          >
            {totalTokens.toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );
}
