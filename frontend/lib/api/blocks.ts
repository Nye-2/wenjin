// Mirror of backend/src/agents/lead_agent/blocks.py — keep field names in sync.

export interface TextBlock {
  kind: "text";
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
  findings: Finding[];
  recommend?: Recommend | null;
  links: Link[];
  feedback: FeedbackBlock;
  stats: RunStats;
}

export type AgentBlock =
  | TextBlock
  | StatusLineBlock
  | QuestionCardBlock
  | ResultCardBlock;

export interface AgentMessage { blocks: AgentBlock[]; }

export const isText = (b: AgentBlock): b is TextBlock => b.kind === "text";
export const isStatusLine = (b: AgentBlock): b is StatusLineBlock => b.kind === "status_line";
export const isQuestionCard = (b: AgentBlock): b is QuestionCardBlock => b.kind === "question_card";
export const isResultCard = (b: AgentBlock): b is ResultCardBlock => b.kind === "result_card";
