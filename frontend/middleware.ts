import { NextRequest, NextResponse } from "next/server";

/**
 * Mapping from old feature route slugs to skill IDs.
 *
 * Inlined here rather than imported from lib/ because Next.js middleware runs
 * in the Edge runtime, which may have import restrictions. Keeping the
 * middleware self-contained avoids potential bundling issues.
 */
const FEATURE_SLUG_TO_SKILL: Record<string, string> = {
  "deep-research": "deep-research",
  "literature": "literature-management",
  "opening-research": "opening-research",
  "thesis-writing": "fullpaper-writer",
  "figure-generation": "figure-generation",
  "compile-export": "compile-export",
  "literature-search": "deep-research",
  "paper-analysis": "paper-analysis",
  "writing": "writing",
  "literature-review": "literature-review",
  "framework-outline": "framework-designer",
  "peer-review": "peer-reviewer",
  "journal-recommend": "journal-recommender",
  "proposal-outline": "proposal-writer",
  "background-research": "background-research",
  "experiment-design": "experiment-designer",
  "copyright-materials": "copyright-materials",
  "technical-description": "technical-description",
  "patent-outline": "patent-outline",
  "prior-art-search": "prior-art-search",
};

// Match: /workspaces/{id}/{slug} where slug is a known feature
const FEATURE_ROUTE_RE = /^\/workspaces\/([^/]+)\/([^/]+)$/;

export function middleware(request: NextRequest) {
  const match = request.nextUrl.pathname.match(FEATURE_ROUTE_RE);
  if (!match) return NextResponse.next();

  const [, workspaceId, slug] = match;
  // Only redirect known feature slugs — NOT "chat" or other valid paths
  const skillId = FEATURE_SLUG_TO_SKILL[slug];
  if (!skillId) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = `/workspaces/${workspaceId}/chat/new`;
  url.searchParams.set("skill", skillId);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: "/workspaces/:id/:slug",
};
