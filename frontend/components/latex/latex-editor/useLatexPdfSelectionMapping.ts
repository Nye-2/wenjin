import type { RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { LatexPdfAnchor } from "@/lib/api";
import { mapLatexFeedbackSelection } from "@/lib/api";
import {
  parsePdfAnchor,
  resolveSnippetRange,
} from "./feedbackAnchors";
import type { PrismTextEditorHandle } from "./PrismMonacoEditor";
import type { PdfDraftSelection } from "./types";

interface UseLatexPdfSelectionMappingOptions {
  projectId: string;
  activeFilePath: string | null;
  activeFileKind: "text" | "blob" | null;
  activeFileContent: string;
  compiledPdfUrl: string | null;
  compileHistoryId?: string | null;
  selectionRange: [number, number];
  selectionText: string;
  editorRef: RefObject<PrismTextEditorHandle | null>;
  openFile: (path: string) => Promise<void>;
  setSelectedPath: (path: string) => void;
  setSelectedPathType: (type: "file" | "dir") => void;
  setSelectionRange: (range: [number, number]) => void;
  setFeedbackStatus: (message: string) => void;
  setFeedbackError: (message: string) => void;
}

export function useLatexPdfSelectionMapping({
  projectId,
  activeFilePath,
  activeFileKind,
  activeFileContent,
  compiledPdfUrl,
  compileHistoryId,
  selectionRange,
  selectionText,
  editorRef,
  openFile,
  setSelectedPath,
  setSelectedPathType,
  setSelectionRange,
  setFeedbackStatus,
  setFeedbackError,
}: UseLatexPdfSelectionMappingOptions) {
  const [pdfDraftSelection, setPdfDraftSelection] = useState<PdfDraftSelection | null>(null);
  const [transientPdfAnchor, setTransientPdfAnchor] = useState<LatexPdfAnchor | null>(null);
  const texMapRequestSeqRef = useRef(0);
  const lastTexMapKeyRef = useRef("");

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
        history_id: compileHistoryId || null,
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
    compileHistoryId,
    editorRef,
    openFile,
    projectId,
    selectionRange,
    setFeedbackError,
    setFeedbackStatus,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
  ]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPdfDraftSelection(null);
      setTransientPdfAnchor(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeFilePath]);

  useEffect(() => {
    if (
      !compiledPdfUrl
      || !compileHistoryId
      || !activeFilePath
      || activeFileKind !== "text"
      || !selectionText.trim()
      || selectionRange[1] <= selectionRange[0]
    ) {
      const timer = window.setTimeout(() => {
        setTransientPdfAnchor(null);
      }, 0);
      lastTexMapKeyRef.current = "";
      return () => window.clearTimeout(timer);
    }

    const mapKey = [
      compileHistoryId,
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
        history_id: compileHistoryId,
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
    compileHistoryId,
    compiledPdfUrl,
    projectId,
    selectionRange,
    selectionText,
  ]);

  return {
    pdfDraftSelection,
    transientPdfAnchor,
    setPdfDraftSelection,
    setTransientPdfAnchor,
    handlePdfSelection,
  };
}
