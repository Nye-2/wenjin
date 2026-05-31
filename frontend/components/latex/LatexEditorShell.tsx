"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Columns3,
  Eye,
  FileImage,
  FileText,
  Focus,
  Loader2,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { LatexRewritePreviewPanel } from "@/components/latex/latex-editor/LatexRewritePreviewPanel";
import {
  PrismMonacoEditor,
  type PrismTextEditorHandle,
} from "@/components/latex/latex-editor/PrismMonacoEditor";
import { PrismOptimizationTraceDialog } from "@/components/latex/latex-editor/PrismOptimizationTraceDialog";
import {
  buildFeedbackAnchor,
  createFeedbackId,
  parsePdfAnchor,
  resolveFeedbackRange,
  resolveSnippetRange,
  shiftFeedbacksAfterRewrite,
} from "@/components/latex/latex-editor/feedbackAnchors";
import {
  isImageFile,
  isTextFile,
} from "@/components/latex/latex-editor/fileKinds";
import {
  createPrismOptimizationJobId,
  jobStatusFromExecution,
  prismJobStatusLabel,
  TERMINAL_PRISM_EXECUTION_STATUSES,
  trimSnippet,
  type PrismOptimizationJob,
} from "@/components/latex/latex-editor/prismOptimizationJobs";
import {
  STALE_REWRITE_ERROR_CODES,
  STRUCTURE_REWRITE_ERROR_CODES,
} from "@/components/latex/latex-editor/rewriteDisplay";
import { LatexFileTree } from "@/components/latex/LatexFileTree";
import { LatexPdfPreview } from "@/components/latex/LatexPdfPreview";
import { LatexToolbar } from "@/components/latex/LatexToolbar";
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
  ExecutionRecord,
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
  readClientErrorCode,
  readClientErrorDetailField,
  readClientErrorMessage,
} from "@/components/latex/latex-editor/clientErrors";
import { listExecutions } from "@/lib/api/executions";
import { groupExecutionPhases } from "@/lib/execution-phases";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { useAuthStore } from "@/stores/auth";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";
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

