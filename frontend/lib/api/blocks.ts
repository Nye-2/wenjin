// Mirror of backend/src/agents/lead_agent/blocks.py — keep field names in sync.

import type { WorkspacePrismReviewItem } from "@/lib/api/types";

export interface TextBlock {
  kind: "text";
  content: string;
}

export interface ThinkingBlock {
  kind: "thinking";
  content: string;
}

export type StatusTone = "info" | "warn" | "error";

export interface StatusLineBlock {
  kind: "status_line";
  label: string;
  run_id: string;
  phase_index?: number | null;
  tone: StatusTone;
}

export interface Pill {
  label: string;
  intent: string;
}

export interface QuestionCardBlock {
  kind: "question_card";
  label: string;
  question: string;
  pills: Pill[];                            // 0-3
  context_ref_subagent_task_id?: string | null;
  context_ref_phase_index?: number | null;
}

export interface Finding { id: string; text: string; }
export interface Recommend { label: string; body: string; }
export interface Link { icon: string; label: string; href: string; }

export type FeedbackPillKind = "primary" | "normal" | "warn";
export interface FeedbackPill { kind: FeedbackPillKind; label: string; intent: string; }

export interface FeedbackBlock {
  question: string;
  pills: FeedbackPill[];
  allow_free_input: boolean;
}

export interface RunStats {
  duration_ms: number;
  subagents: number;
  tokens: number;
}

export interface ResultCardBlock {
  kind: "result_card";
  run_id: string;
  title: string;
  tldr: string;
  full_summary?: string | null;
  findings: Finding[];
  recommend?: Recommend | null;
  links: Link[];
  review_items?: WorkspacePrismReviewItem[];
  feedback: FeedbackBlock;
  stats: RunStats;
}

export interface ToolInvocationBlock {
  kind: "tool_invocation";
  tool: string;
  input: Record<string, unknown>;
  tool_call_id?: string | null;
}

export interface ToolResultBlock {
  kind: "tool_result";
  tool: string;
  status?: string | null;
  output: Record<string, unknown>;
  tool_call_id?: string | null;
  execution_id?: string | null;
  feature_id?: string | null;
}

export type AgentBlock =
  | TextBlock
  | ThinkingBlock
  | StatusLineBlock
  | QuestionCardBlock
  | ResultCardBlock
  | ToolInvocationBlock
  | ToolResultBlock;

export interface AgentMessage { blocks: AgentBlock[]; }

export const isText = (b: AgentBlock): b is TextBlock => b.kind === "text";
export const isThinking = (b: AgentBlock): b is ThinkingBlock => b.kind === "thinking";
export const isStatusLine = (b: AgentBlock): b is StatusLineBlock => b.kind === "status_line";
export const isQuestionCard = (b: AgentBlock): b is QuestionCardBlock => b.kind === "question_card";
export const isResultCard = (b: AgentBlock): b is ResultCardBlock => b.kind === "result_card";
export const isToolInvocation = (b: AgentBlock): b is ToolInvocationBlock => b.kind === "tool_invocation";
export const isToolResult = (b: AgentBlock): b is ToolResultBlock => b.kind === "tool_result";

type RawRecord = Record<string, unknown>;

function isRecord(value: unknown): value is RawRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return isRecord(value) ? { ...value } : undefined;
}

function rawKind(raw: RawRecord): string {
  return String(raw.kind ?? raw.type ?? "").trim();
}

function toolSource(raw: RawRecord): RawRecord {
  return isRecord(raw.data) ? raw.data : raw;
}

function extractToolName(raw: RawRecord, fallback = "unknown"): string {
  const direct =
    stringValue(raw.tool) ??
    stringValue(raw.tool_name) ??
    stringValue(raw.name) ??
    stringValue(raw.function_name);
  if (direct) return direct;
  if (isRecord(raw.function)) {
    return stringValue(raw.function.name) ?? fallback;
  }
  return fallback;
}

function extractToolInput(raw: RawRecord): Record<string, unknown> {
  return (
    recordValue(raw.input) ??
    recordValue(raw.args) ??
    recordValue(raw.arguments) ??
    recordValue(raw.parameters) ??
    {}
  );
}

function extractToolCallId(raw: RawRecord): string | undefined {
  return (
    stringValue(raw.tool_call_id) ??
    stringValue(raw.invocation_id) ??
    stringValue(raw.call_id) ??
    stringValue(raw.id)
  );
}

function extractThinkingContent(raw: RawRecord): string {
  const data = isRecord(raw.data) ? raw.data : undefined;
  return (
    stringValue(raw.content) ??
    stringValue(raw.text) ??
    (data ? stringValue(data.text) : undefined) ??
    (data ? stringValue(data.content) : undefined) ??
    ""
  );
}

function extractToolOutput(raw: RawRecord, source: RawRecord): Record<string, unknown> {
  const rawOutput = recordValue(raw.output);
  if (rawOutput) return rawOutput;
  const sourceOutput = recordValue(source.output);
  if (sourceOutput) return sourceOutput;
  const rawResult = recordValue(raw.result);
  if (rawResult) return rawResult;
  const sourceResult = recordValue(source.result);
  if (sourceResult) return sourceResult;
  if (isRecord(raw.data)) {
    return { ...raw.data };
  }
  return { ...source };
}

export function normalizeChatBlock(raw: unknown): AgentBlock {
  if (!isRecord(raw)) {
    return { kind: "text", content: String(raw ?? "") };
  }

  const kind = rawKind(raw);

  if (kind === "reasoning" || kind === "thought" || kind === "thinking") {
    return { kind: "thinking", content: extractThinkingContent(raw) };
  }

  if (kind === "tool_invocation" || kind === "tool" || kind === "tool_call" || kind === "tool_use") {
    const source = toolSource(raw);
    const block: ToolInvocationBlock = {
      kind: "tool_invocation",
      tool: extractToolName(source, extractToolName(raw, "unknown")),
      input: extractToolInput(source),
    };
    const toolCallId = extractToolCallId(source) ?? extractToolCallId(raw);
    if (toolCallId) block.tool_call_id = toolCallId;
    return block;
  }

  if (kind === "tool_result") {
    const source = toolSource(raw);
    const output = extractToolOutput(raw, source);
    const block: ToolResultBlock = {
      kind: "tool_result",
      tool: extractToolName(source, extractToolName(raw, "unknown")),
      output,
    };
    const status = stringValue(source.status) ?? stringValue(raw.status);
    if (status) block.status = status;
    const toolCallId = extractToolCallId(source) ?? extractToolCallId(raw);
    if (toolCallId) block.tool_call_id = toolCallId;
    const executionId = stringValue(source.execution_id) ?? stringValue(raw.execution_id) ?? stringValue(output.execution_id);
    if (executionId) block.execution_id = executionId;
    const featureId = stringValue(source.feature_id) ?? stringValue(raw.feature_id) ?? stringValue(output.feature_id);
    if (featureId) block.feature_id = featureId;
    return block;
  }

  if (kind && kind !== raw.kind) {
    const { type: _type, ...rest } = raw;
    return { ...rest, kind } as AgentBlock;
  }

  if (!kind) {
    return { kind: "text", content: String(raw.content ?? "") };
  }

  return raw as unknown as AgentBlock;
}
