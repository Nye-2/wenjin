import type {
  ThreadCreditStatus,
  CreditTransactionItem,
  UserDashboardData,
} from "@/lib/api/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getNumericValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function formatCreditTransactionType(type: string): string {
  switch (type) {
    case "admin_grant":
      return "管理员发放";
    case "admin_deduct":
      return "管理员扣减";
    case "workflow_consume":
      return "功能扣费";
    case "thread_token_consume":
      return "主线对话扣费";
    case "registration_bonus":
      return "注册奖励";
    default:
      return type;
  }
}

export function getThreadCreditStatus(
  credits: UserDashboardData["credits"] | null | undefined
): ThreadCreditStatus | null {
  const candidate = credits?.thread;
  if (!isRecord(candidate)) return null;

  const enabled = candidate.enabled;
  const canStartThread = candidate.can_start_thread;
  const overdraftCredits = getNumericValue(candidate.overdraft_credits);
  const billingUnit = candidate.billing_unit;
  const pricing = candidate.pricing;

  if (
    typeof enabled !== "boolean" ||
    typeof canStartThread !== "boolean" ||
    overdraftCredits === null ||
    billingUnit !== "credits" ||
    pricing !== "usage_based"
  ) {
    return null;
  }

  return {
    enabled,
    can_start_thread: canStartThread,
    overdraft_credits: overdraftCredits,
    billing_unit: billingUnit,
    pricing,
  };
}

export function summarizeCreditTransaction(item: CreditTransactionItem): string {
  const base = item.description?.trim() || "";
  const isSettledBilling =
    item.type === "thread_token_consume" ||
    (item.type === "workflow_consume" && isRecord(item.metadata));
  if (!isSettledBilling || !isRecord(item.metadata)) {
    return base || "-";
  }

  const parts: string[] = [];
  const creditsCharged =
    getNumericValue(item.metadata.credits_charged) ?? Math.abs(item.amount);
  const overdraftCredits = getNumericValue(item.metadata.overdraft_credits);
  const modelName = typeof item.metadata.model_name === "string" ? item.metadata.model_name : null;

  if (creditsCharged > 0) {
    parts.push(`扣费 ${creditsCharged} 积分`);
  } else {
    parts.push("未扣积分");
  }
  if (overdraftCredits && overdraftCredits > 0) {
    parts.push(`透支 ${overdraftCredits} 积分`);
  }
  if (modelName) {
    parts.push(modelName);
  }

  const details = parts.join(" | ");
  return details || base || "-";
}
