"use client";

import { memo } from "react";
import type { Block } from "@/stores/chat-store-v2";
import { ThinkingBlock } from "./ThinkingBlock";
import { StatusLineBlock } from "./StatusLineBlock";
import { ResultCard, type ResultCardFullData } from "./ResultCard";

interface MessageBlockProps {
  block: Block;
}

export const MessageBlock = memo(function MessageBlock({ block }: MessageBlockProps) {
  switch (block.kind) {
    case "text":
      return <span style={{ whiteSpace: "pre-wrap" }}>{block.content}</span>;
    case "thinking":
      return <ThinkingBlock content={block.content} />;
    case "status_line":
      return <StatusLineBlock content={block.content} />;
    case "tool_invocation":
      return (
        <div
          style={{
            padding: "6px 10px",
            background: "var(--v2-accent-purple-100)",
            borderRadius: "var(--v2-radius-sm)",
            fontSize: 12,
            color: "var(--v2-accent-purple-700)",
            margin: "4px 0",
          }}
        >
          ⚡ {block.data.tool}
        </div>
      );
    case "tool_result":
      return (
        <div
          style={{
            padding: "6px 10px",
            background: "var(--v2-surface-soft)",
            borderRadius: "var(--v2-radius-sm)",
            fontSize: 12,
            color: "var(--v2-text-secondary)",
            margin: "4px 0",
          }}
        >
          ✓ {block.data.status}
        </div>
      );
    case "result_card":
      return <ResultCard data={block.data as unknown as ResultCardFullData} />;
    case "question_card":
      return (
        <div
          style={{
            padding: "12px",
            background: "var(--v2-surface-soft)",
            borderRadius: "var(--v2-radius-md)",
            margin: "8px 0",
            fontSize: 13.5,
          }}
        >
          ❓ {block.data.question}
        </div>
      );
    default:
      return null;
  }
});
