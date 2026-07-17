"use client";

import {
  FilePlus2,
  FileText,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  WandSparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { stageMissionVisualInsertion } from "@/lib/api/missions";
import type { PrismContextRef } from "@/lib/api/mission-types";
import {
  createWorkspacePrismFile,
  getWorkspacePrismFile,
  saveWorkspacePrismFile,
} from "@/lib/api/workspace";
import type {
  WorkspacePrismFile,
  WorkspacePrismFileContent,
  WorkspacePrismSurfaceResponse,
} from "@/lib/api/types";

type SaveState = "idle" | "loading" | "dirty" | "saving" | "saved" | "error" | "conflict";
type VisualInsertionSource = {
  missionId: string;
  sourceReviewItemId: string;
};
type SaveOperation = {
  id: number;
  fileId: string;
  promise: Promise<boolean>;
};

const TEXT_EXTENSIONS = [".md", ".markdown", ".tex", ".bib", ".svg"];
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".svg"];
const AUTOSAVE_DELAY_MS = 1500;

function sortFiles(files: WorkspacePrismFile[]): WorkspacePrismFile[] {
  return [...files].sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.path.localeCompare(b.path);
  });
}

function fileName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function fileDirectory(path: string): string {
  const index = path.lastIndexOf("/");
  return index > 0 ? path.slice(0, index) : "";
}

function extension(path: string): string {
  const index = path.lastIndexOf(".");
  return index >= 0 ? path.slice(index).toLowerCase() : "";
}

function isTextFile(file: WorkspacePrismFile | null): boolean {
  if (!file) return false;
  const mime = file.mime_type ?? "";
  if (mime.startsWith("text/")) return true;
  return TEXT_EXTENSIONS.includes(extension(file.path));
}

function isMarkdownFile(file: WorkspacePrismFile | null): boolean {
  if (!file) return false;
  const mime = file.mime_type ?? "";
  return mime.includes("markdown") || [".md", ".markdown"].includes(extension(file.path));
}

function isManuscriptTextFile(file: WorkspacePrismFile | null): boolean {
  return file !== null && [".md", ".markdown", ".tex"].includes(extension(file.path));
}

function isImageFile(file: WorkspacePrismFile | null): boolean {
  if (!file) return false;
  const mime = file.mime_type ?? "";
  return mime.startsWith("image/") || IMAGE_EXTENSIONS.includes(extension(file.path));
}

function readAssetUrl(content: WorkspacePrismFileContent | null): string | null {
  const inline = content?.current_version?.content_inline ?? "";
  if (inline.startsWith("data:image/")) return inline;
  const metadata = content?.file.metadata_json ?? {};
  const rawUrl = metadata.asset_url ?? metadata.url ?? metadata.preview_url;
  return typeof rawUrl === "string" && rawUrl.trim() ? rawUrl.trim() : null;
}

function saveLabel(state: SaveState): string {
  if (state === "loading") return "加载中";
  if (state === "dirty") return "未保存";
  if (state === "saving") return "保存中";
  if (state === "error") return "保存失败";
  if (state === "conflict") return "有冲突";
  return "已保存";
}

function inferMimeType(path: string): string | undefined {
  const ext = extension(path);
  if (ext === ".md" || ext === ".markdown") return "text/markdown";
  if (ext === ".tex") return "text/x-tex";
  if (ext === ".bib") return "text/x-bibtex";
  if (ext === ".svg") return "image/svg+xml";
  return undefined;
}

