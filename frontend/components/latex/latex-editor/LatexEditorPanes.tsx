import { useEffect, useState, type RefObject } from "react";
import {
  Columns3,
  FileImage,
  Fullscreen,
  Loader2,
  MessageSquareText,
  Minimize2,
  PanelRightClose,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { LatexPdfPreview } from "@/components/latex/LatexPdfPreview";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import type {
  LatexCompileEngine,
  LatexCompileResult,
  LatexPdfAnchor,
} from "@/lib/api";
import { isImageFile, isTextFile } from "./fileKinds";
import {
  PrismMonacoEditor,
  type PrismTextEditorHandle,
} from "./PrismMonacoEditor";
import type {
  PdfDraftSelection,
  PrismAssistIntent,
  PrismSurfaceMode,
} from "./types";

interface PdfHighlightFeedback {
  id: string;
  selectedText: string;
  pdfAnchor?: LatexPdfAnchor | null;
}

export function LatexEditorPanes({
  surfaceMode,
  stageLabel,
  activeFilePath,
  activeFileKind,
  activeFileContent,
  activeBlobUrl,
  dirty,
  isFileLoading,
  hasFeedbackSelection,
  selectionText,
  pdfDraftSelection,
  editorRef,
  compiledPdfUrl,
  pdfHighlightFeedbacks,
  activeFeedbackId,
  transientPdfAnchor,
  isCompiling,
  isSaving,
  engine,
  compileResult,
  onSurfaceModeChange,
  onAssistOpenChange,
  onOpenAssist,
  onFileContentChange,
  onSelectionChange,
  onPdfSelection,
  onCompile,
  onOpenCompileLog,
}: {
  surfaceMode: PrismSurfaceMode;
  stageLabel?: string;
  activeFilePath: string | null;
  activeFileKind: "text" | "blob" | null;
  activeFileContent: string;
  activeBlobUrl: string | null;
  dirty: boolean;
  isFileLoading: boolean;
  hasFeedbackSelection: boolean;
  selectionText: string;
  pdfDraftSelection: PdfDraftSelection | null;
  editorRef: RefObject<PrismTextEditorHandle | null>;
  compiledPdfUrl: string | null;
  pdfHighlightFeedbacks: PdfHighlightFeedback[];
  activeFeedbackId: string | null;
  transientPdfAnchor: LatexPdfAnchor | null;
  isCompiling: boolean;
  isSaving: boolean;
  engine: LatexCompileEngine;
  compileResult: LatexCompileResult | null;
  onSurfaceModeChange: (mode: PrismSurfaceMode) => void;
  onAssistOpenChange: (open: boolean) => void;
  onOpenAssist: (intent: PrismAssistIntent) => void;
  onFileContentChange: (content: string) => void;
  onSelectionChange: (range: [number, number]) => void;
  onPdfSelection: (payload: PdfDraftSelection) => void;
  onCompile: () => void;
  onOpenCompileLog: () => void;
}) {
  const [pdfFitMode, setPdfFitMode] = useState<"width" | "page">("width");
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [syncScroll, setSyncScroll] = useState(true);
  const [pdfFocused, setPdfFocused] = useState(false);
  const [isNarrowStage, setIsNarrowStage] = useState(false);
  const [narrowStageView, setNarrowStageView] = useState<"editor" | "pdf" | "review">("pdf");

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia("(max-width: 899px)");
    const update = () => setIsNarrowStage(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (surfaceMode === "compare" && isNarrowStage) {
      setNarrowStageView("pdf");
    }
  }, [isNarrowStage, surfaceMode]);

  const renderEditorPanel = () => (
    <div className="relative flex h-full min-h-0 flex-1 flex-col rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white shadow-[var(--wjn-shadow-sm)]">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate text-sm font-medium text-[var(--wjn-text)]">
            <span className="truncate">{activeFilePath || "未选择文件"}</span>
            {isFileLoading ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[var(--wjn-text-muted)]" />
            ) : null}
          </p>
          <p className="text-[11px] text-[var(--wjn-text-muted)]">
            {activeFileKind === "blob"
              ? "预览文件"
              : dirty
                ? "存在未保存修改"
                : "内容已同步"}
          </p>
        </div>
        {hasFeedbackSelection ? (
          <div className="flex items-center gap-2 rounded-full border border-[var(--wjn-line)] bg-white px-2 py-1 shadow-sm">
            <span className="text-[11px] text-[var(--wjn-text-muted)]">
              已选 {selectionText.trim() ? selectionText.length : pdfDraftSelection?.text.trim().length || 0} 字
            </span>
            <Button size="sm" variant="outline" onClick={() => onOpenAssist("selection")}>
              <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
              点评
            </Button>
            <Button size="sm" onClick={() => onOpenAssist("selection")}>
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              优化
            </Button>
          </div>
        ) : surfaceMode !== "compare" ? (
          <button
            type="button"
            onClick={() => {
              onSurfaceModeChange("compare");
              onAssistOpenChange(false);
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--wjn-line)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--wjn-text-secondary)] hover:bg-[rgba(15,23,42,0.04)]"
          >
            <Columns3 className="h-3.5 w-3.5" />
            打开 PDF 对照
          </button>
        ) : null}
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
            <div className="px-6 text-center text-sm text-[var(--wjn-text-muted)]">
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
            onChange={onFileContentChange}
            onSelect={onSelectionChange}
            readOnly={!activeFilePath || !isTextFile(activeFilePath)}
          />
        </div>
      )}
    </div>
  );

  const renderPdfPanel = () => (
    <div className="flex min-h-0 flex-1 flex-col rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white shadow-[var(--wjn-shadow-sm)]">
      <div
        role="toolbar"
        aria-label="PDF 预览台"
        className="wjn-prism-pdf-toolbar flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 rounded-t-[var(--wjn-radius-md)] border-b border-[var(--wjn-line)] px-3 py-2"
      >
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--wjn-text)]">PDF 预览台</p>
          <p className="text-[11px] text-[var(--wjn-text-muted)]">
            可在 PDF 中划词，系统会映射回 TeX
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          <button
            type="button"
            aria-label="重新编译 PDF"
            title="重新编译 PDF"
            onClick={onCompile}
            className="wjn-icon-button"
            disabled={isCompiling || isSaving}
          >
            <RefreshCw
              className={isCompiling ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
              aria-hidden="true"
            />
          </button>
          <button
            type="button"
            aria-label="同步滚动"
            aria-pressed={syncScroll}
            onClick={() => setSyncScroll((value) => !value)}
            className="wjn-stage-button"
          >
            同步滚动
          </button>
          <button
            type="button"
            aria-label="适合宽度"
            aria-pressed={pdfFitMode === "width"}
            onClick={() => setPdfFitMode("width")}
            className="wjn-stage-button"
          >
            适合宽度
          </button>
          <button
            type="button"
            aria-label="整页"
            aria-pressed={pdfFitMode === "page"}
            onClick={() => setPdfFitMode("page")}
            className="wjn-stage-button"
          >
            整页
          </button>
          <label className="wjn-stage-field">
            <span className="sr-only">PDF 页码</span>
            <input
              aria-label="PDF 页码"
              type="number"
              min={1}
              value={pdfPage}
              onChange={(event) => setPdfPage(Math.max(1, Number(event.target.value) || 1))}
            />
            <span>/ 1</span>
          </label>
          <label className="wjn-stage-field">
            <span className="sr-only">PDF 缩放</span>
            <input
              aria-label="PDF 缩放"
              type="number"
              min={50}
              max={200}
              step={10}
              value={pdfZoom}
              onChange={(event) =>
                setPdfZoom(Math.min(200, Math.max(50, Number(event.target.value) || 100)))
              }
            />
            <span>%</span>
          </label>
          <button
            type="button"
            aria-label={pdfFocused ? "收起 PDF 预览" : "展开 PDF 预览"}
            title={pdfFocused ? "收起 PDF 预览" : "展开 PDF 预览"}
            aria-pressed={pdfFocused}
            onClick={() => setPdfFocused((value) => !value)}
            className="wjn-icon-button"
          >
            {pdfFocused ? (
              <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Fullscreen className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
          <Button size="sm" variant="outline" onClick={() => onSurfaceModeChange("edit")}>
            <PanelRightClose className="mr-1.5 h-3.5 w-3.5" />
            收起 PDF
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden bg-white">
        {compiledPdfUrl ? (
          <LatexPdfPreview
            pdfUrl={compiledPdfUrl}
            feedbacks={pdfHighlightFeedbacks}
            activeFeedbackId={activeFeedbackId}
            transientSelectionAnchor={transientPdfAnchor}
            transientSelectionText={selectionText}
            onSelection={onPdfSelection}
            fitMode={pdfFitMode}
            zoomPercent={pdfZoom}
            currentPage={pdfPage}
            className="h-full min-h-[520px] w-full"
          />
        ) : isCompiling ? (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 px-6 text-center text-sm text-[var(--wjn-text-muted)]">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在使用 {engine} 编译当前项目...
          </div>
        ) : compileResult && !compileResult.ok ? (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center px-6 text-center">
            <p className="text-sm font-medium text-red-600">编译失败</p>
            <p className="mt-2 max-w-sm text-xs leading-6 text-[var(--wjn-text-muted)]">
              {compileResult.error || "没有生成 PDF。打开编译日志查看 LaTeX 输出。"}
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => {
                onOpenAssist("compile");
                onOpenCompileLog();
              }}
            >
              查看编译日志
            </Button>
          </div>
        ) : (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 px-6 text-center text-sm text-[var(--wjn-text-muted)]">
            还没有可预览的 PDF。先保存并编译当前项目。
            <Button size="sm" onClick={onCompile} disabled={isCompiling || isSaving}>
              编译生成 PDF
            </Button>
          </div>
        )}
      </div>
    </div>
  );

  const renderNarrowStage = () => (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        role="tablist"
        aria-label="Prism 预览模式"
        className="wjn-prism-stage-switch mx-3 mt-3"
      >
        {[
          ["editor", "编辑"],
          ["pdf", "PDF"],
          ["review", "审阅"],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={narrowStageView === value}
            onClick={() => setNarrowStageView(value as "editor" | "pdf" | "review")}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 p-3">
        {narrowStageView === "editor" ? renderEditorPanel() : null}
        {narrowStageView === "pdf" ? renderPdfPanel() : null}
        {narrowStageView === "review" ? (
          <div className="flex h-full min-h-0 flex-col rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white p-4 shadow-[var(--wjn-shadow-sm)]">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--wjn-text)]">审阅</p>
              <p className="mt-1 text-xs text-[var(--wjn-text-muted)]">
                批注、待复核修改、保护段落
              </p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onAssistOpenChange(true)}>
                <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
                打开审阅
              </Button>
              <Button size="sm" variant="outline" onClick={() => setNarrowStageView("pdf")}>
                返回 PDF
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-[var(--wjn-bg-base)]">
      <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--wjn-line)] bg-white px-3 py-2">
        <p className="text-xs font-medium text-[var(--wjn-text-muted)]">
          {surfaceMode === "compare"
            ? `${stageLabel ?? "PDF 预览台"}已展开`
            : "PDF 对照按需打开"}
        </p>
      </div>
      <div className="flex min-h-0 flex-1 p-3">
        {surfaceMode === "compare" && isNarrowStage ? (
          renderNarrowStage()
        ) : surfaceMode === "compare" ? (
          <ResizablePanelGroup
            key={pdfFocused ? "pdf-focused" : "pdf-split"}
            orientation="horizontal"
            className="h-full min-h-0 gap-3"
          >
            <ResizablePanel id="prism-editor-panel" defaultSize={pdfFocused ? 34 : 54} minSize={28}>
              {renderEditorPanel()}
            </ResizablePanel>
            <ResizableHandle withHandle className="bg-transparent" />
            <ResizablePanel id="prism-pdf-panel" defaultSize={pdfFocused ? 66 : 46} minSize={32}>
              {renderPdfPanel()}
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          renderEditorPanel()
        )}
      </div>
    </section>
  );
}
