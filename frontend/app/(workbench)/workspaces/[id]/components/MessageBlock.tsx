"use client";

import { memo } from "react";
import type {
  FeedbackPill,
  QuestionCardBlock as AgentQuestionCardBlock,
  ResultCardBlock as AgentResultCardBlock,
} from "@/lib/api/blocks";
import type { Block } from "@/stores/chat-store";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { MissionCard } from "./MissionCardBlock";
import { ThinkingBlock } from "./ThinkingBlock";
import { StatusLineBlock } from "./StatusLineBlock";
import { WorkspaceActionLink } from "./WorkspaceActionLink";
import type { Components } from "react-markdown";

const messageMarkdownComponents: Components = {
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
          color: "var(--wjn-blue)",
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
  onMaterialAction?: () => void;
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
          background: "var(--wjn-blue)",
          color: "#FFFFFF",
          border: "var(--wjn-blue)",
        }
      : tone === "warn"
        ? {
            background: "var(--wjn-error-soft)",
            color: "var(--wjn-error)",
            border: "rgba(179, 52, 62, 0.22)",
          }
        : {
            background: "var(--wjn-bg-base)",
            color: "var(--wjn-text-secondary)",
            border: "var(--wjn-line)",
          };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: "6px 12px",
        borderRadius: "var(--wjn-radius-pill)",
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
        background: "var(--wjn-bg-base)",
        borderRadius: "var(--wjn-radius-md)",
        margin: "8px 0",
        fontSize: 13.5,
        border: "1px solid var(--wjn-line)",
      }}
    >
      <div
        style={{
          fontSize: 11.5,
          fontWeight: 600,
          color: "var(--wjn-text-muted)",
          marginBottom: 6,
        }}
      >
        {block.label}
      </div>
      <div style={{ color: "var(--wjn-text)" }}>{block.question}</div>
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
        background: "var(--wjn-surface-raised)",
        borderRadius: "var(--wjn-radius-lg)",
        border: "1px solid var(--wjn-line)",
        boxShadow: "var(--wjn-shadow-sm)",
        margin: "8px 0",
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: "var(--wjn-text)",
          marginBottom: 6,
        }}
      >
        {block.title}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--wjn-text-secondary)",
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
                color: "var(--wjn-text)",
                fontSize: 13,
              }}
            >
              <span
                style={{
                  minWidth: 18,
                  color: "var(--wjn-blue)",
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
            borderRadius: "var(--wjn-radius-md)",
            background: "var(--wjn-accent-soft)",
            border: "1px solid var(--wjn-accent-soft)",
          }}
        >
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-blue)",
              marginBottom: 4,
            }}
          >
            {block.recommend.label}
          </div>
          <div style={{ fontSize: 13, color: "var(--wjn-text-secondary)" }}>
            {block.recommend.body}
          </div>
        </div>
      )}
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
                color: "var(--wjn-blue)",
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
          color: "var(--wjn-text-muted)",
          marginBottom: 10,
        }}
      >
        <span>{formatDuration(block.stats.duration_ms)}</span>
        <span>{block.stats.subagents} 个团队成员</span>
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--wjn-text-secondary)",
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
  onIntent,
  intentDisabled = false,
  onMaterialAction,
}: MessageBlockProps) {
  switch (block.kind) {
    case "text":
      return (
        <MarkdownRenderer
          content={block.content}
          className="prose-chat"
          components={messageMarkdownComponents}
        />
      );
    case "thinking":
      return <ThinkingBlock content={block.text} />;
    case "status_line":
      return (
        <StatusLineBlock
          label={block.label}
          tone={block.tone}
          phaseIndex={block.phase_index ?? null}
        />
      );
    case "result_card":
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
    case "mission_card":
      return <MissionCard block={block} onMaterialAction={onMaterialAction} />;
    default:
      return null;
  }
});