export function PrismWorkspaceShell({
  workspaceId,
  surface,
  initialFileId,
  visualInsertionSource,
  onSurfaceChanged,
}: {
  workspaceId: string;
  surface: WorkspacePrismSurfaceResponse;
  initialFileId?: string | null;
  visualInsertionSource?: VisualInsertionSource | null;
  onSurfaceChanged?: () => void;
}) {
  const router = useRouter();
  const files = useMemo(() => sortFiles(surface.prism_files ?? []), [surface.prism_files]);
  const defaultFileId = initialFileId && files.some((file) => file.id === initialFileId)
    ? initialFileId
    : files[0]?.id ?? null;
  const [selectedFileId, setSelectedFileId] = useState<string | null>(defaultFileId);
  const [loadedFileId, setLoadedFileId] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<WorkspacePrismFileContent | null>(null);
  const [editorValue, setEditorValue] = useState("");
  const [baseContent, setBaseContent] = useState("");
  const [baseHash, setBaseHash] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>(defaultFileId ? "loading" : "saved");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [stagingInsertion, setStagingInsertion] = useState(false);
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef<SaveOperation | null>(null);
  const saveOperationIdRef = useRef(0);
  const switchRequestIdRef = useRef(0);
  const fileSessionRef = useRef(0);
  const selectedFileIdRef = useRef<string | null>(selectedFileId);
  const loadedFileIdRef = useRef<string | null>(loadedFileId);
  const editorValueRef = useRef(editorValue);
  const baseContentRef = useRef(baseContent);
  const baseHashRef = useRef(baseHash);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const selectedFile = files.find((file) => file.id === selectedFileId) ?? null;
  const activeContent =
    loadedFileId === selectedFileId && fileContent?.file.id === selectedFileId
      ? fileContent
      : null;
  const activeFile = activeContent?.file ?? selectedFile;
  const editorReady = Boolean(selectedFileId && loadedFileId === selectedFileId);
  const textEditable = isTextFile(activeFile);
  const dirty = editorReady && textEditable && editorValue !== baseContent;
  const assetUrl = readAssetUrl(activeContent);

  selectedFileIdRef.current = selectedFileId;
  loadedFileIdRef.current = loadedFileId;
  editorValueRef.current = editorValue;
  baseContentRef.current = baseContent;
  baseHashRef.current = baseHash;

  const readSelectionContext = useCallback(async (): Promise<PrismContextRef | null> => {
    const editor = editorRef.current;
    const revisionRef = activeContent?.current_version?.id;
    const projectId = surface.prism_project_id;
    if (
      !editor ||
      !selectedFileId ||
      !revisionRef ||
      !projectId ||
      dirty ||
      saveState !== "saved"
    ) {
      setErrorText("请先保存文件，再选择一段正文生成学术图。");
      return null;
    }
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    if (end <= start) {
      setErrorText("请先在正文中选择一段需要配图的内容。");
      editor.focus();
      return null;
    }
    const selection = editorValue.slice(start, end);
    const encoder = new TextEncoder();
    const selectionBytes = encoder.encode(selection);
    const selectionByteStart = encoder.encode(editorValue.slice(0, start)).byteLength;
    const selectionByteEnd = selectionByteStart + selectionBytes.byteLength;
    const digest = await crypto.subtle.digest(
      "SHA-256",
      selectionBytes,
    );
    const selectionHash = `sha256:${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
    return {
      workspace_id: workspaceId,
      prism_project_id: projectId,
      file_id: selectedFileId,
      base_revision_ref: revisionRef,
      selection_hash: selectionHash,
      selection_byte_range: [selectionByteStart, selectionByteEnd],
    };
  }, [activeContent, dirty, editorValue, saveState, selectedFileId, surface.prism_project_id, workspaceId]);

  const openVisualTaskFromSelection = useCallback(async () => {
    const context = await readSelectionContext();
    if (!context) return;
    const params = new URLSearchParams({
      prism_project_id: context.prism_project_id,
      prism_file_id: context.file_id,
      prism_revision_ref: context.base_revision_ref,
      prism_selection_hash: context.selection_hash,
      prism_selection_byte_start: String(context.selection_byte_range[0]),
      prism_selection_byte_end: String(context.selection_byte_range[1]),
    });
    router.push(`/workspaces/${encodeURIComponent(workspaceId)}?${params.toString()}`);
  }, [readSelectionContext, router, workspaceId]);

  const stageVisualInsertion = useCallback(async () => {
    if (!visualInsertionSource) return;
    if (!isManuscriptTextFile(activeFile)) {
      setErrorText("请选择 Markdown 或 TeX 正文文件后再插入学术图。");
      return;
    }
    const context = await readSelectionContext();
    if (!context) return;
    setStagingInsertion(true);
    setErrorText(null);
    try {
      await stageMissionVisualInsertion({
        missionId: visualInsertionSource.missionId,
        sourceReviewItemId: visualInsertionSource.sourceReviewItemId,
        prismContextRef: context,
      });
      router.push(
        `/workspaces/${encodeURIComponent(workspaceId)}?mission_id=${encodeURIComponent(visualInsertionSource.missionId)}&mission_surface=review`,
      );
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "插入预览生成失败");
    } finally {
      setStagingInsertion(false);
    }
  }, [activeFile, readSelectionContext, router, visualInsertionSource, workspaceId]);

  const saveBufferSnapshot = useCallback((
    fileId: string,
    content: string,
    expectedHash: string | null,
  ): Promise<boolean> => {
    const operationId = saveOperationIdRef.current + 1;
    const savingSession = fileSessionRef.current;
    saveOperationIdRef.current = operationId;

    const promise = (async () => {
      setSaveState("saving");
      setErrorText(null);
      try {
        const result = await saveWorkspacePrismFile(workspaceId, fileId, {
          content_inline: content,
          expected_current_hash: expectedHash,
        });
        if (result.file.id !== fileId) {
          throw new Error("保存响应与当前文件不匹配");
        }
        if (
          selectedFileIdRef.current !== fileId ||
          loadedFileIdRef.current !== fileId ||
          fileSessionRef.current !== savingSession
        ) {
          return false;
        }

        const nextHash = result.file.content_hash ?? result.version?.content_hash ?? null;
        baseContentRef.current = content;
        baseHashRef.current = nextHash;
        setFileContent((current) => current && current.file.id === fileId
          ? {
              ...current,
              file: result.file,
              current_version: result.version ?? current.current_version ?? null,
            }
          : {
              file: result.file,
              current_version: result.version ?? null,
            });
        setBaseContent(content);
        setBaseHash(nextHash);
        setSaveState(editorValueRef.current === content ? "saved" : "dirty");
        onSurfaceChanged?.();
        return true;
      } catch (error) {
        if (
          selectedFileIdRef.current === fileId &&
          loadedFileIdRef.current === fileId &&
          fileSessionRef.current === savingSession
        ) {
          const message = error instanceof Error ? error.message : "保存失败";
          setSaveState(message.includes("409") || message.includes("changed") ? "conflict" : "error");
          setErrorText(message);
        }
        return false;
      } finally {
        if (saveInFlightRef.current?.id === operationId) {
          saveInFlightRef.current = null;
        }
      }
    })();

    saveInFlightRef.current = { id: operationId, fileId, promise };
    return promise;
  }, [onSurfaceChanged, workspaceId]);

  const flushCurrentBuffer = useCallback(async (fileId: string): Promise<boolean> => {
    while (
      selectedFileIdRef.current === fileId &&
      loadedFileIdRef.current === fileId
    ) {
      const inFlight = saveInFlightRef.current;
      if (inFlight) {
        if (inFlight.fileId !== fileId || !(await inFlight.promise)) {
          return false;
        }
        continue;
      }

      const content = editorValueRef.current;
      if (content === baseContentRef.current) {
        return true;
      }
      if (!(await saveBufferSnapshot(fileId, content, baseHashRef.current))) {
        return false;
      }
    }
    return false;
  }, [saveBufferSnapshot]);

  const selectFile = useCallback(async (fileId: string) => {
    const requestId = switchRequestIdRef.current + 1;
    switchRequestIdRef.current = requestId;
    if (selectedFileIdRef.current === fileId) return;

    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }

    const currentFileId = selectedFileIdRef.current;
    if (currentFileId && loadedFileIdRef.current === currentFileId) {
      const saved = await flushCurrentBuffer(currentFileId);
      if (!saved || switchRequestIdRef.current !== requestId) return;
    }
    if (switchRequestIdRef.current !== requestId) return;

    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    selectedFileIdRef.current = fileId;
    loadedFileIdRef.current = null;
    editorValueRef.current = "";
    baseContentRef.current = "";
    baseHashRef.current = null;
    fileSessionRef.current += 1;
    setSelectedFileId(fileId);
    setLoadedFileId(null);
    setFileContent(null);
    setEditorValue("");
    setBaseContent("");
    setBaseHash(null);
    setErrorText(null);
    setSaveState("loading");
  }, [flushCurrentBuffer]);

  useEffect(() => {
    if (!selectedFileId && defaultFileId) {
      void selectFile(defaultFileId);
    }
  }, [defaultFileId, selectFile, selectedFileId]);

  useEffect(() => {
    if (!selectedFileId) {
      loadedFileIdRef.current = null;
      editorValueRef.current = "";
      baseContentRef.current = "";
      baseHashRef.current = null;
      setLoadedFileId(null);
      setFileContent(null);
      setEditorValue("");
      setBaseContent("");
      setBaseHash(null);
      setSaveState("saved");
      return;
    }

    const requestedFileId = selectedFileId;
    const requestedSession = fileSessionRef.current + 1;
    fileSessionRef.current = requestedSession;
    let cancelled = false;
    loadedFileIdRef.current = null;
    setLoadedFileId(null);
    setFileContent(null);
    setEditorValue("");
    setBaseContent("");
    setBaseHash(null);
    setSaveState("loading");
    setErrorText(null);
    getWorkspacePrismFile(workspaceId, requestedFileId)
      .then((content) => {
        if (
          cancelled ||
          fileSessionRef.current !== requestedSession ||
          selectedFileIdRef.current !== requestedFileId ||
          content.file.id !== requestedFileId
        ) {
          return;
        }
        const inline = content.current_version?.content_inline ?? "";
        const contentHash = content.file.content_hash ?? content.current_version?.content_hash ?? null;
        loadedFileIdRef.current = requestedFileId;
        editorValueRef.current = inline;
        baseContentRef.current = inline;
        baseHashRef.current = contentHash;
        setLoadedFileId(requestedFileId);
        setFileContent(content);
        setEditorValue(inline);
        setBaseContent(inline);
        setBaseHash(contentHash);
        setSaveState("saved");
      })
      .catch((error) => {
        if (
          cancelled ||
          fileSessionRef.current !== requestedSession ||
          selectedFileIdRef.current !== requestedFileId
        ) {
          return;
        }
        setSaveState("error");
        setErrorText(error instanceof Error ? error.message : "文件加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFileId, workspaceId]);

  useEffect(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!editorReady || !textEditable || !dirty || !selectedFileId) {
      setSaveState((current) => current === "dirty" ? "saved" : current);
      return undefined;
    }
    setSaveState((current) => current === "saving" ? current : "dirty");
    const fileId = selectedFileId;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      void flushCurrentBuffer(fileId);
    }, AUTOSAVE_DELAY_MS);
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [dirty, editorReady, editorValue, flushCurrentBuffer, selectedFileId, textEditable]);

  const createFile = useCallback(async () => {
    const rawPath = window.prompt("新建文件路径", "docs/new-note.md");
    const path = rawPath?.trim();
    if (!path) return;
    setSaveState("saving");
    setErrorText(null);
    try {
      const result = await createWorkspacePrismFile(workspaceId, {
        path,
        content_inline: "",
        file_role: "manual",
        mime_type: inferMimeType(path),
      });
      void selectFile(result.file.id);
      onSurfaceChanged?.();
    } catch (error) {
      setSaveState("error");
      setErrorText(error instanceof Error ? error.message : "新建文件失败");
    }
  }, [onSurfaceChanged, selectFile, workspaceId]);

  return (
    <section
      data-testid="prism-workspace-shell"
      className="flex h-full min-h-0 flex-col overflow-y-auto bg-[var(--wjn-surface)] text-[var(--wjn-text)] md:grid md:grid-cols-[220px_minmax(0,1fr)] md:grid-rows-[minmax(320px,1fr)_minmax(240px,0.7fr)] md:overflow-hidden xl:grid-cols-[260px_minmax(320px,1fr)_minmax(320px,0.9fr)] xl:grid-rows-1"
    >
      <aside className="flex min-h-[120px] max-h-44 shrink-0 flex-col border-b border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] md:row-span-2 md:max-h-none md:min-h-0 md:border-b-0 md:border-r xl:row-span-1">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">文件</div>
            <div className="text-xs text-[var(--wjn-text-muted)]">{files.length} 个项目</div>
          </div>
          <IconButton label="新建文件" onClick={createFile}>
            <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {files.length === 0 ? (
            <div className="px-2 py-8 text-center text-sm text-[var(--wjn-text-muted)]">
              暂无文件
            </div>
          ) : (
            files.map((file) => {
              const active = file.id === selectedFileId;
              const dir = fileDirectory(file.path);
              const Icon = isImageFile(file) && !isTextFile(file) ? ImageIcon : FileText;
              return (
                <button
                  key={file.id}
                  type="button"
                  data-testid={`prism-file-${file.id}`}
                  onClick={() => void selectFile(file.id)}
                  className={[
                    "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors",
                    active
                      ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-text)]"
                      : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]",
                  ].join(" ")}
                >
                  <Icon className="h-4 w-4 shrink-0 text-[var(--wjn-blue)]" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{fileName(file.path)}</span>
                    {dir ? (
                      <span className="block truncate text-xs text-[var(--wjn-text-muted)]">{dir}</span>
                    ) : null}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <main className="flex min-h-[360px] shrink-0 flex-col border-b border-[var(--wjn-line)] md:min-h-0 md:border-r xl:border-b-0">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-4">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{activeFile?.path ?? "WenjinPrism"}</div>
            {activeFile?.content_hash ? (
              <div className="truncate text-xs text-[var(--wjn-text-muted)]">{activeFile.content_hash}</div>
            ) : null}
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--wjn-text-muted)]">
            {textEditable && !visualInsertionSource ? (
              <IconButton
                label="基于选区生成学术图"
                onClick={() => void openVisualTaskFromSelection()}
                disabled={dirty || saveState !== "saved"}
              >
                <WandSparkles className="h-3.5 w-3.5" aria-hidden="true" />
              </IconButton>
            ) : null}
            {saveState === "saving" || saveState === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : saveState === "error" || saveState === "conflict" ? (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            ) : null}
            <span data-testid="prism-save-state">{saveLabel(saveState)}</span>
          </div>
        </div>
        {visualInsertionSource ? (
          <div
            data-testid="prism-visual-insertion"
            className="flex shrink-0 flex-col items-stretch gap-2 border-b border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] px-4 py-2.5 sm:flex-row sm:items-center sm:gap-3"
          >
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold text-[var(--wjn-accent-strong)]">放置已确认的学术图</div>
              <div className="mt-0.5 text-[11px] leading-4 text-[var(--wjn-text-secondary)]">
                在正文中选中图应放置在其后的段落，再生成可确认的插入预览。
              </div>
            </div>
            <button
              type="button"
              disabled={stagingInsertion || dirty || saveState !== "saved"}
              onClick={() => void stageVisualInsertion()}
              className="wjn-button-primary flex h-8 shrink-0 items-center gap-1.5 px-3 text-xs disabled:opacity-45"
            >
              {stagingInsertion ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <WandSparkles className="h-3.5 w-3.5" aria-hidden="true" />}
              {stagingInsertion ? "生成中" : "生成插入预览"}
            </button>
            <button
              type="button"
              disabled={stagingInsertion}
              onClick={() => router.push(`/workspaces/${encodeURIComponent(workspaceId)}/prism`)}
              className="h-8 shrink-0 px-2 text-xs text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)] disabled:opacity-45"
            >
              取消
            </button>
          </div>
        ) : null}
        {errorText ? (
          <div className="border-b border-[rgba(185,28,28,0.18)] bg-[rgba(254,242,242,0.86)] px-4 py-2 text-xs text-[var(--wjn-error)]">
            {errorText}
          </div>
        ) : null}
        <div className="min-h-0 flex-1">
          {!activeFile ? (
            <div className="flex h-full items-center justify-center text-sm text-[var(--wjn-text-muted)]">
              选择或新建一个文件
            </div>
          ) : saveState === "loading" && loadedFileId !== activeFile.id ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-[var(--wjn-text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              正在打开文件
            </div>
          ) : textEditable ? (
            <textarea
              ref={editorRef}
              data-testid="prism-file-editor"
              aria-label={`编辑 ${activeFile.path}`}
              value={editorValue}
              onChange={(event) => {
                editorValueRef.current = event.target.value;
                setEditorValue(event.target.value);
              }}
              spellCheck={false}
              className="h-full w-full resize-none border-0 bg-[var(--wjn-surface)] p-4 font-mono text-sm leading-6 text-[var(--wjn-text)] outline-none"
            />
          ) : (
            <div className="flex h-full items-center justify-center px-8 text-center text-sm text-[var(--wjn-text-muted)]">
              此文件是非文本资源，可在右侧预览。
            </div>
          )}
        </div>
      </main>

      <aside className="flex min-h-[260px] shrink-0 flex-col bg-[var(--wjn-surface)] md:col-start-2 md:min-h-0 xl:col-start-auto">
        <div className="flex h-12 shrink-0 items-center border-b border-[var(--wjn-line)] px-4 text-sm font-semibold">
          预览
        </div>
        <div data-testid="prism-file-preview" className="min-h-0 flex-1 overflow-auto p-5">
          {!activeFile ? (
            <div className="text-sm text-[var(--wjn-text-muted)]">暂无预览</div>
          ) : isMarkdownFile(activeFile) ? (
            <MarkdownRenderer content={editorValue} className="prose-chat text-[var(--wjn-text)]" />
          ) : isImageFile(activeFile) && assetUrl ? (
            <img
              src={assetUrl}
              alt={fileName(activeFile.path)}
              className="max-h-full max-w-full rounded-md border border-[var(--wjn-line)] object-contain"
            />
          ) : textEditable ? (
            <pre className="whitespace-pre-wrap rounded-md bg-[var(--wjn-surface-subtle)] p-4 font-mono text-xs leading-6 text-[var(--wjn-text-secondary)]">
              {editorValue}
            </pre>
          ) : (
            <div className="text-sm text-[var(--wjn-text-muted)]">
              当前资源没有可用的内联预览。
            </div>
          )}
        </div>
      </aside>
    </section>
  );
}
