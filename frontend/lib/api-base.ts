/**
 * Shared API base URL resolution for frontend HTTP calls.
 *
 * Resolution order:
 * 1) NEXT_PUBLIC_API_URL
 * 2) NEXT_PUBLIC_BACKEND_BASE_URL (legacy alias)
 * 3) /api (same-origin proxy default)
 */

const DEFAULT_DEV_API_BASE = "http://localhost:8001/api";

const RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL ??
  (process.env.NODE_ENV === "development" ? DEFAULT_DEV_API_BASE : "/api");

const ABSOLUTE_URL_PATTERN = /^https?:\/\//i;

function trimTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

function normalizeBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "/api";
  }

  if (ABSOLUTE_URL_PATTERN.test(trimmed)) {
    return trimTrailingSlashes(trimmed);
  }

  if (trimmed.startsWith("/")) {
    const normalized = trimTrailingSlashes(trimmed);
    return normalized.length > 0 ? normalized : "/";
  }

  return `/${trimTrailingSlashes(trimmed)}`;
}

function ensureApiSuffix(base: string): string {
  return base.endsWith("/api") ? base : `${base}/api`;
}

const NORMALIZED_BASE = normalizeBase(RAW_API_BASE);

/**
 * Full API base including `/api` suffix.
 * Examples:
 * - "http://localhost:8001" -> "http://localhost:8001/api"
 * - "/api" -> "/api"
 */
export const API_BASE_URL = ensureApiSuffix(NORMALIZED_BASE);

/**
 * Gateway/server base without `/api` suffix.
 * Examples:
 * - "http://localhost:8001/api" -> "http://localhost:8001"
 * - "/api" -> ""
 */
export const API_SERVER_BASE_URL =
  API_BASE_URL === "/api"
    ? ""
    : API_BASE_URL.endsWith("/api")
      ? API_BASE_URL.slice(0, -4)
      : API_BASE_URL;
