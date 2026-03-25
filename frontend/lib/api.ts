/**
 * Public API surface for AcademiaGPT frontend.
 *
 * Keep this file as a stable aggregation layer so callers can continue to
 * import from `@/lib/api` while the implementation is split by domain.
 */

export { authorizedFetch } from "@/lib/api/client";
export { default } from "@/lib/api/client";
export * from "@/lib/api/types";
export * from "@/lib/api/health";
export * from "@/lib/api/workspace";
export * from "@/lib/api/chat";
export * from "@/lib/api/streams";
export * from "@/lib/api/models";
export * from "@/lib/api/admin";
