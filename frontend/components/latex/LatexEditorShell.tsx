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
  type PrismInspectorTab,
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
    if (
      feedbackWorkflow.hasFeedbackSelection
      || feedbackWorkflow.view.feedbackDraftComment.trim()
    ) {
      setActiveInspectorTab("assist");
      setIsInspectorOpen(true);
    }
  }, [
    feedbackWorkflow.hasFeedbackSelection,
    feedbackWorkflow.view.feedbackDraftComment,
  ]);

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
  const inspectorTabs: Array<{
    id: PrismInspectorTab;
    label: string;
    badge?: number;
  }> = [
    { id: "assist", label: "划词", badge: feedbackView.currentFileFeedbacks.length || undefined },
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
          feedbackContextText={feedbackView.feedbackContextText}
          feedbackDraftComment={feedbackView.feedbackDraftComment}
          feedbackScope={feedbackView.feedbackScope}
          canCreateFeedback={feedbackView.canCreateFeedback}
          isSaving={isSaving}
          isChatSending={isChatSending}
          feedbackBusyId={feedbackView.feedbackBusyId}
          feedbackError={feedbackError}
          feedbackStatus={feedbackStatus}
          protectionStatus={feedbackView.protectionStatus}
          protectionError={feedbackView.protectionError}
          isProtectingActiveFile={feedbackView.isProtectingActiveFile}
          activeFilePath={activeFilePath}
          activeFileKind={activeFileKind}
          lastRewriteUndo={feedbackView.lastRewriteUndo}
          isApplyingRewrite={feedbackView.isApplyingRewrite}
          selectedRewriteCandidate={feedbackView.selectedRewriteCandidate}
          selectedRewriteCandidateIndex={feedbackView.selectedRewriteCandidateIndex}
          rewriteCandidates={feedbackView.rewriteCandidates}
          diffViewMode={feedbackView.diffViewMode}
          showWhitespaceOnlyDiff={feedbackView.showWhitespaceOnlyDiff}
          collapsedDiffHunks={feedbackView.collapsedDiffHunks}
          previewFeedbackItem={feedbackView.previewFeedbackItem}
          feedbackLoaded={feedbackLoaded}
          currentFileFeedbacks={feedbackView.currentFileFeedbacks}
          activeFeedbackId={feedbackView.activeFeedbackId}
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
          onFeedbackDraftCommentChange={feedbackActions.setFeedbackDraftComment}
          onFeedbackScopeChange={feedbackActions.setFeedbackScope}
          onAddFeedbackAndRewrite={() => void feedbackActions.addFeedbackAndRewrite()}
          onAddFeedbackOnly={() => void feedbackActions.addFeedbackOnly()}
          onProtectActiveFile={() => void feedbackActions.protectFile()}
          onUndoLastRewrite={() => void feedbackActions.undoRewrite()}
          onSelectRewriteCandidate={feedbackActions.selectRewriteCandidate}
          onRegenerateRewrite={() => void feedbackActions.regenerateRewrite()}
          onDiffViewModeChange={feedbackActions.setDiffViewMode}
          onToggleWhitespaceOnlyDiff={feedbackActions.toggleWhitespaceOnlyDiff}
          onCollapseAllDiffHunks={feedbackActions.setAllDiffHunksCollapsed}
          onToggleDiffHunkCollapsed={feedbackActions.toggleDiffHunkCollapsed}
          onCopySelectedRewrite={() => void feedbackActions.copySelectedRewrite()}
          onCancelRewritePreview={feedbackActions.cancelRewritePreview}
          onApplyRewriteCandidate={() => void feedbackActions.applyRewrite()}
          onFocusFeedback={feedbackActions.focusFeedback}
          onRewriteFromFeedback={(item) => void feedbackActions.rewrite(item)}
          onLaunchPrismOptimization={(item) => void feedbackActions.launchPrismOptimization(item)}
          onRemoveFeedback={feedbackActions.removeFeedback}
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
