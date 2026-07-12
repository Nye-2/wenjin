import type {
  ThreadCreditStatus,
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
    case "thread":
    case "thread_token_billing":
      return "主线对话";
    case "mission":
    case "mission_token_billing":
      return "研究任务";
    case "sandbox_run_python":
      return "实验环境 Python";
    case "sandbox_operation_billing":
      return "实验环境";
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
    case "thread_token_consume":
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
  if (value.enabled === false) return "未启用";
  if (value.unit === "credits" && typeof value.credits === "number") {
    return `${value.credits} 积分/次`;
  }
  if (value.unit === "credits" && value.pricing === "usage_based") {
    return "按实际使用折算积分";
  }
  return "按积分结算";
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
    (item.type === "workflow_consume" &&
      isRecord(item.metadata) &&
      (item.metadata.type === "mission_token_billing" ||
        item.metadata.type === "sandbox_operation_billing"));
  if (!isSettledBilling || !isRecord(item.metadata)) {
    return base || "-";
  }

  const parts: string[] = [];
  const creditsCharged =
    getNumericValue(item.metadata.credits_charged) ?? Math.abs(item.amount);
  const overdraftCredits = getNumericValue(item.metadata.overdraft_credits);
  const modelName = typeof item.metadata.model_name === "string" ? item.metadata.model_name : null;
  const operation = typeof item.metadata.operation === "string" ? item.metadata.operation : null;

  if (creditsCharged > 0) {
    parts.push(`扣费 ${creditsCharged} 积分`);
  } else {
    parts.push("未扣积分");
  }
  if (overdraftCredits && overdraftCredits > 0) {
    parts.push(`透支 ${overdraftCredits} 积分`);
  }
  if (operation) {
    parts.push(formatCreditCostLabel(`sandbox_${operation}`));
  }
  if (modelName) {
    parts.push(modelName);
  }

  const details = parts.join(" | ");
  return details || base || "-";
}
