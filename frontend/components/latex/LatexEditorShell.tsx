"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { LatexCompileLogDialog } from "@/components/latex/latex-editor/LatexCompileLogDialog";
import { LatexEditorPanes } from "@/components/latex/latex-editor/LatexEditorPanes";
import { LatexEditorProjectBar } from "@/components/latex/latex-editor/LatexEditorProjectBar";
import { LatexInspector } from "@/components/latex/latex-editor/LatexInspector";
import { LatexResourceRail } from "@/components/latex/latex-editor/LatexResourceRail";
import {
  type PrismTextEditorHandle,
} from "@/components/latex/latex-editor/PrismMonacoEditor";
import { PrismOptimizationTraceDialog } from "@/components/latex/latex-editor/PrismOptimizationTraceDialog";
import {
  buildFeedbackAnchor,
  parsePdfAnchor,
  resolveFeedbackRange,
  shiftFeedbacksAfterRewrite,
} from "@/components/latex/latex-editor/feedbackAnchors";
import {
  createPrismOptimizationJobId,
  type PrismOptimizationJob,
} from "@/components/latex/latex-editor/prismOptimizationJobs";
import {
  STALE_REWRITE_ERROR_CODES,
  STRUCTURE_REWRITE_ERROR_CODES,
} from "@/components/latex/latex-editor/rewriteDisplay";
import {
  type LastRewriteUndoState,
  type PrismInspectorTab,
  type PrismSurfaceMode,
} from "@/components/latex/latex-editor/types";
import { usePrismOptimizationJobs } from "@/components/latex/latex-editor/usePrismOptimizationJobs";
import { usePrismReviewQueue } from "@/components/latex/latex-editor/usePrismReviewQueue";
import { useLatexFeedbackPersistence } from "@/components/latex/latex-editor/useLatexFeedbackPersistence";
import { useLatexPdfSelectionMapping } from "@/components/latex/latex-editor/useLatexPdfSelectionMapping";
import { useLatexFeedbackCreation } from "@/components/latex/latex-editor/useLatexFeedbackCreation";
import type {
  LatexCompileEngine,
  LatexAppliedFileChange,
  LatexFeedbackItem,
  LatexFeedbackRewriteCandidate,
  LatexFileChange,
} from "@/lib/api";
import {
  applyLatexFeedbackRewrite,
  previewLatexFeedbackRewrite,
  protectLatexSection,
  revertLatexFeedbackRewrite,
} from "@/lib/api";
import {
  readClientErrorCode,
  readClientErrorDetailField,
  readClientErrorMessage,
} from "@/components/latex/latex-editor/clientErrors";
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

