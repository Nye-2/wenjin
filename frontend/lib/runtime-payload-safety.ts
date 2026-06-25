export function readRuntimeString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function safeRuntimeText(value: unknown, max = 180): string | null {
  const text = readRuntimeString(value);
  if (!text || isRawRuntimePayloadText(text)) {
    return null;
  }
  return truncateRuntimeText(text, max);
}

export function isRawRuntimePayloadText(value: string): boolean {
  const normalized = value.trim();
  if (!normalized) {
    return false;
  }
  if (/(^|[^a-z])std(?:out|err)([^a-z]|$)/i.test(normalized)) {
    return true;
  }
  if (
    normalized.includes("/workspace/outputs/harness/") ||
    normalized.includes("/workspace/tmp/tasks/.harness/")
  ) {
    return true;
  }
  return (
    normalized.startsWith("{") ||
    (normalized.startsWith("[") && normalized.endsWith("]")) ||
    /["']std(?:out|err)["']\s*:/i.test(normalized)
  );
}

export function truncateRuntimeText(value: string, max: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, max - 3))}...`;
}

export function runtimeStatusLabel(status: string | null | undefined): string {
  if (status === "launching") return "启动中";
  if (status === "queued" || status === "pending") return "排队中";
  if (status === "running" || status === "cancelling") return "运行中";
  if (status === "completed") return "已完成";
  if (status === "failed_partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return status || "未知";
}

export function recoverableOutputRefCount(...values: unknown[]): number {
  let count = 0;
  for (const value of values) {
    if (Array.isArray(value)) {
      count += recoverableOutputRefCount(...value);
      continue;
    }
    if (readRuntimeString(value)) {
      count += 1;
      continue;
    }
    const object = readRuntimeObject(value);
    if (
      object &&
      (readRuntimeString(object.output_ref) ||
        readRuntimeString(object.ref) ||
        readRuntimeString(object.path))
    ) {
      count += 1;
    }
  }
  return count;
}

export function safeStructuredFallback(value: unknown, fallback: string): string {
  const object = readRuntimeObject(value);
  if (!object) {
    return fallback;
  }
  const refCount = recoverableOutputRefCount(object.output_refs, object.output_ref);
  const fieldCount = Object.keys(object).length;
  return [
    fallback,
    refCount > 0 ? `可恢复引用：${refCount} 个` : null,
    fieldCount > 0 ? `字段：${fieldCount} 项` : null,
  ].filter((line): line is string => Boolean(line)).join(" · ");
}

export function readRuntimeObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}
