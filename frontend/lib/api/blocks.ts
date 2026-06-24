// Mirror of backend/src/agents/lead_agent/blocks.py — keep field names in sync.

import type { WorkspacePrismReviewItem } from "@/lib/api/types";

export interface TextBlock {
  kind: "text";
  content: string;
}

export interface ThinkingBlock {
  kind: "thinking";
  text: string;
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

function isSafeVisibleText(value: string): boolean {
  const lowered = value.toLowerCase();
  return ![
    "/mnt/user-data",
    "/workspace/",
    "/private/",
    "output_ref",
    "storage_path",
  ].some((marker) => lowered.includes(marker));
}

function safeStringValue(value: unknown): string | undefined {
  const text = stringValue(value);
  return text && isSafeVisibleText(text) ? text : undefined;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return isRecord(value) ? { ...value } : undefined;
}

function rawKind(raw: RawRecord): string {
  return String(raw.kind ?? raw.type ?? "").trim();
}

function titledDetailText(raw: RawRecord): string {
  const data = isRecord(raw.data) ? raw.data : undefined;
  const content = isRecord(raw.content) ? raw.content : undefined;
  const title =
    safeStringValue(raw.title) ??
    safeStringValue(raw.label) ??
    safeStringValue(raw.name);
  const detail =
    safeStringValue(raw.detail) ??
    safeStringValue(raw.message) ??
    safeStringValue(raw.summary) ??
    (data ? safeStringValue(data.detail) : undefined) ??
    (data ? safeStringValue(data.message) : undefined) ??
    (data ? safeStringValue(data.summary) : undefined) ??
    (data ? safeStringValue(data.text) : undefined) ??
    (data ? safeStringValue(data.content) : undefined) ??
    (content ? safeStringValue(content.detail) : undefined) ??
    (content ? safeStringValue(content.message) : undefined) ??
    (content ? safeStringValue(content.summary) : undefined) ??
    (content ? safeStringValue(content.text) : undefined) ??
    (content ? safeStringValue(content.content) : undefined) ??
    safeStringValue(raw.content) ??
    safeStringValue(raw.text);
  if (title && detail && title !== detail) {
    return `${title}：${detail}`;
  }
  return title ?? detail ?? "";
}

function fallbackTextBlock(raw: RawRecord): TextBlock {
  const text = titledDetailText(raw);
  if (text) return { kind: "text", content: text };
  return { kind: "text", content: "Unsupported message block" };
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
    stringValue(raw.text) ??
    stringValue(raw.content) ??
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

function normalizeLinks(value: unknown): Link[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item) => ({
      icon: stringValue(item.icon) ?? "",
      label: stringValue(item.label) ?? "",
      href: stringValue(item.href) ?? "",
    }))
    .filter((item) => item.label || item.href);
}

function normalizeFindings(value: unknown): Finding[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item, index) => ({
      id: stringValue(item.id) ?? String(index + 1),
      text: stringValue(item.text) ?? "",
    }))
    .filter((item) => item.text);
}

function normalizeFeedback(value: unknown): FeedbackBlock {
  const raw = isRecord(value) ? value : {};
  const pills = Array.isArray(raw.pills)
    ? raw.pills
        .filter(isRecord)
        .map((item) => {
          const kind: FeedbackPillKind =
            item.kind === "primary" || item.kind === "warn" || item.kind === "normal"
              ? item.kind
              : "normal";
          return {
            kind,
            label: stringValue(item.label) ?? "",
            intent: stringValue(item.intent) ?? "",
          };
        })
        .filter((item) => item.label && item.intent)
    : [];
  return {
    question: stringValue(raw.question) ?? "",
    pills,
    allow_free_input:
      typeof raw.allow_free_input === "boolean" ? raw.allow_free_input : true,
  };
}

function normalizeStats(value: unknown): RunStats {
  const raw = isRecord(value) ? value : {};
  return {
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : 0,
    subagents: typeof raw.subagents === "number" ? raw.subagents : 0,
    tokens: typeof raw.tokens === "number" ? raw.tokens : 0,
  };
}

function normalizeRecommend(value: unknown): Recommend | null {
  if (!isRecord(value)) return null;
  const label = stringValue(value.label);
  const body = stringValue(value.body);
  return label || body
    ? { label: label ?? "", body: body ?? "" }
    : null;
}

function normalizeResultCard(raw: RawRecord): ResultCardBlock | null {
  const runId = stringValue(raw.run_id);
  const title = stringValue(raw.title);
  const tldr = stringValue(raw.tldr);
  if (!runId || !title || !tldr) {
    return null;
  }

  const normalized: ResultCardBlock = {
    kind: "result_card",
    run_id: runId,
    title,
    tldr,
    findings: normalizeFindings(raw.findings),
    links: normalizeLinks(raw.links),
    review_items: Array.isArray(raw.review_items)
      ? raw.review_items as WorkspacePrismReviewItem[]
      : [],
    feedback: normalizeFeedback(raw.feedback),
    stats: normalizeStats(raw.stats),
  };
  const fullSummary = stringValue(raw.full_summary);
  if (fullSummary) normalized.full_summary = fullSummary;
  const recommend = normalizeRecommend(raw.recommend);
  if (recommend) normalized.recommend = recommend;
  return normalized;
}

export function normalizeChatBlock(raw: unknown): AgentBlock {
  if (!isRecord(raw)) {
    return { kind: "text", content: String(raw ?? "") };
  }

  const kind = rawKind(raw);

  if (kind === "text") {
    if (typeof raw.content === "string") {
      return { kind: "text", content: raw.content };
    }
    if (typeof raw.text === "string") {
      return { kind: "text", content: raw.text };
    }
    return fallbackTextBlock(raw);
  }

  if (kind === "reasoning" || kind === "thought" || kind === "thinking") {
    return { kind: "thinking", text: extractThinkingContent(raw) };
  }

  if (kind === "status_line") {
    const tone = raw.tone === "warn" || raw.tone === "error" ? raw.tone : "info";
    return {
      kind: "status_line",
      label: stringValue(raw.label) ?? (titledDetailText(raw) || "Status update"),
      run_id: stringValue(raw.run_id) ?? "legacy-status",
      phase_index: typeof raw.phase_index === "number" ? raw.phase_index : null,
      tone,
    };
  }

  if (kind === "warning") {
    return {
      kind: "status_line",
      label: titledDetailText(raw) || "Warning",
      run_id: stringValue(raw.run_id) ?? "legacy-warning",
      tone: "warn",
    };
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

  if (kind === "question_card") {
    const label = stringValue(raw.label);
    const question = stringValue(raw.question);
    if (label && question) {
      return {
        kind: "question_card",
        label,
        question,
        pills: Array.isArray(raw.pills) ? raw.pills as Pill[] : [],
        context_ref_subagent_task_id:
          stringValue(raw.context_ref_subagent_task_id) ?? null,
        context_ref_phase_index:
          typeof raw.context_ref_phase_index === "number"
            ? raw.context_ref_phase_index
            : null,
      };
    }
    return fallbackTextBlock(raw);
  }

  if (kind === "result_card") {
    return normalizeResultCard(raw) ?? fallbackTextBlock(raw);
  }

  if (!kind) {
    return fallbackTextBlock(raw);
  }

  return fallbackTextBlock(raw);
}
