import type {
  LatexFeedbackAnchor,
  LatexFeedbackItem,
} from "@/lib/api";

export function createFeedbackId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `feedback-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function countLinesUntil(text: string, offset: number): number {
  let line = 1;
  const safeOffset = Math.max(0, Math.min(offset, text.length));
  for (let i = 0; i < safeOffset; i += 1) {
    if (text[i] === "\n") {
      line += 1;
    }
  }
  return line;
}

const SECTION_HEADING_RE =
  /\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}/g;

function stripLatexComment(line: string): string {
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] !== "%") continue;
    let slashCount = 0;
    let cursor = i - 1;
    while (cursor >= 0 && line[cursor] === "\\") {
      slashCount += 1;
      cursor -= 1;
    }
    if (slashCount % 2 === 0) {
      return line.slice(0, i);
    }
  }
  return line;
}

function findNearestHeading(content: string, offset: number): {
  title: string;
  level: string;
} | null {
  let best: { title: string; level: string; start: number } | null = null;
  let cursor = 0;
  for (const line of content.split("\n")) {
    const clean = stripLatexComment(line);
    SECTION_HEADING_RE.lastIndex = 0;
    let match = SECTION_HEADING_RE.exec(clean);
    while (match) {
      const level = String(match[1] || "").trim();
      const title = String(match[2] || "").trim();
      const start = cursor + match.index;
      if (start <= offset) {
        best = { title, level, start };
      }
      match = SECTION_HEADING_RE.exec(clean);
    }
    cursor += line.length + 1;
  }
  if (!best) {
    return null;
  }
  return { title: best.title, level: best.level };
}

function normalizeAnchorSegment(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function scoreContextMatch(expected: string, actual: string): number {
  const left = normalizeAnchorSegment(expected);
  const right = normalizeAnchorSegment(actual);
  if (!left || !right) return 0;
  if (left === right) return Math.min(80, left.length * 2);
  if (right.endsWith(left)) return Math.min(60, left.length * 1.5);
  if (left.endsWith(right)) return Math.min(50, right.length * 1.3);
  let overlap = 0;
  const max = Math.min(left.length, right.length, 60);
  for (let len = max; len >= 8; len -= 1) {
    if (left.slice(-len) === right.slice(-len)) {
      overlap = len;
      break;
    }
  }
  return overlap;
}

export function buildFeedbackAnchor(content: string, start: number, end: number): LatexFeedbackAnchor {
  const safeStart = Math.max(0, Math.min(start, content.length));
  const safeEnd = Math.max(safeStart, Math.min(end, content.length));
  const heading = findNearestHeading(content, safeStart);
  return {
    selected_text: content.slice(safeStart, safeEnd),
    prefix: content.slice(Math.max(0, safeStart - 120), safeStart),
    suffix: content.slice(safeEnd, Math.min(content.length, safeEnd + 120)),
    heading_title: heading?.title || "",
    heading_level: heading?.level || "",
    line_hint: countLinesUntil(content, safeStart),
  };
}

export function resolveFeedbackRange(
  item: Pick<LatexFeedbackItem, "start" | "end" | "selected_text" | "anchor">,
  content: string,
): { start: number; end: number; text: string } | null {
  const anchor = item.anchor;
  const targetText = anchor?.selected_text || item.selected_text;
  if (!targetText) return null;

  const safeStart = Math.max(0, Math.min(item.start, content.length));
  const safeEnd = Math.max(safeStart, Math.min(item.end, content.length));
  const exact = content.slice(safeStart, safeEnd);
  if (exact === targetText) {
    return { start: safeStart, end: safeEnd, text: targetText };
  }

  const nearbyStart = Math.max(0, safeStart - 400);
  const nearbyEnd = Math.min(content.length, safeEnd + 400 + targetText.length);
  const nearby = content.slice(nearbyStart, nearbyEnd);
  const nearbyIndex = nearby.indexOf(targetText);
  if (nearbyIndex >= 0) {
    const start = nearbyStart + nearbyIndex;
    return { start, end: start + targetText.length, text: targetText };
  }

  const candidateStarts: number[] = [];
  let searchIndex = 0;
  while (searchIndex < content.length) {
    const found = content.indexOf(targetText, searchIndex);
    if (found === -1) break;
    candidateStarts.push(found);
    if (candidateStarts.length >= 120) break;
    searchIndex = found + Math.max(1, targetText.length);
  }
  if (!candidateStarts.length) return null;

  let best: { start: number; score: number } | null = null;
  for (const start of candidateStarts) {
    const end = start + targetText.length;
    let score = 0;
    score -= Math.min(Math.abs(start - safeStart), 3000) / 8;
    if (anchor) {
      const actualPrefix = content.slice(Math.max(0, start - 120), start);
      const actualSuffix = content.slice(end, Math.min(content.length, end + 120));
      score += scoreContextMatch(anchor.prefix, actualPrefix);
      score += scoreContextMatch(anchor.suffix, actualSuffix);
      const heading = findNearestHeading(content, start);
      if (heading?.title && anchor.heading_title && heading.title === anchor.heading_title) {
        score += 90;
      }
      if (heading?.level && anchor.heading_level && heading.level === anchor.heading_level) {
        score += 30;
      }
      const lineDistance = Math.abs(countLinesUntil(content, start) - (anchor.line_hint || 1));
      score -= Math.min(lineDistance, 200) / 3;
    }
    if (!best || score > best.score) {
      best = { start, score };
    }
  }
  if (!best) return null;
  return { start: best.start, end: best.start + targetText.length, text: targetText };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function resolveSnippetRange(
  content: string,
  snippet: string,
  preferredOffset = 0,
): { start: number; end: number } | null {
  const raw = snippet.trim();
  if (!raw) return null;

  const candidates: Array<{ start: number; end: number }> = [];
  let cursor = 0;
  while (cursor < content.length) {
    const found = content.indexOf(raw, cursor);
    if (found < 0) break;
    candidates.push({ start: found, end: found + raw.length });
    cursor = found + Math.max(1, raw.length);
    if (candidates.length >= 120) break;
  }

  if (!candidates.length) {
    const tokens = raw.split(/\s+/).filter(Boolean).slice(0, 40);
    if (!tokens.length) return null;
    const pattern = new RegExp(tokens.map((token) => escapeRegExp(token)).join("\\s+"), "ig");
    let match = pattern.exec(content);
    while (match) {
      candidates.push({
        start: match.index,
        end: match.index + match[0].length,
      });
      if (candidates.length >= 120) break;
      match = pattern.exec(content);
    }
  }

  if (!candidates.length) return null;
  let best = candidates[0];
  let bestScore = Math.abs(best.start - preferredOffset);
  for (const candidate of candidates.slice(1)) {
    const score = Math.abs(candidate.start - preferredOffset);
    if (score < bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best;
}

export function parsePdfAnchor(
  value: unknown,
): {
  page: number;
  text: string;
  rects: Array<{ x: number; y: number; width: number; height: number }>;
} | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as {
    page?: unknown;
    text?: unknown;
    rects?: unknown;
  };
  const page = Number(raw.page);
  const text = typeof raw.text === "string" ? raw.text : "";
  const rectsRaw = Array.isArray(raw.rects) ? raw.rects : [];
  const rects = rectsRaw
    .map((rect) => {
      if (!rect || typeof rect !== "object") return null;
      const next = rect as {
        x?: unknown;
        y?: unknown;
        width?: unknown;
        height?: unknown;
      };
      const x = Number(next.x);
      const y = Number(next.y);
      const width = Number(next.width);
      const height = Number(next.height);
      if (![x, y, width, height].every((item) => Number.isFinite(item))) {
        return null;
      }
      return { x, y, width, height };
    })
    .filter((item): item is { x: number; y: number; width: number; height: number } => Boolean(item));
  if (!Number.isFinite(page) || page <= 0 || rects.length === 0) {
    return null;
  }
  return { page, text, rects };
}

export function shiftFeedbacksAfterRewrite(
  items: LatexFeedbackItem[],
  filePath: string,
  feedbackId: string,
  start: number,
  end: number,
  nextText: string,
  nextContent: string,
): LatexFeedbackItem[] {
  const delta = nextText.length - (end - start);
  return items.map((item) => {
    if (item.file_path !== filePath) return item;
    if (item.id === feedbackId) {
      return {
        ...item,
        start,
        end: start + nextText.length,
        selected_text: nextText,
        anchor: buildFeedbackAnchor(nextContent, start, start + nextText.length),
        last_status: "done",
        last_error: "",
      };
    }
    let nextStart = item.start;
    let nextEnd = item.end;
    if (item.start >= end) {
      nextStart = item.start + delta;
      nextEnd = item.end + delta;
    }
    const nextExact = nextContent.slice(nextStart, nextEnd);
    if (nextExact === item.selected_text) {
      return {
        ...item,
        start: nextStart,
        end: nextEnd,
        anchor: buildFeedbackAnchor(nextContent, nextStart, nextEnd),
      };
    }
    const resolved = resolveFeedbackRange(item, nextContent);
    if (!resolved) {
      return { ...item, start: nextStart, end: nextEnd };
    }
    return {
      ...item,
      start: resolved.start,
      end: resolved.end,
      anchor: buildFeedbackAnchor(nextContent, resolved.start, resolved.end),
    };
  });
}
