"use client";

import { memo } from "react";
import type {
  FeedbackPill,
  QuestionCardBlock as AgentQuestionCardBlock,
  ResultCardBlock as AgentResultCardBlock,
} from "@/lib/api/blocks";
import type { Block, ResultCardData } from "@/stores/chat-store";
import { PrismReviewList } from "@/components/prism/PrismReviewList";
import { ThinkingBlock } from "./ThinkingBlock";
import { StatusLineBlock } from "./StatusLineBlock";
import { ResultCard } from "./ResultCard";
import { WorkspaceActionLink } from "./WorkspaceActionLink";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const markdownComponents = {
  a: ({
    href,
    children,
  }: {
    href?: string;
    children?: React.ReactNode;
  }) => {
    if (!href) {
      return <span>{children}</span>;
    }
    return (
      <WorkspaceActionLink
        href={href}
        style={{
          color: "var(--v2-accent-blue-700)",
          textDecoration: "underline",
          textUnderlineOffset: 2,
        }}
      >
        {children}
      </WorkspaceActionLink>
    );
  },
};

interface MessageBlockProps {
  block: Block;
  workspaceId?: string;
  onIntent?: (
    intent: string,
    sourceBlockKind: "question_card" | "result_card",
  ) => void;
  intentDisabled?: boolean;
}

type AsyncResultCardBlock = { kind: "result_card"; data: ResultCardData };

function isAsyncResultCard(block: Block): block is AsyncResultCardBlock {
  return block.kind === "result_card" && "data" in block;
}

function isAgentResultCard(block: Block): block is AgentResultCardBlock {
  return block.kind === "result_card" && "run_id" in block;
}

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  return `${(durationMs / 1000).toFixed(durationMs % 1000 === 0 ? 0 : 1)}s`;
}

function ActionPill({
  label,
  tone = "normal",
  disabled = false,
  onClick,
}: {
  label: string;
  tone?: FeedbackPill["kind"];
  disabled?: boolean;
  onClick: () => void;
}) {
  const palette =
    tone === "primary"
      ? {
          background: "var(--v2-accent-purple-700)",
          color: "#FFFFFF",
          border: "var(--v2-accent-purple-700)",
        }
      : tone === "warn"
        ? {
            background: "rgba(185, 28, 28, 0.08)",
            color: "#B91C1C",
            border: "rgba(185, 28, 28, 0.16)",
          }
        : {
            background: "var(--v2-surface-soft)",
            color: "var(--v2-text-secondary)",
            border: "var(--v2-border-default)",
          };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: "6px 12px",
        borderRadius: "var(--v2-radius-pill)",
        border: `1px solid ${palette.border}`,
        background: palette.background,
        color: palette.color,
        fontSize: 12.5,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {label}
    </button>
  );
}

