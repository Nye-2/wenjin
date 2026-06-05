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

  return (
    <div
      style={{
        marginTop: 6,
        borderRadius: "var(--wjn-radius-md)",
        background: "var(--wjn-bg-base)",
        border: "1px solid var(--wjn-line)",
        overflow: "hidden",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 12,
        color: "var(--wjn-text)",
      }}
    >
      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--wjn-line)",
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
              fontFamily: "var(--wjn-font-sans)",
              color:
                activeTab === tab.key
                  ? "var(--wjn-blue)"
                  : "var(--wjn-text-secondary)",
              background:
                activeTab === tab.key
                  ? "var(--wjn-accent-soft)"
                  : "transparent",
              border: "none",
              borderBottom:
                activeTab === tab.key
                  ? "2px solid var(--wjn-blue)"
                  : "2px solid transparent",
              cursor: "pointer",
              transition: "all var(--wjn-duration-fast) var(--wjn-ease-standard)",
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
              fontFamily: "var(--wjn-font-mono)",
              fontSize: 11,
              lineHeight: 1.5,
              color: "var(--wjn-text)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {content}
          </pre>
        ) : (
          <span
            style={{
              fontFamily: "var(--wjn-font-sans)",
              fontSize: 11,
              color: "var(--wjn-text-muted)",
            }}
          >
            No data available
          </span>
        )}
      </div>

    </div>
  );
}