export function LatexEditorShell({
  projectId,
  workspaceId,
  initialFileChanges,
  initialAppliedFileChanges,
  onReviewStateChanged,
}: LatexEditorShellProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
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
  const [feedbackDraftComment, setFeedbackDraftComment] = useState("");
  const [feedbackScope, setFeedbackScope] = useState<"selection" | "section">("section");
  const [activeFeedbackId, setActiveFeedbackId] = useState<string | null>(null);
  const [feedbackBusyId, setFeedbackBusyId] = useState<string | null>(null);
  const [rewritePreviewFilePath, setRewritePreviewFilePath] = useState<string | null>(null);
  const [rewritePreviewFeedbackId, setRewritePreviewFeedbackId] = useState<string | null>(null);
  const [rewriteCandidates, setRewriteCandidates] = useState<LatexFeedbackRewriteCandidate[]>([]);
  const [selectedRewriteCandidateId, setSelectedRewriteCandidateId] = useState<string | null>(null);
  const [diffViewMode, setDiffViewMode] = useState<"inline" | "side-by-side">("inline");
  const [showWhitespaceOnlyDiff, setShowWhitespaceOnlyDiff] = useState(false);
  const [collapsedDiffHunks, setCollapsedDiffHunks] = useState<Record<string, boolean>>({});
  const [isApplyingRewrite, setIsApplyingRewrite] = useState(false);
  const [lastRewriteUndo, setLastRewriteUndo] = useState<LastRewriteUndoState | null>(null);
  const [isProtectingActiveFile, setIsProtectingActiveFile] = useState(false);
  const [protectionStatus, setProtectionStatus] = useState("");
  const [protectionError, setProtectionError] = useState("");
  const [surfaceMode, setSurfaceMode] = useState<PrismSurfaceMode>("edit");
  const [isInspectorOpen, setIsInspectorOpen] = useState(true);
  const [activeInspectorTab, setActiveInspectorTab] = useState<PrismInspectorTab>("assist");
  const editorRef = useRef<PrismTextEditorHandle | null>(null);
  const {
    feedbackItems,
    feedbackLoaded,
    feedbackStatus,
    feedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setFeedbackError,
  } = useLatexFeedbackPersistence(projectId);

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
  const pdfSelection = useLatexPdfSelectionMapping({
    projectId,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    compiledPdfUrl,
    compileHistoryId: compileResult?.history_id,
    selectionRange,
    selectionText,
    editorRef,
    openFile,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
    setFeedbackStatus,
    setFeedbackError,
  });
  const {
    pdfDraftSelection,
    transientPdfAnchor,
    setPdfDraftSelection,
    setTransientPdfAnchor,
    handlePdfSelection,
  } = pdfSelection;
  const createFeedbackFromSelection = useLatexFeedbackCreation({
    projectId,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    compileHistoryId: compileResult?.history_id,
    feedbackDraftComment,
    pdfDraftSelection,
    transientPdfAnchor,
    selectionRange,
    editorRef,
    openFile,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
    setTransientPdfAnchor,
    setFeedbackStatus,
    setFeedbackError,
  });
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

  const prismOptimization = usePrismOptimizationJobs({
    workspaceId,
    projectId,
    executions,
    upsertExecution,
    loadProject,
    onReviewStateChanged,
    onFeedbackStatus: setFeedbackStatus,
  });

  const reviewQueue = usePrismReviewQueue({
    projectId,
    project,
    activeFilePath,
    fileChanges,
    appliedFileChanges,
    searchParams,
    openFile,
    applyFileChange,
    discardFileChange,
    revertFileChange,
    onReviewStateChanged,
  });

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
    if (prismOptimization.activeJobId) {
      setActiveInspectorTab("agent");
      setIsInspectorOpen(true);
    }
  }, [prismOptimization.activeJobId]);
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
  }, [rewritePreviewFeedbackId, setFeedbackItems]);

  useEffect(() => {
    setCollapsedDiffHunks({});
  }, [selectedRewriteCandidateId, rewritePreviewFeedbackId]);

  useEffect(() => {
    setSelectionRange([0, 0]);
    setFeedbackDraftComment("");
    setActiveFeedbackId(null);
    setFeedbackBusyId(null);
    clearRewritePreview();
  }, [activeFilePath, clearRewritePreview]);

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
  }, [
    createFeedbackFromSelection,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setPdfDraftSelection,
  ]);

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
  }, [activeFileContent, activeFileKind, setFeedbackError, setTransientPdfAnchor]);

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
  }, [
    activeFeedbackId,
    clearRewritePreview,
    lastRewriteUndo,
    rewritePreviewFeedbackId,
    setFeedbackItems,
  ]);

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
      prismOptimization.addJob(job);
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
        prismOptimization.updateJob(
          jobId,
          (entry) => ({ ...entry, executionId: result.executionId, status: "running" }),
        );
        setFeedbackStatus("Agent 优化已启动，右下角可查看工作过程。");
        return;
      }

      const detail =
        typeof result?.toolResult?.detail === "string" && result.toolResult.detail.trim()
          ? result.toolResult.detail.trim()
          : "未能启动 Prism 划词优化，请稍后重试。";
      prismOptimization.updateJob(
        jobId,
        (entry) => ({
          ...entry,
          status: result?.status === "advisory" ? "advisory" : "failed",
          error: detail,
        }),
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
    prismOptimization,
    saveActiveFile,
    sendChatMessage,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
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
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
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
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
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
  }, [selectedRewriteCandidate, setFeedbackError, setFeedbackStatus]);

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
  }, [
    activeFilePath,
    lastRewriteUndo,
    openFile,
    project,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
  ]);

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
  }, [
    createFeedbackFromSelection,
    launchPrismOptimizationFromFeedback,
    setFeedbackItems,
    setPdfDraftSelection,
  ]);

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

  const deleteCurrentProject = useCallback(async () => {
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
  }, [deleteProject, project, router, workspaceId]);

  const inspectorTabs: Array<{
    id: PrismInspectorTab;
    label: string;
    badge?: number;
  }> = [
    { id: "assist", label: "划词", badge: currentFileFeedbacks.length || undefined },
    { id: "review", label: "审阅", badge: fileChanges.length || undefined },
    { id: "compile", label: "编译" },
    { id: "agent", label: "Agent", badge: prismOptimization.jobs.length || undefined },
  ];

  const openInspector = useCallback((tab: PrismInspectorTab) => {
    setActiveInspectorTab(tab);
    setIsInspectorOpen(true);
  }, []);

  return (
    <main className="wjn-shell-bg flex h-full min-h-0 flex-col overflow-hidden text-[var(--wjn-text)]">
      <LatexEditorProjectBar
        projectName={project?.name}
        mainFile={project?.main_file}
        activeFilePath={activeFilePath}
        dirty={dirty}
        engine={engine}
        isProjectLoading={isProjectLoading}
        isSaving={isSaving}
        isCompiling={isCompiling}
        activeFileKind={activeFileKind}
        isInspectorOpen={isInspectorOpen}
        backLabel={workspaceId ? "Workbench" : "工作区"}
        onBack={() => router.push(workspaceId ? `/workspaces/${workspaceId}` : "/workspaces")}
        onEngineChange={setEngine}
        onSave={() => void saveActiveFile()}
        onCompile={() => void compileProject(engine)}
        onToggleInspector={() => setIsInspectorOpen((prev) => !prev)}
      />
      {error ? (
        <div className="border-b border-red-500/20 bg-red-500/8 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      ) : null}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {surfaceMode !== "focus" ? (
          <LatexResourceRail
            tree={tree}
            selectedPath={effectiveSelectedPath}
            engine={engine}
            isSaving={isSaving}
            isCompiling={isCompiling}
            isProjectLoading={isProjectLoading}
            isDeletingProject={isDeletingProject}
            projectName={project?.name}
            currentFolderLabel={currentFolder || "项目根目录"}
            engineHint={engineHint}
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
            onEngineChange={setEngine}
            onSave={() => void saveActiveFile()}
            onCompile={() => void compileProject(engine)}
            onCreateFile={(path) => createFile(path)}
            onCreateFolder={(path) => createFolder(path)}
            onUploadFiles={(files) => uploadFiles(files, currentFolder || undefined)}
            onUploadDirectory={(files) => uploadDirectory(files, currentFolder || undefined)}
            onUploadArchive={(archive) => uploadArchive(archive, currentFolder || undefined)}
            onDeleteProject={deleteCurrentProject}
          />
        ) : null}
        <LatexEditorPanes
          surfaceMode={surfaceMode}
          activeFilePath={activeFilePath}
          activeFileKind={activeFileKind}
          activeFileContent={activeFileContent}
          activeBlobUrl={activeBlobUrl}
          dirty={dirty}
          isFileLoading={isFileLoading}
          hasFeedbackSelection={hasFeedbackSelection}
          selectionText={selectionText}
          pdfDraftSelection={pdfDraftSelection}
          editorRef={editorRef}
          compiledPdfUrl={compiledPdfUrl}
          pdfHighlightFeedbacks={pdfHighlightFeedbacks}
          activeFeedbackId={activeFeedbackId}
          transientPdfAnchor={transientPdfAnchor}
          isCompiling={isCompiling}
          isSaving={isSaving}
          engine={engine}
          compileResult={compileResult}
          onSurfaceModeChange={setSurfaceMode}
          onInspectorOpenChange={setIsInspectorOpen}
          onOpenInspector={openInspector}
          onFileContentChange={setActiveFileContent}
          onSelectionChange={setSelectionRange}
          onPdfSelection={(payload) => void handlePdfSelection(payload)}
          onCompile={() => void compileProject(engine)}
          onOpenCompileLog={() => setIsCompileLogOpen(true)}
        />
        <LatexInspector
          isOpen={isInspectorOpen}
          surfaceMode={surfaceMode}
          activeTab={activeInspectorTab}
          tabs={inspectorTabs}
          feedbackContextText={feedbackContextText}
          feedbackDraftComment={feedbackDraftComment}
          feedbackScope={feedbackScope}
          canCreateFeedback={canCreateFeedback}
          isSaving={isSaving}
          isChatSending={isChatSending}
          feedbackBusyId={feedbackBusyId}
          feedbackError={feedbackError}
          feedbackStatus={feedbackStatus}
          protectionStatus={protectionStatus}
          protectionError={protectionError}
          isProtectingActiveFile={isProtectingActiveFile}
          activeFilePath={activeFilePath}
          activeFileKind={activeFileKind}
          lastRewriteUndo={lastRewriteUndo}
          isApplyingRewrite={isApplyingRewrite}
          selectedRewriteCandidate={selectedRewriteCandidate}
          selectedRewriteCandidateIndex={selectedRewriteCandidateIndex}
          rewriteCandidates={rewriteCandidates}
          diffViewMode={diffViewMode}
          showWhitespaceOnlyDiff={showWhitespaceOnlyDiff}
          collapsedDiffHunks={collapsedDiffHunks}
          previewFeedbackItem={previewFeedbackItem}
          feedbackLoaded={feedbackLoaded}
          currentFileFeedbacks={currentFileFeedbacks}
          activeFeedbackId={activeFeedbackId}
          optimizingFeedbackIds={prismOptimization.optimizingFeedbackIds}
          fileChangesRef={reviewQueue.fileChangesRef}
          fileChanges={fileChanges}
          appliedFileChanges={appliedFileChanges}
          pendingReviewItems={reviewQueue.pendingReviewItems}
          appliedReviewItems={reviewQueue.appliedReviewItems}
          focusedReviewItemId={reviewQueue.focusedReviewItemId}
          focusedLogicalKey={reviewQueue.focusedLogicalKey}
          fileChangePreviews={reviewQueue.fileChangePreviews}
          busyFileChangeKey={reviewQueue.busyFileChangeKey}
          fileChangeError={reviewQueue.fileChangeError}
          engineHint={engineHint}
          isCompiling={isCompiling}
          engine={engine}
          mainFile={project?.main_file}
          compileResult={compileResult}
          canOpenCompileLog={canOpenCompileLog}
          activePrismOptimizationJob={prismOptimization.activeJob}
          onTabChange={setActiveInspectorTab}
          onClose={() => setIsInspectorOpen(false)}
          onFeedbackDraftCommentChange={setFeedbackDraftComment}
          onFeedbackScopeChange={setFeedbackScope}
          onAddFeedbackAndRewrite={() => void addFeedbackAndRewrite()}
          onAddFeedbackOnly={() => void addFeedbackOnly()}
          onProtectActiveFile={() => void protectActiveFile()}
          onUndoLastRewrite={() => void undoLastRewrite()}
          onSelectRewriteCandidate={setSelectedRewriteCandidateId}
          onRegenerateRewrite={() => void regenerateRewritePreview()}
          onDiffViewModeChange={setDiffViewMode}
          onToggleWhitespaceOnlyDiff={() => setShowWhitespaceOnlyDiff((prev) => !prev)}
          onCollapseAllDiffHunks={setAllDiffHunksCollapsed}
          onToggleDiffHunkCollapsed={toggleDiffHunkCollapsed}
          onCopySelectedRewrite={() => void copySelectedRewrite()}
          onCancelRewritePreview={() => clearRewritePreview()}
          onApplyRewriteCandidate={() => void applyRewriteCandidate()}
          onFocusFeedback={focusFeedback}
          onRewriteFromFeedback={(item) => void rewriteFromFeedback(item)}
          onLaunchPrismOptimization={(item) => void launchPrismOptimizationFromFeedback(item)}
          onRemoveFeedback={removeFeedback}
          onPreviewProjectFileChange={(change) => void reviewQueue.previewProjectFileChange(change)}
          onDiscardPendingFileChange={(change) => void reviewQueue.discardPendingFileChange(change)}
          onApplyPendingFileChange={(change) => void reviewQueue.applyPendingFileChange(change)}
          onRevertAppliedFileChange={(change) => void reviewQueue.revertAppliedFileChange(change)}
          onOpenCompileLog={() => setIsCompileLogOpen(true)}
          onOpenTrace={() => prismOptimization.setTraceOpen(true)}
        />
      </div>

      <PrismOptimizationTraceDialog
        open={prismOptimization.isTraceOpen}
        activeJob={prismOptimization.activeJob}
        jobs={prismOptimization.jobs}
        activeRecord={prismOptimization.activeRecord}
        activePhases={prismOptimization.activePhases}
        fileChangesCount={fileChanges.length}
        onOpenChange={prismOptimization.setTraceOpen}
        onSelectJob={prismOptimization.setActiveJobId}
        onViewPendingChanges={() => {
          reviewQueue.scrollToReviewQueue();
          prismOptimization.setTraceOpen(false);
        }}
      />

      <LatexCompileLogDialog
        open={isCompileLogOpen}
        compileResult={compileResult}
        compileLog={compileLog}
        onOpenChange={setIsCompileLogOpen}
      />
    </main>
  );
}
