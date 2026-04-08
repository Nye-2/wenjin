"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, FileImage, Loader2, Trash2 } from "lucide-react";

import { LatexFileTree } from "@/components/latex/LatexFileTree";
import { LatexPdfPreview } from "@/components/latex/LatexPdfPreview";
import { LatexToolbar } from "@/components/latex/LatexToolbar";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import type { LatexFeedbackAnchor, LatexFeedbackItem, LatexPdfAnchor } from "@/lib/api";
import {
  getLatexProjectFeedback,
  mapLatexFeedbackSelection,
  rewriteLatexFeedback,
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
    if (candidateStarts.length >= 100) break;
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

export function LatexEditorShell({ projectId }: LatexEditorShellProps) {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const {
    project,
    tree,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    activeFileSavedContent,
    activeBlobUrl,
    syncConflicts,
    compileResult,
    compileLog,
    compiledPdfUrl,
    isProjectLoading,
    isFileLoading,
    isSaving,
    isCompiling,
    error,
    loadProject,
    openFile,
    setActiveFileContent,
    saveActiveFile,
    createFile,
    createFolder,
    renamePath,
    deletePath,
    saveOrder,
    uploadFiles,
    resolveConflict,
    deleteProject,
    compileProject,
  } = useLatexStore();
  const [engine, setEngine] = useState<"xelatex" | "pdflatex">("xelatex");
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
    void loadProject(projectId);
  }, [loadProject, projectId]);

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
    setPdfDraftSelection(null);
    setTransientPdfAnchor(null);
  }, [activeFilePath]);

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
          setFeedbackError(`加载点评失败: ${String(err)}`);
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
        setFeedbackError(`保存点评失败: ${String(err)}`);
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
      tex_anchor: anchor,
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
  }, [activeFeedbackId]);

  const rewriteFromFeedback = useCallback(async (item: LatexFeedbackItem) => {
    if (!project || activeFileKind !== "text") {
      setFeedbackError("当前文件不可执行点评改写。");
      return;
    }
    setFeedbackBusyId(item.id);
    setFeedbackError("");
    setFeedbackStatus("");
    try {
      const resolved = resolveFeedbackRange(item, activeFileContent);
      if (!resolved) {
        throw new Error("无法在当前文本中定位该点评原文。");
      }
      const response = await rewriteLatexFeedback(project.id, {
        file_path: item.file_path,
        selected_text: resolved.text,
        comment: item.comment,
        selection_start: resolved.start,
        selection_end: resolved.end,
        anchor: item.anchor || buildFeedbackAnchor(activeFileContent, resolved.start, resolved.end),
        scope: feedbackScope,
        file_content: activeFileContent,
        apply: false,
      });
      const nextContent = response.proposed_content;
      setActiveFileContent(nextContent);
      const nextStart = response.target_start;
      const nextEnd = response.target_start + response.rewritten_text.length;
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(nextStart, nextEnd);
      }
      setSelectionRange([nextStart, nextEnd]);
      setFeedbackItems((prev) =>
        shiftFeedbacksAfterRewrite(
          prev,
          item.file_path,
          item.id,
          response.target_start,
          response.target_end,
          response.rewritten_text,
          nextContent,
        ).map((entry) => (
          entry.id === item.id
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
      setActiveFeedbackId(item.id);
      setFeedbackStatus(
        response.scope === "section"
          ? `已按点评重写 section：${response.section_title}`
          : "已按点评重写选区。",
      );
    } catch (err) {
      setFeedbackError(`点评改写失败: ${String(err)}`);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: String(err) }
            : entry,
        ),
      );
    } finally {
      setFeedbackBusyId(null);
    }
  }, [activeFileContent, activeFileKind, feedbackScope, project, setActiveFileContent]);

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

  return (
    <main className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <Header />
      <section className="mx-auto max-w-[1500px] px-6 pb-10 pt-28">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => router.push("/latex")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回项目列表
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
                  router.push("/latex");
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
              isSaving={isSaving}
              isCompiling={isCompiling}
              disableActions={isProjectLoading}
              currentFolderLabel={currentFolder || "项目根目录"}
            />

            {syncConflicts.length > 0 ? (
              <div className="rounded-[1.5rem] border border-amber-500/25 bg-amber-500/10 p-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-700" />
                  <p className="text-sm font-medium text-amber-900">
                    检测到同步冲突
                  </p>
                </div>
                <p className="mt-2 text-xs leading-6 text-amber-900/80">
                  这些文件在 workspace 同步时因你已经手动修改而被保护性跳过。
                </p>
                <div className="mt-3 space-y-2">
                  {syncConflicts.map((conflict) => (
                    <div
                      key={`${conflict.logical_key}:${conflict.path}`}
                      className="flex items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-white/70 px-3 py-3"
                    >
                      <div>
                        <p className="text-xs font-medium text-[var(--text-primary)]">
                          {conflict.path}
                        </p>
                        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                          {conflict.reason}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => void resolveConflict(conflict.logical_key, "keep_current")}
                        disabled={isSaving}
                      >
                        保留当前版本
                      </Button>
                      <Button
                        onClick={() => void resolveConflict(conflict.logical_key, "accept_feature")}
                        disabled={isSaving}
                      >
                        接受工作区版本
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="rounded-[1.5rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.95)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  划词点评与改写
                </p>
                <div className="text-xs text-[var(--text-muted)]">
                  选中主稿文本后可直接点评
                </div>
              </div>
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
                                ? "待采纳"
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
                            disabled={feedbackBusyId === item.id}
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
