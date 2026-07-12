/**
 * Public API surface for Wenjin (问津) frontend.
 *
 * Keep this file as a stable aggregation layer so callers can continue to
 * import from `@/lib/api` while the implementation is split by domain.
 */

export { authorizedFetch } from "@/lib/api/client";
export { default } from "@/lib/api/client";
export * from "@/lib/api/types";
export * from "@/lib/api/health";
export * from "@/lib/api/workspace";
export * from "@/lib/api/threads";
export * from "@/lib/api/runs";
export * from "@/lib/api/streams";
export * from "@/lib/api/models";
export * from "@/lib/api/admin";
export * from "@/lib/api/credits";
export * from "@/lib/api/latex";
