import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from "axios";

import { API_BASE_URL, API_SERVER_BASE_URL } from "@/lib/api-base";
import { useAuthStore } from "@/stores/auth";

const AUTH_STORAGE_KEY = "auth-storage";
const AUTH_ENDPOINT_MARKERS = [
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
];

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

function extractApiErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string" && record.detail.trim()) {
    return record.detail.trim();
  }
  if (typeof record.message === "string" && record.message.trim()) {
    return record.message.trim();
  }
  const nestedError = record.error;
  if (nestedError && typeof nestedError === "object") {
    const nestedRecord = nestedError as Record<string, unknown>;
    if (
      typeof nestedRecord.message === "string" &&
      nestedRecord.message.trim()
    ) {
      return nestedRecord.message.trim();
    }
  }
  return null;
}

function readPersistedAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const authStorage = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!authStorage) {
      return null;
    }
    const parsed = JSON.parse(authStorage);
    return parsed?.state?.accessToken ?? null;
  } catch (error) {
    console.error("Failed to parse auth token:", error);
    return null;
  }
}

function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken ?? readPersistedAccessToken();
}

function isAuthRequest(url?: string): boolean {
  if (!url) {
    return false;
  }
  return AUTH_ENDPOINT_MARKERS.some((marker) => url.includes(marker));
}

function withAuthorizationHeader(
  headers: HeadersInit | undefined,
  token: string | null
): Headers {
  const resolved = new Headers(headers);
  if (token) {
    resolved.set("Authorization", `Bearer ${token}`);
  } else {
    resolved.delete("Authorization");
  }
  return resolved;
}

let refreshPromise: Promise<boolean> | null = null;

export function normalizeAuthorizedFetchInput(
  input: RequestInfo | URL
): RequestInfo | URL {
  if (typeof input !== "string") {
    return input;
  }

  if (input === "/api") {
    return API_BASE_URL;
  }

  if (input.startsWith("/api/") || input.startsWith("/api?")) {
    return `${API_BASE_URL}${input.slice(4)}`;
  }

  return input;
}

async function refreshSession(): Promise<boolean> {
  if (typeof window === "undefined") {
    return false;
  }

  if (!refreshPromise) {
    const { refreshToken, refreshTokens, logout } = useAuthStore.getState();
    if (!refreshToken) {
      return false;
    }

    refreshPromise = refreshTokens()
      .then((refreshed) => {
        if (!refreshed) {
          logout();
        }
        return refreshed;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  options: { retryOn401?: boolean } = {}
): Promise<Response> {
  const { retryOn401 = true } = options;
  const requestInput = normalizeAuthorizedFetchInput(input);
  const requestInit: RequestInit = {
    ...init,
    headers: withAuthorizationHeader(init.headers, getAccessToken()),
  };

  let response = await fetch(requestInput, requestInit);
  if (!retryOn401 || response.status !== 401 || typeof window === "undefined") {
    return response;
  }

  const refreshed = await refreshSession();
  if (!refreshed) {
    return response;
  }

  response = await fetch(requestInput, {
    ...init,
    headers: withAuthorizationHeader(init.headers, getAccessToken()),
  });
  return response;
}

export async function readErrorMessage(
  response: Response,
  fallback?: string
): Promise<string> {
  let message = fallback ?? `Request failed (${response.status})`;
  try {
    const payload = await response.json();
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : typeof payload?.error === "string"
          ? payload.error
          : null;
    if (detail) {
      message = detail;
    }
  } catch {
    // Ignore parsing errors and keep fallback message.
  }
  return message;
}

type JsonEventStreamOptions<T> = {
  url: string;
  init?: RequestInit;
  onPayload: (payload: T) => void;
  onOpen?: () => void;
  onError?: (error: string, status?: number) => void;
  onClosedMessage?: string;
};

class HttpStreamError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "HttpStreamError";
  }
}

export function subscribeJsonEventStream<T>({
  url,
  init,
  onPayload,
  onOpen,
  onError,
  onClosedMessage,
}: JsonEventStreamOptions<T>): () => void {
  const controller = new AbortController();

  authorizedFetch(url, {
    ...init,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new HttpStreamError(
          await readErrorMessage(response),
          response.status,
        );
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No reader available");
      }
      onOpen?.();

      const decoder = new TextDecoder();
      let buffer = "";

      const processLine = (line: string) => {
        if (!line.startsWith("data: ")) {
          return;
        }

        const payload = line.slice(6).trim();
        if (!payload) {
          return;
        }

        try {
          onPayload(JSON.parse(payload) as T);
        } catch {
          // Ignore malformed SSE payloads.
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const rawLine of lines) {
          processLine(rawLine.trim());
        }
      }

      buffer += decoder.decode();
      const remaining = buffer.trim();
      if (remaining) {
        for (const rawLine of remaining.split("\n")) {
          processLine(rawLine.trim());
        }
      }

      // Stream ended gracefully (server timeout or completion) — not an error.
      // Only call onError if the stream was NOT aborted (user navigated away)
      // and the caller explicitly wants to know about normal closures.
      // For workspace events, the server closes after 3600s timeout which is
      // a normal lifecycle event, not an error warranting reconnect.
      if (!controller.signal.aborted) {
        onError?.(onClosedMessage || "Stream ended");
      }
    })
    .catch((error: unknown) => {
      const errorName =
        error instanceof DOMException
          ? error.name
          : typeof error === "object" && error && "name" in error
            ? String(error.name)
            : "";
      if (errorName === "AbortError") {
        return;
      }
      const message =
        error instanceof Error ? error.message : "Unknown stream error";
      const status = error instanceof HttpStreamError ? error.status : undefined;
      onError?.(message, status);
    });

  return () => controller.abort();
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetriableRequestConfig | undefined;

    if (
      typeof window !== "undefined" &&
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthRequest(originalRequest.url)
    ) {
      originalRequest._retry = true;
      const refreshed = await refreshSession();
      if (refreshed) {
        const token = getAccessToken();
        if (token) {
          originalRequest.headers = originalRequest.headers ?? {};
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
        return apiClient(originalRequest);
      }
    }

    const normalizedMessage =
      extractApiErrorMessage(error.response?.data) || error.message;
    error.message = normalizedMessage;
    console.error("API Error:", normalizedMessage);
    return Promise.reject(error);
  }
);

export { API_BASE_URL, API_SERVER_BASE_URL };

export default apiClient;
