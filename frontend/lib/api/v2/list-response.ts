function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readItemsArray<T>(
  payload: unknown,
  resourceName: string,
): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }

  if (isRecord(payload) && Array.isArray(payload.items)) {
    return payload.items as T[];
  }

  throw new Error(`Invalid ${resourceName} response`);
}

export function readOptionalActiveItem<T>(payload: unknown): T[] | null {
  if (!isRecord(payload) || !("active" in payload)) {
    return null;
  }

  const active = payload.active;
  return active ? [active as T] : [];
}
