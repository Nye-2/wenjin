"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Eye,
  FileImage,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { LatexFileTree } from "@/components/latex/LatexFileTree";
import { LatexPdfPreview } from "@/components/latex/LatexPdfPreview";
import { LatexToolbar } from "@/components/latex/LatexToolbar";
import { Header } from "@/components/layout/header";
import {
  fileChangeToPrismReviewItem,
  PrismReviewList,
} from "@/components/prism/PrismReviewList";
import { Button } from "@/components/ui/button";
import type {
  LatexCompileEngine,
  LatexAppliedFileChange,
  LatexFeedbackAnchor,
  LatexFeedbackItem,
  LatexPdfAnchor,
  LatexFeedbackRewriteCandidate,
  LatexFeedbackRewriteUndoPayload,
  LatexFileChange,
  LatexFileChangePreviewResponse,
} from "@/lib/api";
import {
  applyLatexFeedbackRewrite,
  getLatexProjectFeedback,
  mapLatexFeedbackSelection,
  previewLatexFileChange,
  previewLatexFeedbackRewrite,
  protectLatexSection,
  revertLatexFeedbackRewrite,
  saveLatexProjectFeedback,
} from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuthStore } from "@/stores/auth";
import { useLatexStore } from "@/stores/latex";

interface LatexEditorShellProps {
  projectId: string;
  workspaceId?: string;
  initialFileChanges?: LatexFileChange[];
  initialAppliedFileChanges?: LatexAppliedFileChange[];
  onReviewStateChanged?: () => void;
}

interface PdfDraftSelection {
  text: string;
  page: number;
  rects: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
}

interface LastRewriteUndoState extends LatexFeedbackRewriteUndoPayload {
  file_path: string;
  feedback_id: string;
}

function isTextFile(path: string): boolean {
  const lower = path.toLowerCase();
  return [
    ".tex",
    ".bib",
    ".cls",
    ".sty",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
  ].some((suffix) => lower.endsWith(suffix));
}

function isImageFile(path: string): boolean {
  return [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"].some((suffix) =>
    path.toLowerCase().endsWith(suffix),
  );
}

