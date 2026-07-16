export const REASONING_EFFORT_VALUES = [
  "low",
  "medium",
  "high",
  "xhigh",
] as const;

export type ReasoningEffort = (typeof REASONING_EFFORT_VALUES)[number];

export const REASONING_EFFORT_OPTIONS: ReadonlyArray<{
  value: ReasoningEffort;
  label: string;
}> = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
  { value: "xhigh", label: "超高" },
];

export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return (
    typeof value === "string" &&
    REASONING_EFFORT_VALUES.includes(value as ReasoningEffort)
  );
}

export function chooseReasoningEffort(
  available: readonly ReasoningEffort[],
  preferred: unknown,
): ReasoningEffort {
  if (isReasoningEffort(preferred) && available.includes(preferred)) {
    return preferred;
  }
  if (available.includes("xhigh")) {
    return "xhigh";
  }
  return available[0] ?? "xhigh";
}
