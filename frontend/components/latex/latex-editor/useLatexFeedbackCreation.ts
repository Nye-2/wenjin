import { useCallback } from "react";
import type { RefObject } from "react";

import type {
  LatexFeedbackAnchor,
  LatexFeedbackItem,
  LatexPdfAnchor,
} from "@/lib/api";
import { mapLatexFeedbackSelection } from "@/lib/api";
import {
  buildFeedbackAnchor,
  createFeedbackId,
  parsePdfAnchor,
  resolveSnippetRange,
} from "./feedbackAnchors";
import type { PrismTextEditorHandle } from "./PrismMonacoEditor";
import type { PdfDraftSelection } from "./types";

interface UseLatexFeedbackCreationOptions {
  projectId: string;
  activeFilePath: string | null;
  activeFileKind: "text" | "blob" | null;
  activeFileContent: string;
  compileHistoryId?: string | null;
  feedbackDraftComment: string;
  pdfDraftSelection: PdfDraftSelection | null;
  transientPdfAnchor: LatexPdfAnchor | null;
  selectionRange: [number, number];
  editorRef: RefObject<PrismTextEditorHandle | null>;
  openFile: (path: string) => Promise<void>;
  setSelectedPath: (path: string) => void;
  setSelectedPathType: (type: "file" | "dir") => void;
  setSelectionRange: (range: [number, number]) => void;
  setTransientPdfAnchor: (anchor: LatexPdfAnchor | null) => void;
  setFeedbackStatus: (message: string) => void;
  setFeedbackError: (message: string) => void;
}

export function useLatexFeedbackCreation({
  projectId,
  activeFilePath,
  activeFileKind,
  activeFileContent,
  compileHistoryId,
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
}: UseLatexFeedbackCreationOptions) {
  return useCallback(async (requireMappedForRewrite: boolean): Promise<LatexFeedbackItem | null> => {
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
          history_id: compileHistoryId || null,
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
    compileHistoryId,
    editorRef,
    feedbackDraftComment,
    openFile,
    pdfDraftSelection,
    projectId,
    selectionRange,
    setFeedbackError,
    setFeedbackStatus,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
    setTransientPdfAnchor,
    transientPdfAnchor,
  ]);
}
