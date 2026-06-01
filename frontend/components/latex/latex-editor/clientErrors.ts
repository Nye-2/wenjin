export function readClientErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: unknown } }).response;
    const data = response?.data;
    if (typeof data === "string" && data.trim()) {
      return data;
    }
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
      if (detail && typeof detail === "object" && "message" in detail) {
        const message = (detail as { message?: unknown }).message;
        if (typeof message === "string" && message.trim()) {
          return message;
        }
      }
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return String(error);
}

export function readClientErrorCode(error: unknown): string | null {
  if (!(error && typeof error === "object" && "response" in error)) {
    return null;
  }
  const response = (error as { response?: { data?: unknown } }).response;
  const data = response?.data;
  if (!(data && typeof data === "object" && "detail" in data)) {
    return null;
  }
  const detail = (data as { detail?: unknown }).detail;
  if (!(detail && typeof detail === "object" && "code" in detail)) {
    return null;
  }
  const code = (detail as { code?: unknown }).code;
  if (typeof code !== "string" || !code.trim()) {
    return null;
  }
  return code;
}

export function readClientErrorDetailField(error: unknown, field: string): string | null {
  if (!(error && typeof error === "object" && "response" in error)) {
    return null;
  }
  const response = (error as { response?: { data?: unknown } }).response;
  const data = response?.data;
  if (!(data && typeof data === "object" && "detail" in data)) {
    return null;
  }
  const detail = (data as { detail?: unknown }).detail;
  if (!(detail && typeof detail === "object")) {
    return null;
  }
  const value = (detail as Record<string, unknown>)[field];
  return typeof value === "string" && value.trim() ? value : null;
}
