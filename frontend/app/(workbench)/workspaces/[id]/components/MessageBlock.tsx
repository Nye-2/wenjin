"use client";

import { memo } from "react";
import { CheckCircle2, FileText } from "lucide-react";
import type {
  FeedbackPill,
  QuestionCardBlock as AgentQuestionCardBlock,
  ResultCardBlock as AgentResultCardBlock,
  ToolResultBlock as AgentToolResultBlock,
} from "@/lib/api/blocks";
import {
  readIntakeSpecFromToolResultData,
  type IntakeSpecV1,
} from "@/lib/intake-spec";
import type { Block, ResultCardData } from "@/stores/chat-store";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { PrismReviewList } from "@/components/prism/PrismReviewList";
import { ThinkingBlock } from "./ThinkingBlock";
import { StatusLineBlock } from "./StatusLineBlock";
import { ResultCard } from "./ResultCard";
import { WorkspaceActionLink } from "./WorkspaceActionLink";
import {
  writeModeDescription,
  writeModeLabel,
} from "./review-changes/WriteModeSelector";
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
          background: "var(--wjn-blue)",
          color: "#FFFFFF",
          border: "var(--wjn-blue)",
        }
      : tone === "warn"
        ? {
            background: "rgba(185, 28, 28, 0.08)",
            color: "#B91C1C",
            border: "rgba(185, 28, 28, 0.16)",
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

function ToolResultBlock({
  data,
  workspaceId,
}: {
  data: Record<string, unknown>;
  workspaceId?: string;
}) {
  const intakeSpec = readIntakeSpecFromToolResultData(data);
  if (intakeSpec) {
    return (
      <IntakeSpecToolResultCard
        spec={intakeSpec}
        workspaceId={workspaceId}
      />
    );
  }

  const status = String(data.status || "");
  const code = typeof data.code === "string" ? data.code.trim() : "";
  const executionId =
    typeof data.execution_id === "string" ? data.execution_id.trim() : "";
  const capabilityName =
    typeof data.capability_name === "string" && data.capability_name.trim()
      ? data.capability_name.trim()
      : "研究任务";
  const writeMode =
    typeof data.write_mode === "string" && data.write_mode.trim()
      ? data.write_mode.trim()
      : null;

  if (status === "launched" && executionId) {
    return (
      <div
        data-testid="run-receipt"
        style={{
          padding: "12px 14px",
          background: "var(--wjn-accent-soft)",
          borderRadius: "var(--wjn-radius-lg)",
          border: "1px solid var(--wjn-accent-line)",
          margin: "8px 0",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 6,
          }}
        >
          <div
            style={{
              fontSize: 14,
              fontWeight: 650,
              color: "var(--wjn-text)",
            }}
          >
            已启动：{capabilityName}
          </div>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--wjn-blue)",
              background: "var(--wjn-accent-soft)",
              borderRadius: "var(--wjn-radius-pill)",
              padding: "2px 8px",
            }}
          >
            处理中
          </span>
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--wjn-text-secondary)",
            lineHeight: 1.5,
          }}
        >
          问津已开始处理。右侧工作台会展示关键进展，完成后结果会回到这里。
        </div>
        {writeMode ? (
          <div
            style={{
              marginTop: 8,
              padding: "7px 9px",
              borderRadius: "var(--wjn-radius)",
              border: "1px solid rgba(20,20,30,0.08)",
              background: "rgba(255,255,255,0.64)",
              color: "var(--wjn-text-secondary)",
              fontSize: 12,
              lineHeight: 1.45,
            }}
          >
            写入模式：<strong style={{ color: "var(--wjn-text)" }}>
              {writeModeLabel(writeMode)}
            </strong>
            <span>。{writeModeDescription(writeMode)}</span>
          </div>
        ) : null}
        {workspaceId ? (
          <div style={{ display: "flex", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
            <WorkspaceActionLink
              href={`/workspaces/${workspaceId}`}
              style={{
                color: "var(--wjn-blue)",
                fontSize: 12.5,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              查看执行
            </WorkspaceActionLink>
            <WorkspaceActionLink
              href={`/workspaces/${workspaceId}?room=runs`}
              style={{
                color: "var(--wjn-blue)",
                fontSize: 12.5,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              打开运行记录
            </WorkspaceActionLink>
          </div>
        ) : null}
      </div>
    );
  }

  if (status === "lead_busy" || code === "lead_busy") {
    return (
      <div
        style={{
          padding: "8px 10px",
          background: "rgba(198, 138, 26, 0.1)",
          borderRadius: "var(--wjn-radius)",
          fontSize: 12.5,
          color: "var(--semantic-warning)",
          margin: "6px 0",
        }}
      >
        当前任务仍在执行，请先查看右侧进展或运行记录。
      </div>
    );
  }

  if (status === "error") {
    return (
      <div
        style={{
          padding: "8px 10px",
          background: "rgba(220, 38, 38, 0.08)",
          borderRadius: "var(--wjn-radius)",
          fontSize: 12.5,
          color: "var(--wjn-error)",
          margin: "6px 0",
        }}
      >
        {sanitizeUserFacingError(data.detail)}
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "6px 10px",
        background: "var(--wjn-bg-base)",
        borderRadius: "var(--wjn-radius)",
        fontSize: 12,
        color: "var(--wjn-text-secondary)",
        margin: "4px 0",
      }}
    >
      ✓ {status === "advisory" ? "需要补充信息" : "已处理"}
    </div>
  );
}

function IntakeSpecToolResultCard({
  spec,
  workspaceId,
}: {
  spec: IntakeSpecV1;
  workspaceId?: string;
}) {
  const setActiveWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.setActiveWorkbenchTab,
  );
  const sendMessage = useChatStoreV2((state) => state.sendMessage);
  const isSending = useChatStoreV2((state) => state.isSending);
  const ready = spec.status === "ready" && spec.missing_fields.length === 0;
  const statusLabel = ready ? "可执行" : "待补充";

  async function approve() {
    if (!workspaceId || !ready || isSending) {
      return;
    }
    setActiveWorkbenchTab("spec");
    await sendMessage(
      workspaceId,
      [
        `同意并开始执行这份 Spec：${spec.title}`,
        "请按澄清文档中的范围和参数启动团队执行。",
      ].join("\n"),
      [],
      {
        metadata: {
          orchestration: {
            feature_id: spec.capability_id,
            params: spec.params,
          },
          intake_spec_launch: {
            spec_id: spec.spec_id,
            revision: spec.revision,
          },
        },
      },
    );
  }

  return (
    <div
      style={{
        padding: "12px 14px",
        background: "var(--wjn-surface-raised)",
        borderRadius: "var(--wjn-radius-lg)",
        border: "1px solid var(--wjn-line)",
        boxShadow: "var(--wjn-shadow-sm)",
        margin: "8px 0",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 10,
          marginBottom: 6,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: "var(--wjn-text)",
              lineHeight: 1.35,
              overflowWrap: "anywhere",
            }}
          >
            {spec.title}
          </div>
          <div
            style={{
              marginTop: 3,
              fontSize: 12.5,
              color: "var(--wjn-text-muted)",
            }}
          >
            澄清 Spec · {statusLabel}
          </div>
        </div>
        <FileText size={17} color="var(--wjn-blue)" />
      </div>
      {spec.missing_fields.length > 0 ? (
        <div
          style={{
            marginTop: 8,
            fontSize: 12.5,
            color: "var(--wjn-warning)",
          }}
        >
          还缺少：{spec.missing_fields.join("、")}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <button
          type="button"
          onClick={() => setActiveWorkbenchTab("spec")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            height: 30,
            padding: "0 10px",
            borderRadius: 8,
            border: "1px solid var(--wjn-accent-line)",
            background: "var(--wjn-accent-soft)",
            color: "var(--wjn-accent-strong)",
            fontSize: 12.5,
            fontWeight: 650,
            cursor: "pointer",
          }}
        >
          <FileText size={13} />
          <span>查看 Spec</span>
        </button>
        <button
          type="button"
          disabled={!workspaceId || !ready || isSending}
          onClick={() => void approve()}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            height: 30,
            padding: "0 10px",
            borderRadius: 8,
            border: ready ? "1px solid var(--wjn-blue)" : "1px solid var(--wjn-line)",
            background: ready ? "var(--wjn-blue)" : "var(--wjn-bg-base)",
            color: ready ? "#FFFFFF" : "var(--wjn-text-muted)",
            fontSize: 12.5,
            fontWeight: 650,
            cursor: !workspaceId || !ready || isSending ? "not-allowed" : "pointer",
            opacity: !workspaceId || !ready || isSending ? 0.56 : 1,
          }}
        >
          <CheckCircle2 size={13} />
          <span>同意执行</span>
        </button>
      </div>
    </div>
  );
}