function QuestionCard({
  block,
  onIntent,
  disabled = false,
}: {
  block: AgentQuestionCardBlock;
  onIntent?: (
    intent: string,
    sourceBlockKind: "question_card" | "result_card",
  ) => void;
  disabled?: boolean;
}) {
  return (
    <div
      style={{
        padding: "12px",
        background: "var(--v2-surface-soft)",
        borderRadius: "var(--v2-radius-md)",
        margin: "8px 0",
        fontSize: 13.5,
        border: "1px solid var(--v2-border-soft)",
      }}
    >
      <div
        style={{
          fontSize: 11.5,
          fontWeight: 600,
          color: "var(--v2-text-tertiary)",
          marginBottom: 6,
        }}
      >
        {block.label}
      </div>
      <div style={{ color: "var(--v2-text-primary)" }}>{block.question}</div>
      {block.pills.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginTop: 10,
          }}
        >
          {block.pills.map((pill) => (
            <ActionPill
              key={`${pill.intent}:${pill.label}`}
              label={pill.label}
              disabled={disabled}
              onClick={() => onIntent?.(pill.intent, "question_card")}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentResultCard({
  block,
  onIntent,
  disabled = false,
}: {
  block: AgentResultCardBlock;
  onIntent?: (
    intent: string,
    sourceBlockKind: "question_card" | "result_card",
  ) => void;
  disabled?: boolean;
}) {
  return (
    <div
      style={{
        padding: "14px",
        background: "var(--v2-glass-bg)",
        borderRadius: "var(--v2-radius-lg)",
        border: "1px solid var(--v2-glass-border)",
        boxShadow: "var(--v2-glass-shadow)",
        margin: "8px 0",
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: "var(--v2-text-primary)",
          marginBottom: 6,
        }}
      >
        {block.title}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--v2-text-secondary)",
          lineHeight: 1.6,
          marginBottom: block.findings.length > 0 ? 10 : 0,
        }}
      >
        {block.tldr}
      </div>
      {block.findings.length > 0 && (
        <div style={{ display: "grid", gap: 8, marginBottom: 10 }}>
          {block.findings.map((finding) => (
            <div
              key={finding.id}
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                color: "var(--v2-text-primary)",
                fontSize: 13,
              }}
            >
              <span
                style={{
                  minWidth: 18,
                  color: "var(--v2-accent-purple-700)",
                  fontWeight: 600,
                }}
              >
                {finding.id}
              </span>
              <span>{finding.text}</span>
            </div>
          ))}
        </div>
      )}
      {block.recommend && (
        <div
          style={{
            marginBottom: 10,
            padding: "10px 12px",
            borderRadius: "var(--v2-radius-md)",
            background: "rgba(124, 58, 237, 0.06)",
            border: "1px solid rgba(124, 58, 237, 0.12)",
          }}
        >
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--v2-accent-purple-700)",
              marginBottom: 4,
            }}
          >
            {block.recommend.label}
          </div>
          <div style={{ fontSize: 13, color: "var(--v2-text-secondary)" }}>
            {block.recommend.body}
          </div>
        </div>
      )}
      {block.review_items?.length ? (
        <div style={{ marginBottom: 10 }}>
          <PrismReviewList items={block.review_items} />
        </div>
      ) : null}
      {block.links.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            marginBottom: 10,
          }}
        >
          {block.links.map((link) => (
            <WorkspaceActionLink
              key={`${link.href}:${link.label}`}
              href={link.href}
              style={{
                color: "var(--v2-accent-blue-700)",
                fontSize: 12.5,
                fontWeight: 500,
                textDecoration: "none",
              }}
            >
              {link.label}
            </WorkspaceActionLink>
          ))}
        </div>
      )}
      <div
        style={{
          display: "flex",
          gap: 10,
          flexWrap: "wrap",
          fontSize: 12,
          color: "var(--v2-text-tertiary)",
          marginBottom: 10,
        }}
      >
        <span>{formatDuration(block.stats.duration_ms)}</span>
        <span>{block.stats.subagents} 个子代理</span>
        <span>{block.stats.tokens} tokens</span>
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--v2-text-secondary)",
          marginBottom: block.feedback.pills.length > 0 ? 8 : 0,
        }}
      >
        {block.feedback.question}
      </div>
      {block.feedback.pills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {block.feedback.pills.map((pill) => (
            <ActionPill
              key={`${pill.intent}:${pill.label}`}
              label={pill.label}
              tone={pill.kind}
              disabled={disabled}
              onClick={() => onIntent?.(pill.intent, "result_card")}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export const MessageBlock = memo(function MessageBlock({
  block,
  workspaceId,
  onIntent,
  intentDisabled = false,
}: MessageBlockProps) {
  switch (block.kind) {
    case "text":
      return (
        <div className="prose-chat">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {block.content}
          </ReactMarkdown>
        </div>
      );
    case "thinking":
      return <ThinkingBlock content={block.content} />;
    case "status_line":
      return (
        <StatusLineBlock
          label={block.label}
          tone={block.tone}
          phaseIndex={block.phase_index ?? null}
        />
      );
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
      if (isAsyncResultCard(block)) {
        return <ResultCard data={block.data} workspaceId={workspaceId} />;
      }
      if (isAgentResultCard(block)) {
        return (
          <AgentResultCard
            block={block}
            onIntent={onIntent}
            disabled={intentDisabled}
          />
        );
      }
      return null;
    case "question_card":
      return (
        <QuestionCard
          block={block}
          onIntent={onIntent}
          disabled={intentDisabled}
        />
      );
    default:
      return null;
  }
});
