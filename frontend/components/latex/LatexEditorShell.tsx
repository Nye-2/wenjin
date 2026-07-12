"use client";

import {
  useCallback,
  useEffect,
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
  type PrismAssistIntent,
  type PrismSurfaceMode,
} from "@/components/latex/latex-editor/types";
import { usePrismOptimizationJobs } from "@/components/latex/latex-editor/usePrismOptimizationJobs";
import { usePrismReviewQueue } from "@/components/latex/latex-editor/usePrismReviewQueue";
import { useLatexFeedbackPersistence } from "@/components/latex/latex-editor/useLatexFeedbackPersistence";
import { useLatexPdfSelectionMapping } from "@/components/latex/latex-editor/useLatexPdfSelectionMapping";
import { useLatexFeedbackWorkflow } from "@/components/latex/latex-editor/useLatexFeedbackWorkflow";
import type {
  LatexCompileEngine,
  LatexAppliedFileChange,
  LatexFileChange,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { useChatStoreV2 } from "@/stores/chat-store";
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
  const [surfaceMode, setSurfaceMode] = useState<PrismSurfaceMode>("edit");
  const [isAssistOpen, setIsAssistOpen] = useState(false);
  const editorRef = useRef<PrismTextEditorHandle | null>(null);
  const {
    feedbackItems,
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
  const effectiveSelectedPath = selectedPath || activeFilePath;
  const effectiveSelectedType = selectedPathType || (activeFilePath ? "file" : null);
  const currentFolder =
    effectiveSelectedType === "dir"
      ? effectiveSelectedPath || ""
      : effectiveSelectedPath
        ? effectiveSelectedPath.split("/").slice(0, -1).join("/")
        : "";
  const selectionText = activeFileKind === "text" && selectionRange[1] > selectionRange[0]
    ? activeFileContent.slice(selectionRange[0], selectionRange[1])
    : "";
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

  const prismOptimization = usePrismOptimizationJobs({
    workspaceId,
    projectId,
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

  const feedbackWorkflow = useLatexFeedbackWorkflow({
    projectId,
    workspaceId,
    project,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    activeFileSavedContent,
    compileHistoryId: compileResult?.history_id,
    selectionRange,
    pdfDraftSelection,
    transientPdfAnchor,
    feedbackItems,
    setFeedbackItems,
    setFeedbackStatus,
    setFeedbackError,
    editorRef,
    prismOptimization,
    sendChatMessage,
    isChatSending,
    openFile,
    saveActiveFile,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
    setPdfDraftSelection,
    setTransientPdfAnchor,
    onReviewStateChanged,
  });

  useEffect(() => {
    if (feedbackWorkflow.view.feedbackDraftComment.trim()) {
      setIsAssistOpen(true);
    }
  }, [
    feedbackWorkflow.view.feedbackDraftComment,
  ]);

  useEffect(() => {
    if (reviewQueue.focusedReviewItemId || reviewQueue.focusedLogicalKey) {
      setIsAssistOpen(true);
    }
  }, [reviewQueue.focusedLogicalKey, reviewQueue.focusedReviewItemId]);

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

  const feedbackView = feedbackWorkflow.view;
  const feedbackActions = feedbackWorkflow.actions;

  const openAssist = useCallback((intent: PrismAssistIntent) => {
    if (intent === "compile") {
      setIsCompileLogOpen(true);
      return;
    }
    setIsAssistOpen(true);
  }, []);

  const compileWithVisibleFeedback = useCallback(() => {
    setSurfaceMode("compare");
    void compileProject(engine);
  }, [compileProject, engine]);

  const selectedCharacterCount = feedbackWorkflow.selectionText.trim()
    ? feedbackWorkflow.selectionText.trim().length
    : pdfDraftSelection?.text.trim().length || 0;
  const pendingRewriteCount = (feedbackView.selectedRewriteCandidate ? 1 : 0) + fileChanges.length;
  const runningJobCount = prismOptimization.jobs.filter(
    (job) => job.status === "launching" || job.status === "running",
  ).length;
  const assistStatus = feedbackStatus
    || (isCompiling ? `正在编译：${engine} · ${project?.main_file || "main.tex"}` : "")
    || (compileResult?.ok ? `最近一次编译：成功 · ${compileResult.engine} · ${compileResult.main_file}` : "");
  const canUseDocumentAssist = Boolean(activeFilePath && activeFileKind === "text");
  const canDeepAssist = canUseDocumentAssist && Boolean(feedbackView.feedbackDraftComment.trim());
  const stageLabel = surfaceMode === "compare" ? "PDF 预览台" : "编辑台";

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
        backLabel={workspaceId ? "Workbench" : "工作区"}
        onBack={() => router.push(workspaceId ? `/workspaces/${workspaceId}` : "/workspaces")}
        onEngineChange={setEngine}
        onSave={() => void saveActiveFile()}
        onCompile={compileWithVisibleFeedback}
      />
      {error ? (
        <div className="border-b border-red-500/20 bg-red-500/8 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      ) : null}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <LatexResourceRail
          tree={tree}
          selectedPath={effectiveSelectedPath}
          isProjectLoading={isProjectLoading}
          isDeletingProject={isDeletingProject}
          projectName={project?.name}
          currentFolderLabel={currentFolder || "项目根目录"}
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
          onCreateFile={(path) => createFile(path)}
          onCreateFolder={(path) => createFolder(path)}
          onUploadFiles={(files) => uploadFiles(files, currentFolder || undefined)}
          onUploadDirectory={(files) => uploadDirectory(files, currentFolder || undefined)}
          onUploadArchive={(archive) => uploadArchive(archive, currentFolder || undefined)}
          onDeleteProject={deleteCurrentProject}
        />
        <LatexEditorPanes
          surfaceMode={surfaceMode}
          stageLabel={stageLabel}
          activeFilePath={activeFilePath}
          activeFileKind={activeFileKind}
          activeFileContent={activeFileContent}
          activeBlobUrl={activeBlobUrl}
          dirty={dirty}
          isFileLoading={isFileLoading}
          hasFeedbackSelection={feedbackWorkflow.hasFeedbackSelection}
          selectionText={feedbackWorkflow.selectionText}
          pdfDraftSelection={pdfDraftSelection}
          editorRef={editorRef}
          compiledPdfUrl={compiledPdfUrl}
          pdfHighlightFeedbacks={feedbackWorkflow.pdfHighlightFeedbacks}
          activeFeedbackId={feedbackView.activeFeedbackId}
          transientPdfAnchor={transientPdfAnchor}
          isCompiling={isCompiling}
          isSaving={isSaving}
          engine={engine}
          compileResult={compileResult}
          onSurfaceModeChange={setSurfaceMode}
          onAssistOpenChange={setIsAssistOpen}
          onOpenAssist={openAssist}
          onFileContentChange={setActiveFileContent}
          onSelectionChange={setSelectionRange}
          onPdfSelection={(payload) => void handlePdfSelection(payload)}
          onCompile={compileWithVisibleFeedback}
          onOpenCompileLog={() => setIsCompileLogOpen(true)}
        />
      </div>

      <LatexInspector
        open={isAssistOpen}
        selectedCharacterCount={selectedCharacterCount}
        pendingRewriteCount={pendingRewriteCount}
        hasError={Boolean(feedbackError)}
        contextText={feedbackView.feedbackContextText}
        draftComment={feedbackView.feedbackDraftComment}
        scope={feedbackView.feedbackScope}
        canCreate={feedbackView.canCreateFeedback}
        canUseDocumentAssist={canUseDocumentAssist}
        canDeepAssist={canDeepAssist}
        hasSelectionContext={feedbackWorkflow.hasFeedbackSelection}
        busy={Boolean(feedbackView.feedbackBusyId) || isSaving || isChatSending}
        isSaving={isSaving}
        status={assistStatus}
        error={feedbackError}
        annotations={feedbackView.currentFileFeedbacks}
        activeFeedbackId={feedbackView.activeFeedbackId}
        selectedRewriteCandidate={feedbackView.selectedRewriteCandidate}
        selectedRewriteCandidateIndex={feedbackView.selectedRewriteCandidateIndex}
        rewriteCandidates={feedbackView.rewriteCandidates}
        diffViewMode={feedbackView.diffViewMode}
        showWhitespaceOnlyDiff={feedbackView.showWhitespaceOnlyDiff}
        collapsedDiffHunks={feedbackView.collapsedDiffHunks}
        previewFeedbackItem={feedbackView.previewFeedbackItem}
        feedbackBusyId={feedbackView.feedbackBusyId}
        isApplyingRewrite={feedbackView.isApplyingRewrite}
        runningJobCount={runningJobCount}
        protectionStatus={feedbackView.protectionStatus}
        protectionError={feedbackView.protectionError}
        isProtectingActiveFile={feedbackView.isProtectingActiveFile}
        canProtectActiveFile={Boolean(activeFilePath && activeFileKind === "text")}
        hasUndoableRewrite={Boolean(feedbackView.lastRewriteUndo)}
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
        onClose={() => setIsAssistOpen(false)}
        onDraftChange={feedbackActions.setFeedbackDraftComment}
        onScopeChange={feedbackActions.setFeedbackScope}
        onSaveComment={() => void feedbackActions.addFeedbackOnly()}
        onQuickRewrite={() => void feedbackActions.addFeedbackAndQuickRewrite()}
        onDeepAssist={() => void feedbackActions.launchDocumentOptimization()}
        onProtectActiveFile={() => void feedbackActions.protectFile()}
        onUndoRewrite={() => void feedbackActions.undoRewrite()}
        onFocusAnnotation={feedbackActions.focusFeedback}
        onQuickRewriteAnnotation={(item) => void feedbackActions.rewrite(item)}
        onDeepAssistAnnotation={(item) => void feedbackActions.launchPrismOptimization(item)}
        onRemoveAnnotation={feedbackActions.removeFeedback}
        onSelectCandidate={feedbackActions.selectRewriteCandidate}
        onOpenPanel={() => setIsAssistOpen(true)}
        onAnnotateSelection={() => setIsAssistOpen(true)}
        onOpenQuickRewrite={() => setIsAssistOpen(true)}
        onOpenDeepAssist={() => setIsAssistOpen(true)}
        onRegenerate={() => void feedbackActions.regenerateRewrite()}
        onDiffViewModeChange={feedbackActions.setDiffViewMode}
        onToggleWhitespaceOnlyDiff={feedbackActions.toggleWhitespaceOnlyDiff}
        onCollapseAllDiffHunks={feedbackActions.setAllDiffHunksCollapsed}
        onToggleDiffHunkCollapsed={feedbackActions.toggleDiffHunkCollapsed}
        onCopyRewrite={() => void feedbackActions.copySelectedRewrite()}
        onCancelRewrite={feedbackActions.cancelRewritePreview}
        onApplyRewrite={() => void feedbackActions.applyRewrite()}
        onPreviewProjectFileChange={(change) => void reviewQueue.previewProjectFileChange(change)}
        onDiscardPendingFileChange={(change) => void reviewQueue.discardPendingFileChange(change)}
        onApplyPendingFileChange={(change) => void reviewQueue.applyPendingFileChange(change)}
        onRevertAppliedFileChange={(change) => void reviewQueue.revertAppliedFileChange(change)}
      />

      <PrismOptimizationTraceDialog
        open={prismOptimization.isTraceOpen}
        activeJob={prismOptimization.activeJob}
        jobs={prismOptimization.jobs}
        activeMission={prismOptimization.activeMission}
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