type PrismSurfaceMode = "edit" | "compare" | "review" | "focus";
type PrismInspectorTab = "assist" | "review" | "compile" | "agent";

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
  const sendChatMessage = useChatStoreV2((state) => state.sendMessage);
  const isChatSending = useChatStoreV2((state) => state.isSending);
  const executions = useExecutionStore((state) => state.executions);
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);
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
  const [prismOptimizationJobs, setPrismOptimizationJobs] = useState<PrismOptimizationJob[]>([]);
  const [activePrismOptimizationJobId, setActivePrismOptimizationJobId] = useState<string | null>(null);
  const [isPrismOptimizationTraceOpen, setIsPrismOptimizationTraceOpen] = useState(false);
  const [surfaceMode, setSurfaceMode] = useState<PrismSurfaceMode>("edit");
  const [isInspectorOpen, setIsInspectorOpen] = useState(true);
  const [activeInspectorTab, setActiveInspectorTab] = useState<PrismInspectorTab>("assist");
  const editorRef = useRef<PrismTextEditorHandle | null>(null);
  const feedbackSaveTimerRef = useRef<number | null>(null);
  const texMapRequestSeqRef = useRef(0);
  const lastTexMapKeyRef = useRef("");
  const syncedPrismOptimizationExecutionsRef = useRef<Set<string>>(new Set());

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
  const containsCjkContent = /[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]/.test(activeFileContent);
  const engineHint =
    engine === "pdflatex" && containsCjkContent
      ? "当前稿件包含中文或 CJK 标点，请切回 XeLaTeX。PDFLaTeX 在当前运行时不适合作为中文稿件编译器。"
      : "中文或中英混排稿件默认使用 XeLaTeX。PDFLaTeX 主要用于英文模板兼容。";
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
  const hasFeedbackSelection = selectionText.trim().length > 0 || hasPdfDraftSelection;
  const canCreateFeedback = Boolean(
    feedbackDraftComment.trim()
    && hasFeedbackSelection,
  );
  const feedbackContextText = selectionText.trim()
    ? `当前 TeX 已选中 ${selectionText.length} 个字符。`
    : hasPdfDraftSelection
      ? `当前 PDF 已选中 ${pdfDraftSelection?.text.trim().length || 0} 个字符。`
      : "选择正文或 PDF 文本后添加点评，并交给 Agent 异步优化。";
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

  useEffect(() => {
    if (hasFeedbackSelection || feedbackDraftComment.trim()) {
      setActiveInspectorTab("assist");
      setIsInspectorOpen(true);
    }
  }, [feedbackDraftComment, hasFeedbackSelection]);

  useEffect(() => {
    if (fileChanges.length > 0) {
      setActiveInspectorTab("review");
      setIsInspectorOpen(true);
    }
  }, [fileChanges.length]);

  useEffect(() => {
    if (compileResult && !compileResult.ok) {
      setActiveInspectorTab("compile");
      setIsInspectorOpen(true);
    }
  }, [compileResult]);

  useEffect(() => {
    if (activePrismOptimizationJobId) {
      setActiveInspectorTab("agent");
      setIsInspectorOpen(true);
    }
  }, [activePrismOptimizationJobId]);

  const prismOptimizationExecutionIds = useMemo(
    () =>
      prismOptimizationJobs
        .map((job) => job.executionId?.trim())
        .filter((id): id is string => Boolean(id)),
    [prismOptimizationJobs],
  );
  const prismOptimizationExecutionIdKey = prismOptimizationExecutionIds.join("|");
  const activePrismOptimizationJob = useMemo(() => {
    if (!prismOptimizationJobs.length) {
      return null;
    }
    if (activePrismOptimizationJobId) {
      const active = prismOptimizationJobs.find((job) => job.id === activePrismOptimizationJobId);
      if (active) {
        return active;
      }
    }
    return prismOptimizationJobs[0];
  }, [activePrismOptimizationJobId, prismOptimizationJobs]);
  const activePrismOptimizationRecord = useMemo(() => {
    if (!activePrismOptimizationJob?.executionId) {
      return null;
    }
    return executions.get(activePrismOptimizationJob.executionId) ?? null;
  }, [activePrismOptimizationJob, executions]);
  const activePrismOptimizationPhases = useMemo(
    () => groupExecutionPhases(activePrismOptimizationRecord),
    [activePrismOptimizationRecord],
  );
  const prismOptimizationRecords = useMemo(
    () =>
      prismOptimizationJobs
        .map((job) => (job.executionId ? executions.get(job.executionId) : null))
        .filter((record): record is ExecutionRecord => Boolean(record)),
    [executions, prismOptimizationJobs],
  );
  const optimizingFeedbackIds = useMemo(() => {
    const ids = new Set<string>();
    for (const job of prismOptimizationJobs) {
      if (job.status === "launching" || job.status === "running") {
        ids.add(job.feedbackId);
      }
    }
    return ids;
  }, [prismOptimizationJobs]);
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
          title: change.title || `已写入稿件修改: ${change.path}`,
          reason: change.reason || "可撤回的写入记录",
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
    if (!workspaceId || prismOptimizationExecutionIds.length === 0) {
      return;
    }
    const expectedIds = new Set(prismOptimizationExecutionIds);
    let cancelled = false;
    const hydrate = () => {
      void listExecutions({ workspace_id: workspaceId, limit: 20 })
        .then(({ items }) => {
          if (cancelled) {
            return;
          }
          for (const item of items) {
            if (
              expectedIds.has(item.id) ||
              item.feature_id === "prism_selection_optimize"
            ) {
              upsertExecution(item);
            }
          }
        })
        .catch(() => {
          // The chat stream already launched the run; polling is best-effort for the small Prism trace.
        });
    };
    hydrate();
    const interval = window.setInterval(hydrate, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [
    prismOptimizationExecutionIdKey,
    prismOptimizationExecutionIds,
    upsertExecution,
    workspaceId,
  ]);

  useEffect(() => {
    if (!prismOptimizationJobs.length) {
      return;
    }
    setPrismOptimizationJobs((prev) => {
      let changed = false;
      const next = prev.map((job) => {
        const record = job.executionId ? executions.get(job.executionId) : null;
        const status = jobStatusFromExecution(record);
        if (!status || status === job.status) {
          return job;
        }
        changed = true;
        return { ...job, status };
      });
      return changed ? next : prev;
    });
  }, [executions, prismOptimizationJobs.length]);

  useEffect(() => {
    for (const record of prismOptimizationRecords) {
      if (
        !TERMINAL_PRISM_EXECUTION_STATUSES.has(record.status) ||
        syncedPrismOptimizationExecutionsRef.current.has(record.id)
      ) {
        continue;
      }
      syncedPrismOptimizationExecutionsRef.current.add(record.id);
      if (jobStatusFromExecution(record) === "completed") {
        void loadProject(projectId)
          .then(() => {
            onReviewStateChanged?.();
            setFeedbackStatus("Agent 已生成待确认修改，请在 Prism 待确认写入中预览并应用。");
          })
          .catch(() => {
            setFeedbackStatus("Agent 已完成优化，请刷新后查看 Prism 待确认写入。");
          });
      }
    }
  }, [loadProject, onReviewStateChanged, prismOptimizationRecords, projectId]);

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

  const launchPrismOptimizationFromFeedback = useCallback(async (item: LatexFeedbackItem) => {
    const effectiveWorkspaceId = workspaceId || project?.workspace_id || "";
    if (!effectiveWorkspaceId) {
      setFeedbackError("当前 Prism 项目尚未关联 workspace，无法启动 Agent 优化。");
      return;
    }
    if (!project) {
      setFeedbackError("项目尚未加载完成。");
      return;
    }
    if (isChatSending) {
      setFeedbackError("左侧 Chat Agent 正在处理消息，请稍后再启动划词优化。");
      return;
    }

    setFeedbackBusyId(item.id);
    setFeedbackError("");
    setFeedbackStatus("正在把划词优化交给右侧 Lead Agent。");
    try {
      if (activeFilePath !== item.file_path) {
        setSelectedPath(item.file_path);
        setSelectedPathType("file");
        await openFile(item.file_path);
      }

      let latexState = useLatexStore.getState();
      if (latexState.activeFileKind !== "text" || !latexState.activeFilePath) {
        throw new Error("当前文件不可执行 Prism 划词优化。");
      }
      if (latexState.activeFileContent !== latexState.activeFileSavedContent) {
        await saveActiveFile();
        latexState = useLatexStore.getState();
      }

      const launchContent = latexState.activeFileContent;
      const resolved = resolveFeedbackRange(item, launchContent);
      if (!resolved) {
        throw new Error("无法在当前文本中定位该点评原文。");
      }
      const anchor = item.anchor || buildFeedbackAnchor(launchContent, resolved.start, resolved.end);
      const jobId = createPrismOptimizationJobId();
      const job: PrismOptimizationJob = {
        id: jobId,
        feedbackId: item.id,
        status: "launching",
        filePath: item.file_path,
        scope: feedbackScope,
        instruction: item.comment,
        selectedText: resolved.text,
        createdAt: new Date().toISOString(),
      };
      setPrismOptimizationJobs((prev) => [job, ...prev].slice(0, 8));
      setActivePrismOptimizationJobId(jobId);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "pending", last_error: "" }
            : entry,
        ),
      );

      const prompt = [
        "请启动「Prism 划词优化」能力（prism_selection_optimize）。",
        `目标文件：${item.file_path}`,
        `优化范围：${feedbackScope === "section" ? "所在 section" : "仅选区"}`,
        "用户指令：",
        item.comment,
        "请由右侧 Lead Agent 异步处理，生成 Prism 待确认写入，不要直接覆盖正文。",
      ].join("\n");
      const result = await sendChatMessage(effectiveWorkspaceId, prompt, [], {
        metadata: {
          prism_selection_optimize: {
            job_id: jobId,
            feedback_id: item.id,
            latex_project_id: project.id,
            file_path: item.file_path,
          },
          orchestration: {
            params: {
              goal: "Prism 划词优化",
              source_surface: "prism",
              latex_project_id: project.id,
              main_file: project.main_file,
              file_path: item.file_path,
              file_content: launchContent,
              selected_text: resolved.text,
              instruction: item.comment,
              comment: item.comment,
              selection_start: resolved.start,
              selection_end: resolved.end,
              anchor,
              pdf_anchor: item.pdf_anchor || null,
              scope: feedbackScope,
              feedback_id: item.id,
            },
          },
        },
      });

      if (result?.executionId) {
        setPrismOptimizationJobs((prev) =>
          prev.map((entry) =>
            entry.id === jobId
              ? { ...entry, executionId: result.executionId, status: "running" }
              : entry,
          ),
        );
        setFeedbackStatus("Agent 优化已启动，右下角可查看工作过程。");
        return;
      }

      const detail =
        typeof result?.toolResult?.detail === "string" && result.toolResult.detail.trim()
          ? result.toolResult.detail.trim()
          : "未能启动 Prism 划词优化，请稍后重试。";
      setPrismOptimizationJobs((prev) =>
        prev.map((entry) =>
          entry.id === jobId
            ? { ...entry, status: result?.status === "advisory" ? "advisory" : "failed", error: detail }
            : entry,
        ),
      );
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: detail }
            : entry,
        ),
      );
      setFeedbackError(detail);
    } catch (err) {
      const message = readClientErrorMessage(err);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
      setFeedbackError(`启动 Agent 优化失败: ${message}`);
    } finally {
      setFeedbackBusyId(null);
    }
  }, [
    activeFilePath,
    feedbackScope,
    isChatSending,
    openFile,
    project,
    saveActiveFile,
    sendChatMessage,
    workspaceId,
  ]);

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
    await launchPrismOptimizationFromFeedback(item);
  }, [createFeedbackFromSelection, launchPrismOptimizationFromFeedback]);

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

  const surfaceModeOptions: Array<{
    id: PrismSurfaceMode;
    label: string;
    icon: typeof FileText;
  }> = [
    { id: "edit", label: "编辑", icon: FileText },
    { id: "compare", label: "对照", icon: Columns3 },
    { id: "review", label: "审阅", icon: Eye },
    { id: "focus", label: "专注", icon: Focus },
  ];

  const inspectorTabs: Array<{
    id: PrismInspectorTab;
    label: string;
    badge?: number;
  }> = [
    { id: "assist", label: "划词", badge: currentFileFeedbacks.length || undefined },
    { id: "review", label: "审阅", badge: fileChanges.length || undefined },
    { id: "compile", label: "编译" },
    { id: "agent", label: "Agent", badge: prismOptimizationJobs.length || undefined },
  ];

  const openInspector = (tab: PrismInspectorTab) => {
    setActiveInspectorTab(tab);
    setIsInspectorOpen(true);
  };

  const renderProjectBar = () => (
    <div className="wjn-topbar flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-3 px-3 py-2 md:px-4">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push(workspaceId ? `/workspaces/${workspaceId}` : "/workspaces")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {workspaceId ? "Workbench" : "工作区"}
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-sm font-semibold text-[var(--wjn-text)]">
              {project?.name || "加载项目中..."}
            </h1>
            <span className="rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white px-2 py-0.5 text-[11px] text-[var(--wjn-text-muted)]">
              {dirty ? "未保存" : "已保存"}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--wjn-text-muted)]">
            主文件 {project?.main_file || "main.tex"} · {activeFilePath || "未选择文件"}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <select
          value={engine}
          onChange={(event) => setEngine(event.target.value as LatexCompileEngine)}
          className="h-9 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white px-2 text-xs"
        >
          <option value="xelatex">XeLaTeX</option>
          <option value="pdflatex">PDFLaTeX</option>
        </select>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void saveActiveFile()}
          disabled={isProjectLoading || isSaving || activeFileKind !== "text"}
        >
          {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          保存
        </Button>
        <Button
          size="sm"
          onClick={() => void compileProject(engine)}
          disabled={isProjectLoading || isCompiling || isSaving}
        >
          {isCompiling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
          {isCompiling ? "编译中" : "编译"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setIsInspectorOpen((prev) => !prev)}
        >
          {isInspectorOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );

  const renderResourceRail = () => (
    <aside className="hidden w-[260px] shrink-0 flex-col border-r border-[var(--wjn-line)] bg-[var(--wjn-bg-rail)] lg:flex">
      <div className="flex h-12 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <p className="text-xs font-semibold text-[var(--wjn-text-secondary)]">资源</p>
        <span className="text-[11px] text-[var(--wjn-text-muted)]">
          {tree.length} 项
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">
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
      <div className="border-t border-[var(--wjn-line)] p-2">
        <details>
          <summary className="cursor-pointer rounded-[var(--wjn-radius)] px-2 py-1 text-xs text-[var(--wjn-text-muted)] hover:bg-white">
            文件操作
          </summary>
          <div className="mt-2">
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
              engineHint={engineHint}
            />
          </div>
        </details>
        <Button
          variant="destructive"
          size="sm"
          className="mt-2 w-full"
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
    </aside>
  );

  const renderEditorPanel = () => (
    <div className="relative flex h-full min-h-0 flex-1 flex-col border border-[var(--wjn-line)] bg-white">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate text-sm font-medium text-[var(--text-primary)]">
            <span className="truncate">{activeFilePath || "未选择文件"}</span>
            {isFileLoading ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[var(--text-muted)]" />
            ) : null}
          </p>
          <p className="text-[11px] text-[var(--text-muted)]">
            {activeFileKind === "blob"
              ? "预览文件"
              : dirty
                ? "存在未保存修改"
                : "内容已同步"}
          </p>
        </div>
        {hasFeedbackSelection ? (
          <div className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-2 py-1 shadow-sm">
            <span className="text-[11px] text-[var(--text-muted)]">
              已选 {selectionText.trim() ? selectionText.length : pdfDraftSelection?.text.trim().length || 0} 字
            </span>
            <Button size="sm" variant="outline" onClick={() => openInspector("assist")}>
              <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
              点评
            </Button>
            <Button size="sm" onClick={() => openInspector("assist")}>
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              优化
            </Button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setSurfaceMode("compare");
              setIsInspectorOpen(false);
            }}
            className="rounded-md px-2 py-1 text-xs text-[var(--text-muted)] hover:bg-[rgba(15,23,42,0.04)]"
          >
            PDF 默认收起，可切换到对照查看
          </button>
        )}
      </div>

      {activeFileKind === "blob" && activeBlobUrl ? (
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-white">
          {activeFilePath && isImageFile(activeFilePath) ? (
            // Blob URLs from project assets need direct browser rendering.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={activeBlobUrl}
              alt={activeFilePath}
              className="max-h-full w-auto object-contain"
            />
          ) : (
            <div className="px-6 text-center text-sm text-[var(--text-muted)]">
              <FileImage className="mx-auto mb-3 h-8 w-8" />
              该文件类型已加载，可通过浏览器直接预览或下载。
            </div>
          )}
        </div>
      ) : (
        <div className="h-full min-h-0 flex-1">
          <PrismMonacoEditor
            ref={editorRef}
            path={activeFilePath}
            value={activeFileContent}
            onChange={setActiveFileContent}
            onSelect={setSelectionRange}
            readOnly={!activeFilePath || !isTextFile(activeFilePath)}
          />
        </div>
      )}
    </div>
  );

  const renderPdfPanel = () => (
    <div className="flex min-h-0 flex-1 flex-col border border-[var(--wjn-line)] bg-white">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <div>
          <p className="text-sm font-medium">PDF 对照</p>
          <p className="text-[11px] text-[var(--text-muted)]">
            可在 PDF 中划词，系统会映射回 TeX
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setSurfaceMode("edit")}>
          收起 PDF
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden bg-white">
        {compiledPdfUrl ? (
          <LatexPdfPreview
            pdfUrl={compiledPdfUrl}
            feedbacks={pdfHighlightFeedbacks}
            activeFeedbackId={activeFeedbackId}
            transientSelectionAnchor={transientPdfAnchor}
            transientSelectionText={selectionText}
            onSelection={handlePdfSelection}
            className="h-full min-h-[520px] w-full"
          />
        ) : isCompiling ? (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 px-6 text-center text-sm text-[var(--text-muted)]">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在使用 {engine} 编译当前项目...
          </div>
        ) : compileResult && !compileResult.ok ? (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center px-6 text-center">
            <p className="text-sm font-medium text-red-600">编译失败</p>
            <p className="mt-2 max-w-sm text-xs leading-6 text-[var(--text-muted)]">
              {compileResult.error || "没有生成 PDF。打开编译日志查看 LaTeX 输出。"}
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => {
                openInspector("compile");
                setIsCompileLogOpen(true);
              }}
            >
              查看编译日志
            </Button>
          </div>
        ) : (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 px-6 text-center text-sm text-[var(--text-muted)]">
            还没有可预览的 PDF。先保存并编译当前项目。
            <Button size="sm" onClick={() => void compileProject(engine)} disabled={isCompiling || isSaving}>
              编译生成 PDF
            </Button>
          </div>
        )}
      </div>
    </div>
  );

  const renderWritingSurface = () => (
    <section className="flex min-w-0 flex-1 flex-col bg-[var(--wjn-bg-base)]">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] bg-white px-3">
        <div className="inline-flex rounded-[10px] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-0.5">
          {surfaceModeOptions.map((option) => {
            const Icon = option.icon;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  setSurfaceMode(option.id);
                  if (option.id === "review") {
                    openInspector("review");
                  } else if (option.id === "compare" || option.id === "focus") {
                    setIsInspectorOpen(false);
                  }
                }}
                className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs ${
                  surfaceMode === option.id
                    ? "bg-white text-[var(--wjn-text)] shadow-sm"
                    : "text-[var(--wjn-text-muted)] hover:text-[var(--wjn-text)]"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {option.label}
              </button>
            );
          })}
        </div>
        <p className="hidden text-xs text-[var(--wjn-text-muted)] md:block">
          {surfaceMode === "compare"
            ? "正在显示 PDF 对照"
            : "PDF 默认不展开，可切换到“对照”查看"}
        </p>
      </div>
      <div className="flex min-h-0 flex-1 p-3">
        {surfaceMode === "compare" ? (
          <ResizablePanelGroup orientation="horizontal" className="h-full min-h-0 gap-3">
            <ResizablePanel id="prism-editor-panel" defaultSize={56} minSize={36}>
              {renderEditorPanel()}
            </ResizablePanel>
            <ResizableHandle withHandle className="bg-transparent" />
            <ResizablePanel id="prism-pdf-panel" defaultSize={44} minSize={28}>
              {renderPdfPanel()}
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          renderEditorPanel()
        )}
      </div>
    </section>
  );

  const renderFeedbackInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">划词点评与 Agent 优化</p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">{feedbackContextText}</p>
      </div>
      <textarea
        value={feedbackDraftComment}
        onChange={(event) => setFeedbackDraftComment(event.target.value)}
        placeholder="例如：这一段贡献点不够清晰，请加强问题定义和定量结论。"
        className="min-h-[112px] w-full resize-none rounded-lg border border-[var(--border-default)] bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-[var(--v2-accent-purple-300)]"
      />
      <div className="grid gap-2">
        <label className="text-xs text-[var(--text-muted)]">优化范围</label>
        <select
          value={feedbackScope}
          onChange={(event) => setFeedbackScope(event.target.value as "selection" | "section")}
          className="h-9 rounded-lg border border-[var(--border-default)] bg-white px-2 text-sm"
        >
          <option value="section">重写所在 section</option>
          <option value="selection">仅重写选区</option>
        </select>
      </div>
      <div className="grid gap-2">
        <Button
          disabled={!canCreateFeedback || isSaving || isChatSending || Boolean(feedbackBusyId)}
          onClick={() => void addFeedbackAndRewrite()}
        >
          {feedbackBusyId ? "提交中..." : "交给 Agent 优化"}
        </Button>
        <Button
          variant="outline"
          disabled={!canCreateFeedback || isSaving}
          onClick={addFeedbackOnly}
        >
          只保存点评
        </Button>
        <Button
          variant="outline"
          onClick={() => void protectActiveFile()}
          disabled={isProtectingActiveFile || !activeFilePath || activeFileKind !== "text"}
        >
          <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
          {isProtectingActiveFile ? "保护中..." : "保护当前文件"}
        </Button>
      </div>
      {feedbackError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {feedbackError}
        </div>
      ) : null}
      {feedbackStatus ? (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
          {feedbackStatus}
        </div>
      ) : null}
      {protectionStatus ? (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
          {protectionStatus}
        </div>
      ) : null}
      {protectionError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {protectionError}
        </div>
      ) : null}
      {lastRewriteUndo ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border-default)] bg-white px-3 py-2">
          <p className="text-xs text-[var(--text-muted)]">可撤销最近一次本地改写。</p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void undoLastRewrite()}
            disabled={isApplyingRewrite || isSaving}
          >
            {isApplyingRewrite ? "处理中..." : "撤销"}
          </Button>
        </div>
      ) : null}
      <LatexRewritePreviewPanel
        selectedRewriteCandidate={selectedRewriteCandidate}
        selectedRewriteCandidateIndex={selectedRewriteCandidateIndex}
        rewriteCandidates={rewriteCandidates}
        diffViewMode={diffViewMode}
        showWhitespaceOnlyDiff={showWhitespaceOnlyDiff}
        collapsedDiffHunks={collapsedDiffHunks}
        previewFeedbackItem={previewFeedbackItem}
        feedbackBusyId={feedbackBusyId}
        isApplyingRewrite={isApplyingRewrite}
        isSaving={isSaving}
        onSelectCandidate={setSelectedRewriteCandidateId}
        onRegenerate={() => void regenerateRewritePreview()}
        onDiffViewModeChange={setDiffViewMode}
        onToggleWhitespaceOnlyDiff={() => setShowWhitespaceOnlyDiff((prev) => !prev)}
        onCollapseAll={setAllDiffHunksCollapsed}
        onToggleHunkCollapsed={toggleDiffHunkCollapsed}
        onCopy={() => void copySelectedRewrite()}
        onCancel={() => clearRewritePreview()}
        onApply={() => void applyRewriteCandidate()}
      />
      <div className="border-t border-[rgba(15,23,42,0.08)] pt-3">
        <p className="mb-2 text-xs font-semibold text-[var(--text-muted)]">
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
                className={`rounded-lg border px-3 py-2 ${
                  activeFeedbackId === item.id
                    ? "border-[var(--v2-accent-purple-300)] bg-[rgba(124,92,255,0.08)]"
                    : "border-[var(--border-default)] bg-white"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-medium">点评 #{index + 1}</p>
                  <div className="text-[11px] text-[var(--text-muted)]">
                    {item.last_status === "error"
                      ? "失败"
                      : item.last_status === "pending"
                        ? "处理中"
                        : item.last_status === "done"
                          ? "已采纳"
                          : "已保存"}
                  </div>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">
                  {item.selected_text}
                </p>
                <p className="mt-1 text-sm leading-5">{item.comment}</p>
                {item.last_error ? (
                  <p className="mt-1 text-xs text-red-600">{item.last_error}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => focusFeedback(item)}>
                    定位
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void rewriteFromFeedback(item)}
                    disabled={feedbackBusyId === item.id || isApplyingRewrite}
                  >
                    {feedbackBusyId === item.id ? "生成中..." : "生成 diff"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void launchPrismOptimizationFromFeedback(item)}
                    disabled={
                      feedbackBusyId === item.id ||
                      isApplyingRewrite ||
                      isChatSending ||
                      optimizingFeedbackIds.has(item.id)
                    }
                  >
                    {feedbackBusyId === item.id || optimizingFeedbackIds.has(item.id)
                      ? "优化中..."
                      : "Agent 优化"}
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
  );

  const renderReviewInspector = () => (
    <div ref={fileChangesRef} className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          {fileChanges.length > 0 ? (
            <AlertTriangle className="h-4 w-4 text-amber-700" />
          ) : null}
          <p className="text-sm font-medium">Prism 审阅</p>
        </div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          待确认写入会先预览 diff，再由你决定是否应用。
        </p>
      </div>
      {fileChangeError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {fileChangeError}
        </div>
      ) : null}
      {fileChanges.length > 0 ? (
        <PrismReviewList
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
                  onClick={() => void discardPendingFileChange(change)}
                  disabled={isBusy}
                >
                  忽略
                </Button>
                <Button
                  size="sm"
                  onClick={() => void applyPendingFileChange(change)}
                  disabled={isBusy}
                >
                  应用
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
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-default)] bg-white px-3 py-6 text-center text-xs text-[var(--text-muted)]">
          暂无待确认写入。
        </div>
      )}
      {appliedFileChanges.length > 0 ? (
        <div className="border-t border-[rgba(15,23,42,0.08)] pt-3">
          <p className="mb-2 text-xs font-semibold text-[var(--text-muted)]">已写入变更</p>
          <PrismReviewList
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
                  {busyFileChangeKey === change.logical_key ? "撤回中..." : "撤回"}
                </Button>
              );
            }}
          />
        </div>
      ) : null}
    </div>
  );

  const renderCompileInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">编译状态</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">{engineHint}</p>
      </div>
      <div className="rounded-lg border border-[var(--border-default)] bg-white px-3 py-3 text-sm text-[var(--text-secondary)]">
        {isCompiling
          ? `正在编译：${engine} · ${project?.main_file || "main.tex"}`
          : compileResult
            ? `最近一次编译：${compileResult.ok ? "成功" : "失败"} · ${compileResult.engine} · ${compileResult.main_file}`
            : "当前还没有编译记录。"}
      </div>
      <Button
        variant="outline"
        onClick={() => setIsCompileLogOpen(true)}
        disabled={!canOpenCompileLog}
        className="w-full"
      >
        查看后台详情
      </Button>
      {compileResult?.error ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-700">
          {compileResult.error}
        </div>
      ) : null}
    </div>
  );

  const renderAgentInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Agent 任务</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Prism 内只展示轻量过程，完整运行记录在 Workbench。
        </p>
      </div>
      {activePrismOptimizationJob ? (
        <div className="rounded-lg border border-[var(--border-default)] bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {prismJobStatusLabel(activePrismOptimizationJob.status)}
            </p>
            <span className="rounded-full bg-[rgba(124,92,255,0.1)] px-2 py-0.5 text-[11px] text-[var(--v2-accent-purple-700)]">
              {activePrismOptimizationJob.scope === "section" ? "section" : "selection"}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">
            {trimSnippet(activePrismOptimizationJob.selectedText, 180)}
          </p>
          <Button
            className="mt-3 w-full"
            size="sm"
            onClick={() => setIsPrismOptimizationTraceOpen(true)}
          >
            查看工作过程
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-default)] bg-white px-3 py-6 text-center text-xs text-[var(--text-muted)]">
          当前没有 Prism 内任务。
        </div>
      )}
    </div>
  );

  const renderInspector = () => {
    if (!isInspectorOpen || surfaceMode === "focus") {
      return null;
    }
    return (
      <aside className="fixed inset-x-3 bottom-3 z-30 flex max-h-[72vh] flex-col rounded-xl border border-[var(--wjn-line-strong)] bg-[var(--wjn-bg-rail)] shadow-2xl xl:static xl:inset-auto xl:z-auto xl:max-h-none xl:w-[360px] xl:shrink-0 xl:rounded-none xl:border-y-0 xl:border-r-0 xl:shadow-none">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
          <div className="inline-flex rounded-[10px] border border-[var(--wjn-line)] bg-white p-0.5">
            {inspectorTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveInspectorTab(tab.id)}
                className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs ${
                  activeInspectorTab === tab.id
                    ? "bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text)]"
                    : "text-[var(--wjn-text-muted)]"
                }`}
              >
                {tab.label}
                {tab.badge ? (
                  <span className="rounded-full bg-white px-1.5 text-[10px]">{tab.badge}</span>
                ) : null}
              </button>
            ))}
          </div>
          <Button size="sm" variant="outline" onClick={() => setIsInspectorOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          {activeInspectorTab === "assist"
            ? renderFeedbackInspector()
            : activeInspectorTab === "review"
              ? renderReviewInspector()
              : activeInspectorTab === "compile"
                ? renderCompileInspector()
                : renderAgentInspector()}
        </div>
      </aside>
    );
  };

  const renderPrismWorkspace = () => (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      {surfaceMode !== "focus" ? renderResourceRail() : null}
      {renderWritingSurface()}
      {renderInspector()}
    </div>
  );

  return (
    <main className="wjn-shell-bg flex h-full min-h-0 flex-col overflow-hidden text-[var(--wjn-text)]">
      {renderProjectBar()}
      {error ? (
        <div className="border-b border-red-500/20 bg-red-500/8 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      ) : null}
      {renderPrismWorkspace()}

      <PrismOptimizationTraceDialog
        open={isPrismOptimizationTraceOpen}
        activeJob={activePrismOptimizationJob}
        jobs={prismOptimizationJobs}
        activeRecord={activePrismOptimizationRecord}
        activePhases={activePrismOptimizationPhases}
        fileChangesCount={fileChanges.length}
        onOpenChange={setIsPrismOptimizationTraceOpen}
        onSelectJob={setActivePrismOptimizationJobId}
        onViewPendingChanges={() => {
          fileChangesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          setIsPrismOptimizationTraceOpen(false);
        }}
      />

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