function sanitizeUserFacingError(detail: unknown): string {
  if (typeof detail !== "string" || !detail.trim()) {
    return "任务启动失败，请补充需求后再试一次。";
  }
  const text = detail.trim();
  if (
    text.includes("Feature") ||
    text.includes("launch_feature") ||
    text.includes("capability") ||
    text.includes("DataService") ||
    text.includes("Traceback")
  ) {
    return "这次任务没有成功启动。请换一种说法补充研究主题、目标结果或材料，我会重新判断要不要召集团队。";
  }
  return text;
}

function toolInvocationLabel(tool: unknown): string {
  const value = typeof tool === "string" ? tool : "";
  if (value.includes("launch_feature")) {
    return "正在启动研究团队";
  }
  return "正在处理请求";
}

function toolResultDisplayData(block: AgentToolResultBlock): Record<string, unknown> {
  const output =
    block.output && typeof block.output === "object" && !Array.isArray(block.output)
      ? (block.output as Record<string, unknown>)
      : {};
  const blockRecord = block as unknown as Record<string, unknown>;
  return {
    ...output,
    status: block.status ?? output.status,
    execution_id: block.execution_id ?? output.execution_id,
    feature_id: block.feature_id ?? output.feature_id,
    tool_call_id: block.tool_call_id ?? output.tool_call_id,
    write_mode: blockRecord.write_mode ?? output.write_mode,
    tool: block.tool,
  };
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
      return <ThinkingBlock content={block.text} />;
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
            background: "var(--wjn-accent-soft)",
            borderRadius: "var(--wjn-radius)",
            fontSize: 12,
            color: "var(--wjn-blue)",
            margin: "4px 0",
        }}
      >
          ⚡ {toolInvocationLabel(block.tool)}
        </div>
      );
    case "tool_result":
      return (
        <ToolResultBlock
          data={toolResultDisplayData(block)}
          workspaceId={workspaceId}
        />
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
