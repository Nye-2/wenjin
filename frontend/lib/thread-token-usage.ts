export interface ThreadTokenUsageSummary {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  model_name: string | null;
  source: string | null;
  credits_charged: number | null;
  free_tokens_applied: number | null;
  billable_tokens: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readInt(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.trunc(value));
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return 0;
}

function readOptionalInt(value: unknown): number | null {
  const parsed = readInt(value);
  return parsed > 0 ? parsed : null;
}

function readOptionalString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

function readTokenUsageCandidate(
  candidate: unknown
): { input_tokens: number; output_tokens: number; total_tokens: number } | null {
  if (!isRecord(candidate)) {
    return null;
  }

  const input = readInt(
    candidate.input_tokens ?? candidate.prompt_tokens ?? candidate.input
  );
  const output = readInt(
    candidate.output_tokens ?? candidate.completion_tokens ?? candidate.output
  );
  const explicitTotal = readInt(candidate.total_tokens ?? candidate.total);
  const total = explicitTotal > 0 ? explicitTotal : input + output;
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: total,
  };
}

export function parseThreadTokenUsage(
  metadata: Record<string, unknown> | null | undefined
): ThreadTokenUsageSummary | null {
  if (!metadata) {
    return null;
  }

  const usagePayload = isRecord(metadata.usage) ? metadata.usage : null;
  const billingPayload = isRecord(metadata.billing) ? metadata.billing : null;

  const usage =
    readTokenUsageCandidate(usagePayload) ??
    readTokenUsageCandidate(billingPayload?.token_usage) ??
    null;

  const creditsCharged = readOptionalInt(billingPayload?.credits_charged);
  const freeTokensApplied = readOptionalInt(billingPayload?.free_tokens_applied);
  const billableTokens = readOptionalInt(billingPayload?.billable_tokens);

  if (!usage && !creditsCharged && !freeTokensApplied && !billableTokens) {
    return null;
  }

  return {
    input_tokens: usage?.input_tokens ?? 0,
    output_tokens: usage?.output_tokens ?? 0,
    total_tokens: usage?.total_tokens ?? 0,
    model_name:
      readOptionalString(usagePayload?.model_name) ??
      readOptionalString(billingPayload?.model_name),
    source: readOptionalString(usagePayload?.source),
    credits_charged: creditsCharged,
    free_tokens_applied: freeTokensApplied,
    billable_tokens: billableTokens,
  };
}
