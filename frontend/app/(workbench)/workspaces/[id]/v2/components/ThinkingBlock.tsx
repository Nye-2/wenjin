"use client";

import { useState } from "react";

function filterThinkingContent(content: string): string {
  const lines = content.split("\n");
  const filtered = lines.filter(
    (line) =>
      !/^(我是|I am|I'm)\s.*(MiMo|GPT|Claude|ChatGPT|助手|模型|AI)/i.test(line.trim()) &&
      !/由.{2,10}(团队|公司|开发)/.test(line.trim()) &&
      !/虽然我自己/.test(line.trim()) &&
      !/不是专门的/.test(line.trim()),
  );
  return filtered.join("\n").trim();
}

interface ThinkingBlockProps {
  content: string;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const filtered = filterThinkingContent(content);
  if (!filtered) return null;

  return (
    <div style={{ margin: "4px 0" }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          padding: "2px 6px",
          border: "none",
          background: "transparent",
          cursor: "pointer",
          fontSize: 12,
          color: "var(--v2-text-tertiary)",
          borderRadius: "var(--v2-radius-sm)",
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        <span
          style={{
            fontSize: 10,
            transition: "transform 150ms",
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
          }}
        >
          ▶
        </span>
        思考过程
      </button>
      {expanded && (
        <div
          style={{
            padding: "8px 12px",
            marginLeft: 12,
            borderLeft: "2px solid var(--v2-border-default)",
            color: "var(--v2-text-tertiary)",
            fontSize: 12.5,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {filtered}
        </div>
      )}
    </div>
  );
}
