import type {
  ChatCreditStatus,
  CreditCostValue,
  CreditTransactionItem,
  UserDashboardData,
} from "@/lib/api/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getNumericValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function formatCreditCostLabel(key: string): string {
  switch (key) {
    case "chat_token_billing":
      return "主线对话";
    case "deep_research":
      return "深度研究";
    case "literature_search":
      return "文献检索";
    case "paper_analysis":
      return "论文解析";
    case "writing":
      return "论文写作";
    case "thesis_writing":
      return "毕业论文";
    default:
      return key;
  }
}

export function formatCreditTransactionType(type: string): string {
  switch (type) {
    case "admin_grant":
      return "管理员发放";
    case "admin_deduct":
      return "管理员扣减";
    case "workflow_consume":
      return "功能扣费";
    case "chat_token_consume":
      return "主线对话扣费";
    case "registration_bonus":
      return "注册奖励";
    case "refund":
      return "退款";
    default:
      return type;
  }
}

export function renderCostValue(value: CreditCostValue): string {
  if (typeof value === "number") return `${value}`;
  const parts = Object.entries(value).map(([k, v]) =>
    `${k}: ${typeof v === "boolean" ? (v ? "on" : "off") : v}`
  );
  return parts.join(" | ");
}

export function getChatCreditStatus(
  credits: UserDashboardData["credits"] | null | undefined
): ChatCreditStatus | null {
  const candidate = credits?.chat;
  if (!isRecord(candidate)) return null;

  const enabled = candidate.enabled;
  const freeTokens = getNumericValue(candidate.free_tokens);
  const tokensPerCredit = getNumericValue(candidate.tokens_per_credit);
  const consumedTokens = getNumericValue(candidate.consumed_tokens);
  const remainingFreeTokens = getNumericValue(candidate.remaining_free_tokens);
  const canStartChat = candidate.can_start_chat;
  const overdraftCredits = getNumericValue(candidate.overdraft_credits);

  if (
    typeof enabled !== "boolean" ||
    freeTokens === null ||
    tokensPerCredit === null ||
    consumedTokens === null ||
    remainingFreeTokens === null ||
    typeof canStartChat !== "boolean" ||
    overdraftCredits === null
  ) {
    return null;
  }

  return {
    enabled,
    free_tokens: freeTokens,
    tokens_per_credit: tokensPerCredit,
    consumed_tokens: consumedTokens,
    remaining_free_tokens: remainingFreeTokens,
    can_start_chat: canStartChat,
    overdraft_credits: overdraftCredits,
  };
}

export function summarizeCreditTransaction(item: CreditTransactionItem): string {
  const base = item.description?.trim() || "";
  if (item.type !== "chat_token_consume" || !isRecord(item.metadata)) {
    return base || "-";
  }

  const parts: string[] = [];
  const tokenUsage = isRecord(item.metadata.token_usage) ? item.metadata.token_usage : null;
  const totalTokens = tokenUsage ? getNumericValue(tokenUsage.total_tokens) : null;
  const freeTokensApplied = getNumericValue(item.metadata.free_tokens_applied);
  const billableTokens = getNumericValue(item.metadata.billable_tokens);
  const overdraftCredits = getNumericValue(item.metadata.overdraft_credits);
  const modelName = typeof item.metadata.model_name === "string" ? item.metadata.model_name : null;

  if (totalTokens && totalTokens > 0) {
    parts.push(`${totalTokens.toLocaleString()} tokens`);
  }
  if (freeTokensApplied && freeTokensApplied > 0) {
    parts.push(`免费抵扣 ${freeTokensApplied.toLocaleString()}`);
  }
  if (billableTokens && billableTokens > 0) {
    parts.push(`计费 ${billableTokens.toLocaleString()} tokens`);
  }
  if (overdraftCredits && overdraftCredits > 0) {
    parts.push(`透支 ${overdraftCredits} 积分`);
  }
  if (modelName) {
    parts.push(modelName);
  }

  const details = parts.join(" | ");
  if (!base) return details || "-";
  if (!details) return base;
  return `${base} | ${details}`;
}