function createFeedbackId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `feedback-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function countLinesUntil(text: string, offset: number): number {
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

function buildFeedbackAnchor(content: string, start: number, end: number): LatexFeedbackAnchor {
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

function resolveFeedbackRange(
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

function resolveSnippetRange(
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

function readClientErrorMessage(error: unknown): string {
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

function readClientErrorCode(error: unknown): string | null {
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

function readClientErrorDetailField(error: unknown, field: string): string | null {
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

function rewriteProfileLabel(profile: "balanced" | "conservative" | "aggressive"): string {
  if (profile === "conservative") return "保守";
  if (profile === "aggressive") return "激进";
  return "平衡";
}

function riskLevelLabel(level: "low" | "medium" | "high"): string {
  if (level === "high") return "高风险";
  if (level === "medium") return "中风险";
  return "低风险";
}

function riskLevelClass(level: "low" | "medium" | "high"): string {
  if (level === "high") return "border-red-500/25 bg-red-500/10 text-red-700";
  if (level === "medium") return "border-amber-500/25 bg-amber-500/10 text-amber-800";
  return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700";
}

function riskFlagClass(flag: string): string {
  if (["boundary_leak", "citation_drop", "label_drop", "brace_unbalanced"].includes(flag)) {
    return "border-red-500/25 bg-red-500/10 text-red-700";
  }
  if (["math_structure_change", "math_change", "large_change"].includes(flag)) {
    return "border-amber-500/25 bg-amber-500/10 text-amber-800";
  }
  return "border-[var(--border-default)] bg-white/80 text-[var(--text-muted)]";
}

function riskFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    boundary_leak: "越界改写",
    citation_drop: "引用被删",
    label_drop: "标签被删",
    brace_unbalanced: "花括号不平衡",
    math_structure_change: "数学结构变化",
    math_change: "数学相关改动",
    large_change: "改动较大",
    citation_change: "引用改动",
    label_change: "标签改动",
  };
  return labels[flag] || flag;
}

function tokenKindLabel(kind: string): string {
  if (kind === "citation") return "引用";
  if (kind === "label") return "标签";
  if (kind === "math") return "数学";
  if (kind === "env") return "环境";
  if (kind === "latex_cmd") return "命令";
  return "文本";
}

function diffOpLabel(op: "equal" | "insert" | "delete" | "replace"): string {
  if (op === "replace") return "替换";
  if (op === "insert") return "新增";
  if (op === "delete") return "删除";
  return "保持";
}

function isWhitespaceOnlyDiffOp(op: { old_text: string; new_text: string }): boolean {
  const oldCompact = op.old_text.replace(/\s+/g, "");
  const newCompact = op.new_text.replace(/\s+/g, "");
  return oldCompact === newCompact && op.old_text !== op.new_text;
}

const STALE_REWRITE_ERROR_CODES = new Set([
  "invalid_candidate_signature",
  "base_file_hash_mismatch",
  "base_range_hash_mismatch",
  "target_range_out_of_bounds",
]);

const STRUCTURE_REWRITE_ERROR_CODES = new Set([
  "boundary_leak",
  "citation_drop",
  "label_drop",
  "ref_drop",
  "brace_unbalanced",
  "environment_unbalanced",
  "math_delimiter_unbalanced",
]);

function parsePdfAnchor(
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

function shiftFeedbacksAfterRewrite(
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

export function LatexEditorShell({
  projectId,
  workspaceId,
  initialFileChanges,
  initialAppliedFileChanges,
  onReviewStateChanged,
}: LatexEditorShellProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileChangesRef = useRef<HTMLDivElement | null>(null);
  const lastFileChangeFocusKey = useRef("");
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const {
    project,
    tree,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    activeFileSavedContent,
    activeBlobUrl,
    fileChanges,
    appliedFileChanges,
    compileResult,
    compileLog,
    compiledPdfUrl,
    isProjectLoading,
    isFileLoading,
    isSaving,
    isCompiling,
    error,
    loadProject,
    setReviewState,
    openFile,
    setActiveFileContent,
    saveActiveFile,
    createFile,
    createFolder,
    renamePath,
    deletePath,
    saveOrder,
    uploadFiles,
    uploadDirectory,
    uploadArchive,
    applyFileChange,
    deferFileChange,
    discardFileChange,
    revertFileChange,
    deleteProject,
    compileProject,
  } = useLatexStore();
  const [engine, setEngine] = useState<LatexCompileEngine>("xelatex");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedPathType, setSelectedPathType] = useState<"file" | "dir" | null>(null);
  const [isDeletingProject, setIsDeletingProject] = useState(false);
  const [isCompileLogOpen, setIsCompileLogOpen] = useState(false);
  const [selectionRange, setSelectionRange] = useState<[number, number]>([0, 0]);
  const [feedbackItems, setFeedbackItems] = useState<LatexFeedbackItem[]>([]);
  const [feedbackLoaded, setFeedbackLoaded] = useState(false);
  const [feedbackDraftComment, setFeedbackDraftComment] = useState("");
  const [feedbackScope, setFeedbackScope] = useState<"selection" | "section">("section");
  const [activeFeedbackId, setActiveFeedbackId] = useState<string | null>(null);
  const [feedbackBusyId, setFeedbackBusyId] = useState<string | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<string>("");
  const [feedbackError, setFeedbackError] = useState<string>("");
  const [rewritePreviewFilePath, setRewritePreviewFilePath] = useState<string | null>(null);
  const [rewritePreviewFeedbackId, setRewritePreviewFeedbackId] = useState<string | null>(null);
  const [rewriteCandidates, setRewriteCandidates] = useState<LatexFeedbackRewriteCandidate[]>([]);
  const [selectedRewriteCandidateId, setSelectedRewriteCandidateId] = useState<string | null>(null);
  const [diffViewMode, setDiffViewMode] = useState<"inline" | "side-by-side">("inline");
  const [showWhitespaceOnlyDiff, setShowWhitespaceOnlyDiff] = useState(false);
  const [collapsedDiffHunks, setCollapsedDiffHunks] = useState<Record<string, boolean>>({});
  const [isApplyingRewrite, setIsApplyingRewrite] = useState(false);
  const [lastRewriteUndo, setLastRewriteUndo] = useState<LastRewriteUndoState | null>(null);
  const [fileChangePreviews, setFileChangePreviews] = useState<Record<string, LatexFileChangePreviewResponse>>({});
  const [busyFileChangeKey, setBusyFileChangeKey] = useState<string | null>(null);
  const [fileChangeError, setFileChangeError] = useState("");
  const [isProtectingActiveFile, setIsProtectingActiveFile] = useState(false);
  const [protectionStatus, setProtectionStatus] = useState("");
  const [protectionError, setProtectionError] = useState("");
  const [pdfDraftSelection, setPdfDraftSelection] = useState<PdfDraftSelection | null>(null);
  const [transientPdfAnchor, setTransientPdfAnchor] = useState<LatexPdfAnchor | null>(null);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const feedbackSaveTimerRef = useRef<number | null>(null);
  const texMapRequestSeqRef = useRef(0);
  const lastTexMapKeyRef = useRef("");

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    void loadProject(projectId).then(() => {
      if (initialFileChanges || initialAppliedFileChanges) {
        setReviewState(initialFileChanges ?? [], initialAppliedFileChanges ?? []);
      }
    });
  }, [
    initialAppliedFileChanges,
    initialFileChanges,
    loadProject,
    projectId,
    setReviewState,
  ]);

  useEffect(() => {
    setFileChangePreviews({});
    setBusyFileChangeKey(null);
    setFileChangeError("");
  }, [projectId]);

  const dirty = activeFileContent !== activeFileSavedContent;
  const effectiveSelectedPath = selectedPath || activeFilePath;
  const effectiveSelectedType = selectedPathType || (activeFilePath ? "file" : null);
  const currentFolder =
    effectiveSelectedType === "dir"
      ? effectiveSelectedPath || ""
      : effectiveSelectedPath
        ? effectiveSelectedPath.split("/").slice(0, -1).join("/")
        : "";
  const canOpenCompileLog = Boolean(compileResult || compileLog);
  const selectionText = useMemo(() => {
    if (activeFileKind !== "text") {
      return "";
    }
    const [start, end] = selectionRange;
    if (end <= start) {
      return "";
    }
    return activeFileContent.slice(start, end);
  }, [activeFileContent, activeFileKind, selectionRange]);
  const currentFileFeedbacks = useMemo(
    () =>
      feedbackItems.filter(
        (item) => item.file_path === activeFilePath,
      ),
    [activeFilePath, feedbackItems],
  );
  const hasPdfDraftSelection = Boolean(pdfDraftSelection?.text.trim());
  const canCreateFeedback = Boolean(
    feedbackDraftComment.trim()
    && (selectionText.trim().length > 0 || hasPdfDraftSelection),
  );
  const pdfHighlightFeedbacks = useMemo(
    () =>
      feedbackItems.map((item) => ({
        id: item.id,
        selectedText: item.selected_text,
        pdfAnchor: parsePdfAnchor(item.pdf_anchor),
      })),
    [feedbackItems],
  );
  const selectedRewriteCandidate = useMemo(() => {
    if (!rewriteCandidates.length) {
      return null;
    }
    if (!selectedRewriteCandidateId) {
      return rewriteCandidates[0];
    }
    return rewriteCandidates.find((item) => item.candidate_id === selectedRewriteCandidateId) || rewriteCandidates[0];
  }, [rewriteCandidates, selectedRewriteCandidateId]);
  const selectedRewriteCandidateIndex = useMemo(() => {
    if (!selectedRewriteCandidate) {
      return -1;
    }
    return rewriteCandidates.findIndex(
      (item) => item.candidate_id === selectedRewriteCandidate.candidate_id,
    );
  }, [rewriteCandidates, selectedRewriteCandidate]);
  const previewFeedbackItem = useMemo(
    () => feedbackItems.find((item) => item.id === rewritePreviewFeedbackId) || null,
    [feedbackItems, rewritePreviewFeedbackId],
  );
  const pendingReviewItems = useMemo(
    () => fileChanges.map((change) => fileChangeToPrismReviewItem(change)),
    [fileChanges],
  );
  const appliedReviewItems = useMemo(
    () =>
      appliedFileChanges.map((change) =>
        fileChangeToPrismReviewItem({
          ...change,
          status: change.status || "applied",
          title: change.title || change.path,
          reason: change.reason || change.applied_hash,
        }),
      ),
    [appliedFileChanges],
  );
  const clearRewritePreview = useCallback((resetPending = true) => {
    const previewFeedbackId = rewritePreviewFeedbackId;
    if (resetPending && previewFeedbackId) {
      setFeedbackItems((prev) =>
        prev.map((entry) => (
          entry.id === previewFeedbackId && entry.last_status === "pending"
            ? {
              ...entry,
              last_status: "idle",
              last_error: "",
            }
            : entry
        )),
      );
    }
    setRewritePreviewFilePath(null);
    setRewritePreviewFeedbackId(null);
    setRewriteCandidates([]);
    setSelectedRewriteCandidateId(null);
    setDiffViewMode("inline");
    setCollapsedDiffHunks({});
  }, [rewritePreviewFeedbackId]);

  useEffect(() => {
    setCollapsedDiffHunks({});
  }, [selectedRewriteCandidateId, rewritePreviewFeedbackId]);

  const handlePdfSelection = useCallback(async (payload: PdfDraftSelection) => {
    setPdfDraftSelection(payload);
    setFeedbackError("");
    if (!activeFilePath || activeFileKind !== "text") {
      setFeedbackStatus("已记录 PDF 选区，请先打开对应 TeX 文件再继续点评。");
      return;
    }

    try {
      const mapped = await mapLatexFeedbackSelection(projectId, {
        file_path: activeFilePath,
        selected_text: payload.text,
        history_id: compileResult?.history_id || null,
        pdf_anchor: {
          page: payload.page,
          text: payload.text,
          rects: payload.rects,
        },
        file_content: activeFileContent,
        source: "pdf",
      });
      if (mapped.file_path && mapped.file_path !== activeFilePath) {
        setSelectedPath(mapped.file_path);
        setSelectedPathType("file");
        await openFile(mapped.file_path);
      }
      setTransientPdfAnchor(parsePdfAnchor(mapped.pdf_anchor));
      setSelectionRange([mapped.resolved_selection_start, mapped.resolved_selection_end]);
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(
          mapped.resolved_selection_start,
          mapped.resolved_selection_end,
        );
      }
      setFeedbackStatus(
        `已将 PDF 划词映射到 TeX（${mapped.section_title}，${mapped.mapping_method === "synctex" ? "SyncTeX" : "文本回退"}）。`,
      );
      return;
    } catch {
      // Fall through to local matching fallback.
      setTransientPdfAnchor(null);
    }

    const preferred = selectionRange[0] || 0;
    const resolved = resolveSnippetRange(activeFileContent, payload.text, preferred);
    if (!resolved) {
      setFeedbackStatus("已记录 PDF 选区，但尚未在当前 TeX 中匹配到同段文本。");
      return;
    }
    setTransientPdfAnchor({
      page: payload.page,
      text: payload.text,
      rects: payload.rects,
    });
    setSelectionRange([resolved.start, resolved.end]);
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.setSelectionRange(resolved.start, resolved.end);
    }
    setFeedbackStatus("已将 PDF 划词映射到当前 TeX 选区（本地匹配）。");
  }, [
    activeFileContent,
    activeFileKind,
    activeFilePath,
    compileResult?.history_id,
    openFile,
    projectId,
    selectionRange,
  ]);

  useEffect(() => {
    setSelectionRange([0, 0]);
    setFeedbackDraftComment("");
    setActiveFeedbackId(null);
    setFeedbackBusyId(null);
    clearRewritePreview();
    setPdfDraftSelection(null);
    setTransientPdfAnchor(null);
  }, [activeFilePath, clearRewritePreview]);

  useEffect(() => {
    if (
      !compiledPdfUrl
      || !compileResult?.history_id
      || !activeFilePath
      || activeFileKind !== "text"
      || !selectionText.trim()
      || selectionRange[1] <= selectionRange[0]
    ) {
      setTransientPdfAnchor(null);
      lastTexMapKeyRef.current = "";
      return;
    }

    const mapKey = [
      compileResult.history_id,
      activeFilePath,
      String(selectionRange[0]),
      String(selectionRange[1]),
      selectionText,
    ].join("::");
    if (mapKey === lastTexMapKeyRef.current) {
      return;
    }
    lastTexMapKeyRef.current = mapKey;

    const requestSeq = texMapRequestSeqRef.current + 1;
    texMapRequestSeqRef.current = requestSeq;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void mapLatexFeedbackSelection(projectId, {
        file_path: activeFilePath,
        selected_text: selectionText,
        selection_start: selectionRange[0],
        selection_end: selectionRange[1],
        file_content: activeFileContent,
        history_id: compileResult.history_id,
        source: "tex",
      }).then((mapped) => {
        if (cancelled || requestSeq !== texMapRequestSeqRef.current) {
          return;
        }
        const anchor = parsePdfAnchor(mapped.pdf_anchor);
        setTransientPdfAnchor(anchor);
      }).catch(() => {
        if (!cancelled && requestSeq === texMapRequestSeqRef.current) {
          setTransientPdfAnchor(null);
        }
      });
    }, 280);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    activeFileContent,
    activeFileKind,
    activeFilePath,
    compileResult?.history_id,
    compiledPdfUrl,
    projectId,
    selectionRange,
    selectionText,
  ]);

  useEffect(() => {
    let cancelled = false;
    setFeedbackLoaded(false);
    setFeedbackItems([]);
    setFeedbackError("");
    setFeedbackStatus("");
    const load = async () => {
      try {
        const response = await getLatexProjectFeedback(projectId);
        if (cancelled) {
          return;
        }
        const normalized = Array.isArray(response.items)
          ? response.items
            .filter((item) => Boolean(item && typeof item === "object"))
            .map((item) => ({
              ...item,
              created_at: item.created_at || new Date().toISOString(),
            }))
          : [];
        setFeedbackItems(normalized);
      } catch (err) {
        if (!cancelled) {
          setFeedbackError(`加载点评失败: ${readClientErrorMessage(err)}`);
        }
      } finally {
        if (!cancelled) {
          setFeedbackLoaded(true);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!feedbackLoaded) {
      return;
    }
    if (feedbackSaveTimerRef.current) {
      window.clearTimeout(feedbackSaveTimerRef.current);
    }
    feedbackSaveTimerRef.current = window.setTimeout(() => {
      void saveLatexProjectFeedback(projectId, feedbackItems).catch((err) => {
        setFeedbackError(`保存点评失败: ${readClientErrorMessage(err)}`);
      });
    }, 500);
    return () => {
      if (feedbackSaveTimerRef.current) {
        window.clearTimeout(feedbackSaveTimerRef.current);
        feedbackSaveTimerRef.current = null;
      }
    };
  }, [feedbackItems, feedbackLoaded, projectId]);

  const createFeedbackFromSelection = useCallback(async (requireMappedForRewrite: boolean): Promise<LatexFeedbackItem | null> => {
    if (!activeFilePath || activeFileKind !== "text") {
      setFeedbackError("当前文件不可添加点评。");
      return null;
    }
    if (!feedbackDraftComment.trim()) {
      setFeedbackError("请先填写点评内容。");
      return null;
    }

    const localSelected = activeFileContent.slice(selectionRange[0], selectionRange[1]);
    let targetFilePath = activeFilePath;
    let start = selectionRange[0];
    let end = selectionRange[1];
    let selected = localSelected.trim() ? localSelected : "";
    let source: "tex" | "pdf" = selected ? "tex" : "pdf";
    let mappedAnchor: LatexFeedbackAnchor | null = null;
    let pdfAnchor: LatexFeedbackItem["pdf_anchor"] = transientPdfAnchor;

    if (!selected && pdfDraftSelection?.text.trim()) {
      const candidatePdfAnchor = {
        page: pdfDraftSelection.page,
        text: pdfDraftSelection.text,
        rects: pdfDraftSelection.rects,
      };
      pdfAnchor = candidatePdfAnchor;

      try {
        const mapped = await mapLatexFeedbackSelection(projectId, {
          file_path: activeFilePath,
          selected_text: pdfDraftSelection.text,
          history_id: compileResult?.history_id || null,
          pdf_anchor: candidatePdfAnchor,
          file_content: activeFileContent,
          source: "pdf",
        });
        targetFilePath = mapped.file_path || activeFilePath;
        start = mapped.resolved_selection_start;
        end = mapped.resolved_selection_end;
        selected = mapped.selected_text || pdfDraftSelection.text;
        mappedAnchor = mapped.updated_anchor;
        pdfAnchor = parsePdfAnchor(mapped.pdf_anchor) || candidatePdfAnchor;
        setTransientPdfAnchor(parsePdfAnchor(mapped.pdf_anchor));
        setFeedbackStatus(
          `点评定位完成（${mapped.mapping_method === "synctex" ? "SyncTeX" : "文本回退"}）`,
        );
      } catch {
        const resolved = resolveSnippetRange(
          activeFileContent,
          pdfDraftSelection.text,
          selectionRange[0] || 0,
        );
        if (!resolved) {
          if (requireMappedForRewrite) {
            setFeedbackError("当前 PDF 划词尚未映射到 TeX，无法直接改写。请先手动定位后再试。");
            return null;
          }
          setFeedbackError("当前 PDF 划词尚未映射到 TeX，请先切换到对应文本位置。");
          return null;
        }
        start = resolved.start;
        end = resolved.end;
        selected = activeFileContent.slice(start, end);
        source = "pdf";
      }
    }

    if (!selected.trim() || end <= start) {
      setFeedbackError("请先在主稿或 PDF 中划词。");
      return null;
    }

    if (targetFilePath !== activeFilePath) {
      setSelectedPath(targetFilePath);
      setSelectedPathType("file");
      await openFile(targetFilePath);
    }

    setSelectionRange([start, end]);
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.setSelectionRange(start, end);
    }

    const anchor = mappedAnchor || buildFeedbackAnchor(activeFileContent, start, end);
    return {
      id: createFeedbackId(),
      file_path: targetFilePath,
      start,
      end,
      selected_text: selected,
      comment: feedbackDraftComment.trim(),
      created_at: new Date().toISOString(),
      anchor,
      source,
      pdf_anchor: pdfAnchor,
      last_status: "idle",
      last_error: "",
    };
  }, [
    activeFileContent,
    activeFileKind,
    activeFilePath,
    compileResult?.history_id,
    feedbackDraftComment,
    openFile,
    pdfDraftSelection,
    projectId,
    selectionRange,
    transientPdfAnchor,
  ]);

  const addFeedbackOnly = useCallback(async () => {
    const item = await createFeedbackFromSelection(false);
    if (!item) {
      return;
    }
    setFeedbackError("");
    setFeedbackStatus("点评已保存。");
    setFeedbackItems((prev) => [...prev, item]);
    setActiveFeedbackId(item.id);
    setFeedbackDraftComment("");
    setPdfDraftSelection(null);
  }, [createFeedbackFromSelection]);

  const focusFeedback = useCallback((item: LatexFeedbackItem) => {
    if (!editorRef.current || activeFileKind !== "text") {
      return;
    }
    const resolved = resolveFeedbackRange(item, activeFileContent);
    if (!resolved) {
      setActiveFeedbackId(item.id);
      setFeedbackError("无法在当前文本中定位该点评。");
      return;
    }
    editorRef.current.focus();
    editorRef.current.setSelectionRange(resolved.start, resolved.end);
    setSelectionRange([resolved.start, resolved.end]);
    setTransientPdfAnchor(null);
    setActiveFeedbackId(item.id);
    setFeedbackError("");
  }, [activeFileContent, activeFileKind]);

  const removeFeedback = useCallback((feedbackId: string) => {
    setFeedbackItems((prev) => prev.filter((item) => item.id !== feedbackId));
    if (activeFeedbackId === feedbackId) {
      setActiveFeedbackId(null);
    }
    if (rewritePreviewFeedbackId === feedbackId) {
      clearRewritePreview(false);
    }
    if (lastRewriteUndo?.feedback_id === feedbackId) {
      setLastRewriteUndo(null);
    }
  }, [activeFeedbackId, clearRewritePreview, lastRewriteUndo, rewritePreviewFeedbackId]);

  const rewriteFromFeedback = useCallback(async (item: LatexFeedbackItem) => {
    if (!project || activeFileKind !== "text") {
      setFeedbackError("当前文件不可执行点评改写。");
      return;
    }
    if (rewritePreviewFeedbackId && rewritePreviewFeedbackId !== item.id) {
      clearRewritePreview();
    }
    setFeedbackBusyId(item.id);
    setFeedbackError("");
    setFeedbackStatus("");
    try {
      const resolved = resolveFeedbackRange(item, activeFileContent);
      if (!resolved) {
        throw new Error("无法在当前文本中定位该点评原文。");
      }
      const response = await previewLatexFeedbackRewrite(project.id, {
        file_path: item.file_path,
        selected_text: resolved.text,
        comment: item.comment,
        selection_start: resolved.start,
        selection_end: resolved.end,
        anchor: item.anchor || buildFeedbackAnchor(activeFileContent, resolved.start, resolved.end),
        scope: feedbackScope,
        file_content: activeFileContent,
      });
      if (!response.candidates || response.candidates.length === 0) {
        throw new Error("模型未返回可用改写候选。");
      }
      setRewritePreviewFilePath(response.file_path);
      setRewritePreviewFeedbackId(item.id);
      setRewriteCandidates(response.candidates);
      setSelectedRewriteCandidateId(response.candidates[0].candidate_id);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? {
              ...entry,
              last_status: "pending",
              last_error: "",
            }
            : entry,
        ),
      );
      const nextStart = response.resolved_selection_start;
      const nextEnd = response.resolved_selection_end;
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(nextStart, nextEnd);
      }
      setSelectionRange([nextStart, nextEnd]);
      setActiveFeedbackId(item.id);
      setFeedbackStatus("已生成改写候选，请先查看 diff 并确认应用。");
    } catch (err) {
      const message = readClientErrorMessage(err);
      setFeedbackError(`点评改写失败: ${message}`);
      clearRewritePreview(false);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
    } finally {
      setFeedbackBusyId(null);
    }
  }, [
    activeFileContent,
    activeFileKind,
    clearRewritePreview,
    feedbackScope,
    project,
    rewritePreviewFeedbackId,
  ]);

  const applyRewriteCandidate = useCallback(async () => {
    if (!project || !selectedRewriteCandidate || !rewritePreviewFeedbackId || !rewritePreviewFilePath) {
      return;
    }
    setIsApplyingRewrite(true);
    setFeedbackError("");
    try {
      const response = await applyLatexFeedbackRewrite(project.id, {
        file_path: rewritePreviewFilePath,
        candidate_id: selectedRewriteCandidate.candidate_id,
        candidate_signature: selectedRewriteCandidate.candidate_signature,
        target_start: selectedRewriteCandidate.target_start,
        target_end: selectedRewriteCandidate.target_end,
        rewritten_text: selectedRewriteCandidate.rewritten_text,
        base_file_hash: selectedRewriteCandidate.base_file_hash,
        base_range_hash: selectedRewriteCandidate.base_range_hash,
      });

      if (activeFilePath !== response.file_path) {
        setSelectedPath(response.file_path);
        setSelectedPathType("file");
      }
      await openFile(response.file_path);

      const nextEnd = response.target_start + response.rewritten_text.length;
      setSelectionRange([response.target_start, nextEnd]);
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(response.target_start, nextEnd);
      }

      setFeedbackItems((prev) =>
        shiftFeedbacksAfterRewrite(
          prev,
          response.file_path,
          rewritePreviewFeedbackId,
          response.target_start,
          response.target_end,
          response.rewritten_text,
          response.applied_content,
        ).map((entry) => (
          entry.id === rewritePreviewFeedbackId
            ? {
              ...entry,
              anchor: response.updated_anchor,
              pdf_anchor: null,
              last_status: "done",
              last_error: "",
            }
            : entry
        )),
      );
      setActiveFeedbackId(rewritePreviewFeedbackId);
      setLastRewriteUndo({
        ...response.undo,
        file_path: response.file_path,
        feedback_id: rewritePreviewFeedbackId,
      });
      setFeedbackStatus("已应用改写并写回文件。");
      clearRewritePreview(false);
    } catch (err) {
      const code = readClientErrorCode(err);
      let message = readClientErrorMessage(err);
      if (code === "rewrite_compile_failed") {
        const compileError = readClientErrorDetailField(err, "compile_error");
        message = compileError
          ? `编译校验未通过（已自动回滚）：${compileError}`
          : "编译校验未通过，系统已自动回滚。";
        setFeedbackStatus("候选未被应用，文件已自动回滚。");
      } else if (code && STRUCTURE_REWRITE_ERROR_CODES.has(code)) {
        message = "改写未通过结构安全校验，请切换候选或重新生成。";
      }
      const staleCandidate = Boolean(code && STALE_REWRITE_ERROR_CODES.has(code));
      setFeedbackError(`应用改写失败: ${message}`);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === rewritePreviewFeedbackId
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
      if (staleCandidate) {
        clearRewritePreview(false);
        setFeedbackStatus("改写候选已失效，请重新生成 diff。");
      }
    } finally {
      setIsApplyingRewrite(false);
    }
  }, [
    activeFilePath,
    clearRewritePreview,
    openFile,
    project,
    rewritePreviewFeedbackId,
    rewritePreviewFilePath,
    selectedRewriteCandidate,
  ]);

  const regenerateRewritePreview = useCallback(async () => {
    if (!previewFeedbackItem || feedbackBusyId || isApplyingRewrite) {
      return;
    }
    await rewriteFromFeedback(previewFeedbackItem);
  }, [feedbackBusyId, isApplyingRewrite, previewFeedbackItem, rewriteFromFeedback]);

  const copySelectedRewrite = useCallback(async () => {
    if (!selectedRewriteCandidate) {
      return;
    }
    if (!navigator?.clipboard?.writeText) {
      setFeedbackError("当前环境不支持复制到剪贴板。");
      return;
    }
    try {
      await navigator.clipboard.writeText(selectedRewriteCandidate.rewritten_text);
      setFeedbackStatus("已复制当前候选改写文本。");
    } catch {
      setFeedbackError("复制失败，请检查浏览器剪贴板权限。");
    }
  }, [selectedRewriteCandidate]);

  const toggleDiffHunkCollapsed = useCallback((hunkKey: string) => {
    setCollapsedDiffHunks((prev) => ({
      ...prev,
      [hunkKey]: !prev[hunkKey],
    }));
  }, []);

  const setAllDiffHunksCollapsed = useCallback((collapsed: boolean) => {
    if (!selectedRewriteCandidate) {
      return;
    }
    const next: Record<string, boolean> = {};
    selectedRewriteCandidate.diff.hunks.forEach((hunk, index) => {
      const key = `${hunk.old_start}-${hunk.old_end}-${hunk.new_start}-${hunk.new_end}-${index}`;
      next[key] = collapsed;
    });
    setCollapsedDiffHunks(next);
  }, [selectedRewriteCandidate]);

  const undoLastRewrite = useCallback(async () => {
    if (!project || !lastRewriteUndo) {
      return;
    }
    setIsApplyingRewrite(true);
    setFeedbackError("");
    try {
      const response = await revertLatexFeedbackRewrite(project.id, {
        file_path: lastRewriteUndo.file_path,
        candidate_id: lastRewriteUndo.candidate_id,
        revert_start: lastRewriteUndo.revert_start,
        revert_end: lastRewriteUndo.revert_end,
        rewritten_text: lastRewriteUndo.rewritten_text,
        previous_text: lastRewriteUndo.previous_text,
        applied_file_hash: lastRewriteUndo.applied_file_hash,
        revert_signature: lastRewriteUndo.revert_signature,
      });

      if (activeFilePath !== response.file_path) {
        setSelectedPath(response.file_path);
        setSelectedPathType("file");
      }
      await openFile(response.file_path);

      const nextEnd = response.revert_start + response.restored_text.length;
      setSelectionRange([response.revert_start, nextEnd]);
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(response.revert_start, nextEnd);
      }

      setFeedbackItems((prev) =>
        shiftFeedbacksAfterRewrite(
          prev,
          response.file_path,
          lastRewriteUndo.feedback_id,
          response.revert_start,
          response.revert_end,
          response.restored_text,
          response.reverted_content,
        ).map((entry) =>
          entry.id === lastRewriteUndo.feedback_id
            ? {
              ...entry,
              anchor: response.updated_anchor,
              pdf_anchor: null,
              last_status: "idle",
              last_error: "",
            }
            : entry,
        ),
      );
      setActiveFeedbackId(lastRewriteUndo.feedback_id);
      setFeedbackStatus("已撤销最近一次改写。");
      setLastRewriteUndo(null);
    } catch (err) {
      setFeedbackError(`撤销改写失败: ${readClientErrorMessage(err)}`);
    } finally {
      setIsApplyingRewrite(false);
    }
  }, [activeFilePath, lastRewriteUndo, openFile, project]);

  useEffect(() => {
    if (!rewritePreviewFeedbackId || !selectedRewriteCandidate) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "enter") {
        if (!isApplyingRewrite && !isSaving) {
          event.preventDefault();
          void applyRewriteCandidate();
        }
        return;
      }
      if (event.key === "Escape" && !isApplyingRewrite) {
        event.preventDefault();
        clearRewritePreview();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [
    applyRewriteCandidate,
    clearRewritePreview,
    isApplyingRewrite,
    isSaving,
    rewritePreviewFeedbackId,
    selectedRewriteCandidate,
  ]);

  const addFeedbackAndRewrite = useCallback(async () => {
    const item = await createFeedbackFromSelection(true);
    if (!item) {
      return;
    }
    setFeedbackItems((prev) => [...prev, item]);
    setActiveFeedbackId(item.id);
    setFeedbackDraftComment("");
    setPdfDraftSelection(null);
    await rewriteFromFeedback(item);
  }, [createFeedbackFromSelection, rewriteFromFeedback]);

  const previewProjectFileChange = useCallback(async (change: LatexFileChange) => {
    if (!project) {
      return;
    }
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      const preview = await previewLatexFileChange(project.id, {
        logical_key: change.logical_key,
      });
      setFileChangePreviews((prev) => ({
        ...prev,
        [change.logical_key]: preview,
      }));
    } catch (err) {
      setFileChangeError(`生成写入 diff 失败: ${readClientErrorMessage(err)}`);
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [project]);

  const focusedReviewItemId = searchParams.get("review_item_id")?.trim() || null;
  const focusedLogicalKey = searchParams.get("logical_key")?.trim() || null;

  useEffect(() => {
    if (
      !project ||
      searchParams.get("focus") !== "file_changes" ||
      fileChanges.length === 0
    ) {
      return;
    }

    const targetChange =
      fileChanges.find(
        (change) =>
          (focusedReviewItemId && change.id === focusedReviewItemId) ||
          (focusedLogicalKey && change.logical_key === focusedLogicalKey),
      ) ?? null;
    const focusKey = [
      projectId,
      project.id,
      focusedReviewItemId ?? "",
      focusedLogicalKey ?? "",
      targetChange?.logical_key ?? "all",
      fileChanges.length,
    ].join(":");
    if (lastFileChangeFocusKey.current === focusKey) {
      return;
    }
    lastFileChangeFocusKey.current = focusKey;

    fileChangesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (!targetChange) {
      return;
    }
    if (targetChange.path && activeFilePath !== targetChange.path) {
      void openFile(targetChange.path);
    }
    void previewProjectFileChange(targetChange);
  }, [
    activeFilePath,
    fileChanges,
    focusedLogicalKey,
    focusedReviewItemId,
    openFile,
    previewProjectFileChange,
    project,
    projectId,
    searchParams,
  ]);

  const applyPendingFileChange = useCallback(async (change: LatexFileChange) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await applyFileChange(change.logical_key);
      onReviewStateChanged?.();
      setFileChangePreviews((prev) => {
        const next = { ...prev };
        delete next[change.logical_key];
        return next;
      });
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [applyFileChange, onReviewStateChanged]);

  const discardPendingFileChange = useCallback(async (change: LatexFileChange) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await discardFileChange(change.logical_key);
      onReviewStateChanged?.();
      setFileChangePreviews((prev) => {
        const next = { ...prev };
        delete next[change.logical_key];
        return next;
      });
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [discardFileChange, onReviewStateChanged]);

  const deferPendingFileChange = useCallback(async (change: LatexFileChange) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await deferFileChange(change.logical_key);
      onReviewStateChanged?.();
      setFileChangePreviews((prev) => {
        const next = { ...prev };
        delete next[change.logical_key];
        return next;
      });
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [deferFileChange, onReviewStateChanged]);

  const revertAppliedFileChange = useCallback(async (change: {
    logical_key: string;
    revert_signature: string;
  }) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await revertFileChange(change.logical_key, change.revert_signature);
      onReviewStateChanged?.();
      setFileChangePreviews((prev) => {
        const next = { ...prev };
        delete next[change.logical_key];
        return next;
      });
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [onReviewStateChanged, revertFileChange]);

  const protectActiveFile = useCallback(async () => {
    if (!project || !activeFilePath || activeFileKind !== "text") {
      return;
    }
    setIsProtectingActiveFile(true);
    setProtectionStatus("");
    setProtectionError("");
    try {
      await protectLatexSection(project.id, {
        path: activeFilePath,
        scope: "file",
        reason: "user_manual_protect",
      });
      onReviewStateChanged?.();
      setProtectionStatus("当前文件已保护，后续 agent 会以建议形式处理改写。");
    } catch (err) {
      setProtectionError(`保护当前文件失败: ${readClientErrorMessage(err)}`);
    } finally {
      setIsProtectingActiveFile(false);
    }
  }, [activeFileKind, activeFilePath, onReviewStateChanged, project]);

  return (
    <main className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <Header />
      <section className="mx-auto max-w-[1500px] px-6 pb-10 pt-28">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => router.push(workspaceId ? `/workspaces/${workspaceId}` : "/workspaces")}
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              {workspaceId ? "返回 Workbench" : "返回工作区"}
            </Button>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--brand-brass)]">
                Latex Project
              </p>
              <h1 className="mt-1 text-2xl font-semibold">
                {project?.name || "加载项目中..."}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="rounded-full border border-[var(--border-default)] bg-white/70 px-4 py-2 text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">
              主文件 {project?.main_file || "main.tex"}
            </div>
            <Button
              variant="destructive"
              disabled={!project || isDeletingProject || isProjectLoading}
              onClick={async () => {
                if (!project) {
                  return;
                }
                const confirmed = window.confirm(
                  `确定删除 LaTeX 项目「${project.name}」吗？`,
                );
                if (!confirmed) {
                  return;
                }
                setIsDeletingProject(true);
                try {
                  await deleteProject();
                  router.push(workspaceId ? `/workspaces/${workspaceId}` : "/workspaces");
                } finally {
                  setIsDeletingProject(false);
                }
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {isDeletingProject ? "删除中..." : "删除项目"}
            </Button>
          </div>
        </div>

        {error ? (
          <div className="mb-4 rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        ) : null}

        <div className="grid gap-5 xl:grid-cols-2">
          <section className="space-y-4">
            <LatexToolbar
              engine={engine}
              onEngineChange={setEngine}
              onSave={() => void saveActiveFile()}
              onCompile={() => void compileProject(engine)}
              onCreateFile={(path) => createFile(path)}
              onCreateFolder={(path) => createFolder(path)}
              onUploadFiles={(files) => uploadFiles(files, currentFolder || undefined)}
              onUploadDirectory={(files) => uploadDirectory(files, currentFolder || undefined)}
              onUploadArchive={(archive) => uploadArchive(archive, currentFolder || undefined)}
              isSaving={isSaving}
              isCompiling={isCompiling}
              disableActions={isProjectLoading}
              currentFolderLabel={currentFolder || "项目根目录"}
            />

            {fileChanges.length > 0 ? (
              <div ref={fileChangesRef} className="rounded-[1.5rem] border border-amber-500/25 bg-amber-500/10 p-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-700" />
                  <p className="text-sm font-medium text-amber-900">
                    Prism 待确认写入
                  </p>
                </div>
                <p className="mt-2 text-xs leading-6 text-amber-900/80">
                  来自 Compute 的生成内容需要确认后才会写入当前 LaTeX 项目。
                </p>
                {fileChangeError ? (
                  <div className="mt-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
                    {fileChangeError}
                  </div>
                ) : null}
                <PrismReviewList
                  className="mt-3"
                  items={pendingReviewItems}
                  focusedItemId={focusedReviewItemId}
                  focusedLogicalKey={focusedLogicalKey}
                  renderActions={(item) => {
                    const change = fileChanges.find(
                      (entry) => entry.logical_key === item.logical_key,
                    );
                    if (!change) return null;
                    const preview = fileChangePreviews[change.logical_key] ?? null;
                    const isBusy = isSaving || busyFileChangeKey === change.logical_key;
                    return (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void previewProjectFileChange(change)}
                          disabled={isBusy}
                        >
                          <Eye className="mr-1.5 h-3.5 w-3.5" />
                          {busyFileChangeKey === change.logical_key
                            ? "处理中..."
                            : preview
                              ? "刷新 diff"
                              : "预览 diff"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void deferPendingFileChange(change)}
                          disabled={isBusy || change.status === "deferred"}
                        >
                          {change.status === "deferred" ? "已稍后" : "稍后处理"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void discardPendingFileChange(change)}
                          disabled={isBusy}
                        >
                          忽略本次
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => void applyPendingFileChange(change)}
                          disabled={isBusy}
                        >
                          应用到 Prism
                        </Button>
                      </>
                    );
                  }}
                  renderDetails={(item) => {
                    const preview = fileChangePreviews[item.logical_key] ?? null;
                    return preview ? (
                      <LatexFileChangeDiffPreview
                        preview={preview}
                        maxOps={8}
                        className="mt-3"
                      />
                    ) : null;
                  }}
                />
              </div>
            ) : null}

            {appliedFileChanges.length > 0 ? (
              <div className="rounded-[1.5rem] border border-emerald-500/20 bg-emerald-500/8 p-4">
                <div className="flex items-center gap-2">
                  <RotateCcw className="h-4 w-4 text-emerald-700" />
                  <p className="text-sm font-medium text-emerald-900">
                    Prism 已写入变更
                  </p>
                </div>
                <p className="mt-2 text-xs leading-6 text-emerald-900/80">
                  已应用的 Compute 写入仍保留哈希校验撤回点，文件被后续手动修改后不会盲目覆盖。
                </p>
                <PrismReviewList
                  className="mt-3"
                  items={appliedReviewItems}
                  focusedItemId={focusedReviewItemId}
                  focusedLogicalKey={focusedLogicalKey}
                  renderActions={(item) => {
                    const change = appliedFileChanges.find(
                      (entry) => entry.logical_key === item.logical_key,
                    );
                    if (!change) return null;
                    const isBusy = isSaving || busyFileChangeKey === change.logical_key;
                    return (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void revertAppliedFileChange(change)}
                        disabled={isBusy}
                      >
                        <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                        {busyFileChangeKey === change.logical_key ? "撤回中..." : "撤回写入"}
                      </Button>
                    );
                  }}
                />
              </div>
            ) : null}

            <div className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.95)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  划词点评与改写
                </p>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <span className="text-xs text-[var(--text-muted)]">
                    选中主稿文本后可直接点评
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void protectActiveFile()}
                    disabled={
                      isProtectingActiveFile ||
                      !activeFilePath ||
                      activeFileKind !== "text"
                    }
                  >
                    <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                    {isProtectingActiveFile ? "保护中..." : "保护当前文件"}
                  </Button>
                </div>
              </div>
              {protectionStatus ? (
                <div className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
                  {protectionStatus}
                </div>
              ) : null}
              {protectionError ? (
                <div className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
                  {protectionError}
                </div>
              ) : null}
              <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                <textarea
                  value={feedbackDraftComment}
                  onChange={(event) => setFeedbackDraftComment(event.target.value)}
                  placeholder="例如：这一段贡献点不够清晰，请加强问题定义和定量结论。"
                  className="min-h-[92px] rounded-xl border border-[var(--border-default)] bg-white/85 px-3 py-2 text-sm leading-6"
                />
                <div className="space-y-2">
                  <label className="block text-xs text-[var(--text-muted)]">改写范围</label>
                  <select
                    value={feedbackScope}
                    onChange={(event) => setFeedbackScope(event.target.value as "selection" | "section")}
                    className="w-full rounded-lg border border-[var(--border-default)] bg-white/90 px-2 py-2 text-sm"
                  >
                    <option value="section">重写所在 section</option>
                    <option value="selection">仅重写选区</option>
                  </select>
                  <Button
                    variant="outline"
                    disabled={!canCreateFeedback || isSaving}
                    onClick={addFeedbackOnly}
                    className="w-full"
                  >
                    只保存点评
                  </Button>
                  <Button
                    disabled={!canCreateFeedback || isSaving}
                    onClick={() => void addFeedbackAndRewrite()}
                    className="w-full"
                  >
                    点评并生成改写
                  </Button>
                </div>
              </div>
              <div className="mt-2 text-xs text-[var(--text-muted)]">
                {selectionText.trim()
                  ? `当前 TeX 已选中 ${selectionText.length} 个字符。`
                  : hasPdfDraftSelection
                    ? `当前 PDF 已选中 ${pdfDraftSelection?.text.trim().length || 0} 个字符。`
                    : "请先在主稿编辑区或 PDF 预览区划词，再添加点评。"}
              </div>
              {feedbackError ? (
                <div className="mt-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
                  {feedbackError}
                </div>
              ) : null}
              {feedbackStatus ? (
                <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
                  {feedbackStatus}
                </div>
              ) : null}
              {lastRewriteUndo ? (
                <div className="mt-2 flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-white/80 px-3 py-2">
                  <p className="text-xs text-[var(--text-muted)]">可撤销最近一次改写</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void undoLastRewrite()}
                    disabled={isApplyingRewrite || isSaving}
                  >
                    {isApplyingRewrite ? "处理中..." : "撤销最近改写"}
                  </Button>
                </div>
              ) : null}
              {rewritePreviewFeedbackId && selectedRewriteCandidate ? (
                <div className="mt-3 rounded-xl border border-[var(--border-default)] bg-white/80 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                        Rewrite Diff Preview
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        候选 {selectedRewriteCandidateIndex + 1}/{rewriteCandidates.length} · Ctrl/Cmd + Enter 应用 · Esc 取消
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="inline-flex rounded-md border border-[var(--border-default)] bg-white/80 p-0.5">
                        <button
                          type="button"
                          onClick={() => setDiffViewMode("inline")}
                          className={`rounded px-2 py-1 text-xs ${diffViewMode === "inline" ? "bg-[var(--brand-navy)] text-white" : "text-[var(--text-muted)]"}`}
                        >
                          Inline
                        </button>
                        <button
                          type="button"
                          onClick={() => setDiffViewMode("side-by-side")}
                          className={`rounded px-2 py-1 text-xs ${diffViewMode === "side-by-side" ? "bg-[var(--brand-navy)] text-white" : "text-[var(--text-muted)]"}`}
                        >
                          Side-by-side
                        </button>
                      </div>
                      <select
                        value={selectedRewriteCandidate.candidate_id}
                        onChange={(event) => setSelectedRewriteCandidateId(event.target.value)}
                        className="rounded-md border border-[var(--border-default)] bg-white px-2 py-1 text-xs"
                      >
                        {rewriteCandidates.map((candidate, index) => (
                          <option key={candidate.candidate_id} value={candidate.candidate_id}>
                            候选 {index + 1} · {rewriteProfileLabel(candidate.profile)} · {riskLevelLabel(candidate.risk_level)}
                          </option>
                        ))}
                      </select>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void regenerateRewritePreview()}
                        disabled={!previewFeedbackItem || Boolean(feedbackBusyId) || isApplyingRewrite}
                      >
                        {feedbackBusyId ? "重生成中..." : "重生成"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void copySelectedRewrite()}
                        disabled={isApplyingRewrite}
                      >
                        复制改写
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => clearRewritePreview()}
                        disabled={isApplyingRewrite}
                      >
                        取消
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => void applyRewriteCandidate()}
                        disabled={isApplyingRewrite || isSaving}
                      >
                        {isApplyingRewrite ? "应用中..." : "确认应用"}
                      </Button>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-[var(--text-muted)]">
                    {selectedRewriteCandidate.scope === "section"
                      ? `重写范围：section（${selectedRewriteCandidate.section_title}）`
                      : "重写范围：仅选区"}
                    {" · "}
                    风格：{rewriteProfileLabel(selectedRewriteCandidate.profile)}
                    {" · "}
                    <span className={`inline-flex rounded-full border px-1.5 py-0.5 ${riskLevelClass(selectedRewriteCandidate.risk_level)}`}>
                      {riskLevelLabel(selectedRewriteCandidate.risk_level)}
                    </span>
                    {" · "}
                    变更 token {selectedRewriteCandidate.diff.stats.tokens_changed}
                    {" · +"}
                    {selectedRewriteCandidate.diff.stats.chars_added}
                    {" / -"}
                    {selectedRewriteCandidate.diff.stats.chars_deleted}
                  </p>
                  {selectedRewriteCandidate.changes_summary.trim() ? (
                    <p className="mt-2 rounded-lg border border-[var(--border-default)] bg-white/80 px-2 py-1 text-xs text-[var(--text-primary)]">
                      模型摘要：{selectedRewriteCandidate.changes_summary.trim()}
                    </p>
                  ) : null}
                  {selectedRewriteCandidate.diff.risk_flags.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedRewriteCandidate.diff.risk_flags.map((flag) => (
                        <span
                          key={flag}
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${riskFlagClass(flag)}`}
                        >
                          {riskFlagLabel(flag)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setShowWhitespaceOnlyDiff((prev) => !prev)}
                    >
                      {showWhitespaceOnlyDiff ? "隐藏空白改动" : "显示空白改动"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setAllDiffHunksCollapsed(true)}
                    >
                      折叠全部 Hunk
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setAllDiffHunksCollapsed(false)}
                    >
                      展开全部 Hunk
                    </Button>
                  </div>
                  <div className="mt-3 max-h-[320px] space-y-2 overflow-auto rounded-lg border border-[var(--border-default)] bg-[rgba(19,34,53,0.03)] p-2">
                    {selectedRewriteCandidate.diff.hunks.length === 0 ? (
                      <p className="text-xs text-[var(--text-muted)]">未检测到文本差异。</p>
                    ) : (
                      selectedRewriteCandidate.diff.hunks.map((hunk, index) => {
                        const hunkKey = `${hunk.old_start}-${hunk.old_end}-${hunk.new_start}-${hunk.new_end}-${index}`;
                        const changedOps = hunk.ops.filter((op) => op.op !== "equal");
                        const hiddenWhitespaceCount = changedOps.filter((op) => isWhitespaceOnlyDiffOp(op)).length;
                        const visibleOps = showWhitespaceOnlyDiff
                          ? changedOps
                          : changedOps.filter((op) => !isWhitespaceOnlyDiffOp(op));
                        const isCollapsed = Boolean(collapsedDiffHunks[hunkKey]);
                        return (
                          <div key={hunkKey} className="rounded-md border border-[var(--border-default)] bg-white/80 p-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-[11px] text-[var(--text-muted)]">
                                Hunk #{index + 1} · old {hunk.old_start}-{hunk.old_end} · new {hunk.new_start}-{hunk.new_end}
                              </p>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => toggleDiffHunkCollapsed(hunkKey)}
                              >
                                {isCollapsed ? "展开" : "折叠"}
                              </Button>
                            </div>
                            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                              token {hunk.stats.tokens_changed} · +{hunk.stats.chars_added} / -{hunk.stats.chars_deleted}
                              {hiddenWhitespaceCount > 0 && !showWhitespaceOnlyDiff
                                ? ` · 已隐藏空白改动 ${hiddenWhitespaceCount} 条`
                                : ""}
                            </p>
                            {hunk.risk_flags.length > 0 ? (
                              <div className="mt-1 flex flex-wrap gap-1.5">
                                {hunk.risk_flags.map((flag) => (
                                  <span key={flag} className={`rounded-full border px-2 py-0.5 text-[10px] ${riskFlagClass(flag)}`}>
                                    {riskFlagLabel(flag)}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            {!isCollapsed ? (
                              visibleOps.length > 0 ? (
                                diffViewMode === "inline" ? (
                                  <div className="mt-1 space-y-1">
                                    {visibleOps.map((op, opIndex) => (
                                      <div key={`${op.old_start}-${op.new_start}-${opIndex}`} className="text-xs leading-5">
                                        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                                          <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                            {diffOpLabel(op.op)}
                                          </span>
                                          <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                            {tokenKindLabel(op.token_kind)}
                                          </span>
                                          {isWhitespaceOnlyDiffOp(op) ? (
                                            <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                              仅空白改动
                                            </span>
                                          ) : null}
                                        </div>
                                        {op.op === "replace" ? (
                                          <>
                                            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-0.5 font-mono text-[12px] text-red-700">- {op.old_text || "(空)"}</pre>
                                            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[12px] text-emerald-700">+ {op.new_text || "(空)"}</pre>
                                          </>
                                        ) : op.op === "insert" ? (
                                          <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[12px] text-emerald-700">+ {op.new_text || "(空)"}</pre>
                                        ) : (
                                          <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-0.5 font-mono text-[12px] text-red-700">- {op.old_text || "(空)"}</pre>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="mt-1 space-y-1">
                                    {visibleOps.map((op, opIndex) => (
                                      <div key={`${op.old_start}-${op.new_start}-${opIndex}`} className="space-y-1">
                                        <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                                          <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                            {diffOpLabel(op.op)}
                                          </span>
                                          <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                            {tokenKindLabel(op.token_kind)}
                                          </span>
                                          {isWhitespaceOnlyDiffOp(op) ? (
                                            <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                              仅空白改动
                                            </span>
                                          ) : null}
                                        </div>
                                        <div className="grid gap-2 md:grid-cols-2">
                                          <pre className={`overflow-x-auto whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-[12px] ${op.op === "insert" ? "bg-[rgba(19,34,53,0.04)] text-[var(--text-muted)]" : "bg-red-500/10 text-red-700"}`}>
                                            {op.op === "insert" ? "(空)" : op.old_text || "(空)"}
                                          </pre>
                                          <pre className={`overflow-x-auto whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-[12px] ${op.op === "delete" ? "bg-[rgba(19,34,53,0.04)] text-[var(--text-muted)]" : "bg-emerald-500/10 text-emerald-700"}`}>
                                            {op.op === "delete" ? "(空)" : op.new_text || "(空)"}
                                          </pre>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )
                              ) : (
                                <p className="mt-1 text-xs text-[var(--text-muted)]">当前 hunk 仅包含空白改动。</p>
                              )
                            ) : null}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ) : null}
              <div className="mt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  当前文件点评
                </p>
                {!feedbackLoaded ? (
                  <div className="text-xs text-[var(--text-muted)]">加载点评中...</div>
                ) : currentFileFeedbacks.length === 0 ? (
                  <div className="text-xs text-[var(--text-muted)]">当前文件还没有点评。</div>
                ) : (
                  <div className="space-y-2">
                    {currentFileFeedbacks.map((item, index) => (
                      <div
                        key={item.id}
                        className={`rounded-xl border px-3 py-2 ${
                          activeFeedbackId === item.id
                            ? "border-[var(--brand-brass)] bg-[rgba(180,134,63,0.08)]"
                            : "border-[var(--border-default)] bg-white/80"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-medium">点评 #{index + 1}</p>
                          <div className="text-[11px] text-[var(--text-muted)]">
                            {item.last_status === "error"
                              ? "失败"
                              : item.last_status === "pending"
                                ? "待确认"
                                : item.last_status === "done"
                                  ? "已采纳"
                                  : "已保存"}
                          </div>
                        </div>
                        <p className="mt-1 line-clamp-3 text-xs text-[var(--text-muted)]">
                          {item.selected_text}
                        </p>
                        <p className="mt-1 text-sm">{item.comment}</p>
                        {item.last_error ? (
                          <p className="mt-1 text-xs text-red-600">{item.last_error}</p>
                        ) : null}
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Button size="sm" variant="outline" onClick={() => focusFeedback(item)}>
                            定位
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => void rewriteFromFeedback(item)}
                            disabled={feedbackBusyId === item.id || isApplyingRewrite}
                          >
                            {feedbackBusyId === item.id ? "生成中..." : "AI 重写"}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => removeFeedback(item.id)}>
                            删除
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
              <aside className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  文件
                </p>
                <div className="mt-4">
                  <LatexFileTree
                    items={tree}
                    selectedPath={effectiveSelectedPath}
                    onOpenFile={(path) => {
                      setSelectedPath(path);
                      setSelectedPathType("file");
                      void openFile(path);
                    }}
                    onSelectPath={(path, type) => {
                      setSelectedPath(path);
                      setSelectedPathType(type);
                    }}
                    onRenamePath={(fromPath, toPath) => renamePath(fromPath, toPath)}
                    onDeletePath={(path) => deletePath(path)}
                    onReorder={(folder, order) => saveOrder(folder, order)}
                  />
                </div>
              </aside>

              <div className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.95)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">
                      {activeFilePath || "未选择文件"}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      {activeFileKind === "blob"
                        ? "当前文件以预览模式打开"
                        : dirty
                          ? "存在未保存修改"
                          : "内容已同步"}
                    </p>
                  </div>
                  {isFileLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />
                  ) : null}
                </div>
                {activeFileKind === "blob" && activeBlobUrl ? (
                  <div className="flex min-h-[680px] items-center justify-center overflow-hidden rounded-[1.25rem] border border-[var(--border-default)] bg-white">
                    {activeFilePath && isImageFile(activeFilePath) ? (
                      // Blob URLs from project assets need direct browser rendering.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={activeBlobUrl}
                        alt={activeFilePath}
                        className="max-h-[660px] w-auto object-contain"
                      />
                    ) : (
                      <div className="px-6 text-center text-sm text-[var(--text-muted)]">
                        <FileImage className="mx-auto mb-3 h-8 w-8" />
                        该文件类型已加载，可通过浏览器直接预览或下载。
                      </div>
                    )}
                  </div>
                ) : (
                  <textarea
                    ref={editorRef}
                    value={activeFileContent}
                    onChange={(event) => setActiveFileContent(event.target.value)}
                    onSelect={(event) => {
                      const target = event.currentTarget;
                      const start = Math.min(target.selectionStart ?? 0, target.selectionEnd ?? 0);
                      const end = Math.max(target.selectionStart ?? 0, target.selectionEnd ?? 0);
                      setSelectionRange([start, end]);
                    }}
                    readOnly={!activeFilePath || !isTextFile(activeFilePath)}
                    className="min-h-[680px] w-full rounded-[1.25rem] border border-[var(--border-default)] bg-[rgba(244,240,232,0.55)] p-4 font-mono text-[13px] leading-6"
                  />
                )}
              </div>
            </div>
          </section>

          <section className="space-y-5">
            <div className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.95)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                PDF 预览
              </p>
              <div className="mt-4 overflow-hidden rounded-[1.25rem] border border-[var(--border-default)] bg-white">
                {compiledPdfUrl ? (
                  <LatexPdfPreview
                    pdfUrl={compiledPdfUrl}
                    feedbacks={pdfHighlightFeedbacks}
                    activeFeedbackId={activeFeedbackId}
                    transientSelectionAnchor={transientPdfAnchor}
                    transientSelectionText={selectionText}
                    onSelection={handlePdfSelection}
                    className="h-[78vh] min-h-[760px] w-full"
                  />
                ) : (
                  <div className="flex h-[78vh] min-h-[760px] items-center justify-center px-6 text-center text-sm text-[var(--text-muted)]">
                    还没有可预览的 PDF。先保存并编译当前项目。
                  </div>
                )}
              </div>
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                支持在 PDF 预览中直接划词，系统会自动尝试映射到当前 TeX 选区。
              </p>
              {compileResult?.error ? (
                <p className="mt-3 text-sm text-red-600">{compileResult.error}</p>
              ) : null}
            </div>

            <div className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.95)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  编译日志
                </p>
                <Button
                  variant="outline"
                  onClick={() => setIsCompileLogOpen(true)}
                  disabled={!canOpenCompileLog}
                >
                  查看后台详情
                </Button>
              </div>
              <p className="mt-3 text-sm text-[var(--text-muted)]">
                {compileResult
                  ? `最近一次编译：${compileResult.ok ? "成功" : "失败"} · ${compileResult.engine} · ${compileResult.main_file}`
                  : "当前还没有编译记录。"}
              </p>
            </div>
          </section>
        </div>
      </section>

      <Dialog open={isCompileLogOpen} onOpenChange={setIsCompileLogOpen}>
        <DialogContent className="max-h-[85vh] max-w-5xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>编译后台详情</DialogTitle>
            <DialogDescription>
              历史 ID：{compileResult?.history_id || "-"}
            </DialogDescription>
          </DialogHeader>
          {compileResult ? (
            <div className="grid gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-sm text-[var(--text-secondary)] md:grid-cols-2">
              <p>状态：{compileResult.ok ? "成功" : "失败"}</p>
              <p>编译器：{compileResult.engine}</p>
              <p>主文件：{compileResult.main_file}</p>
              <p>退出码：{compileResult.status}</p>
            </div>
          ) : null}
          <pre className="max-h-[56vh] overflow-auto rounded-xl bg-[rgba(19,34,53,0.05)] p-4 text-xs leading-6 text-[var(--text-secondary)]">
            {compileLog || compileResult?.error || "暂无日志"}
          </pre>
        </DialogContent>
      </Dialog>
    </main>
  );
}
