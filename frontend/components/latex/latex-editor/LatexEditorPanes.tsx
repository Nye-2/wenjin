import type { RefObject } from "react";
import {
  Columns3,
  Eye,
  FileImage,
  FileText,
  Focus,
  Loader2,
  MessageSquareText,
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
  PrismInspectorTab,
  PrismSurfaceMode,
} from "./types";

interface PdfHighlightFeedback {
  id: string;
  selectedText: string;
  pdfAnchor?: LatexPdfAnchor | null;
}

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

export function LatexEditorPanes({
  surfaceMode,
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
  onInspectorOpenChange,
  onOpenInspector,
  onFileContentChange,
  onSelectionChange,
  onPdfSelection,
  onCompile,
  onOpenCompileLog,
}: {
  surfaceMode: PrismSurfaceMode;
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
  onInspectorOpenChange: (open: boolean) => void;
  onOpenInspector: (tab: PrismInspectorTab) => void;
  onFileContentChange: (content: string) => void;
  onSelectionChange: (range: [number, number]) => void;
  onPdfSelection: (payload: PdfDraftSelection) => void;
  onCompile: () => void;
  onOpenCompileLog: () => void;
}) {
  const openMode = (mode: PrismSurfaceMode) => {
    onSurfaceModeChange(mode);
    if (mode === "review") {
      onOpenInspector("review");
    } else if (mode === "compare" || mode === "focus") {
      onInspectorOpenChange(false);
    }
  };

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
            <Button size="sm" variant="outline" onClick={() => onOpenInspector("assist")}>
              <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
              点评
            </Button>
            <Button size="sm" onClick={() => onOpenInspector("assist")}>
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              优化
            </Button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              onSurfaceModeChange("compare");
              onInspectorOpenChange(false);
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
            onChange={onFileContentChange}
            onSelect={onSelectionChange}
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
        <Button size="sm" variant="outline" onClick={() => onSurfaceModeChange("edit")}>
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
            onSelection={onPdfSelection}
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
                onOpenInspector("compile");
                onOpenCompileLog();
              }}
            >
              查看编译日志
            </Button>
          </div>
        ) : (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 px-6 text-center text-sm text-[var(--text-muted)]">
            还没有可预览的 PDF。先保存并编译当前项目。
            <Button size="sm" onClick={onCompile} disabled={isCompiling || isSaving}>
              编译生成 PDF
            </Button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-[var(--wjn-bg-base)]">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] bg-white px-3">
        <div className="inline-flex rounded-[10px] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-0.5">
          {surfaceModeOptions.map((option) => {
            const Icon = option.icon;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => openMode(option.id)}
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
}
