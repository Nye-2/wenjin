"use client";

import {
  FilePlus2,
  FileText,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
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
  onSurfaceChanged,
}: {
  workspaceId: string;
  surface: WorkspacePrismSurfaceResponse;
  initialFileId?: string | null;
  onSurfaceChanged?: () => void;
}) {
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
  const saveTimerRef = useRef<number | null>(null);
  const selectedFile = files.find((file) => file.id === selectedFileId) ?? null;
  const activeFile = fileContent?.file ?? selectedFile;
  const textEditable = isTextFile(activeFile);
  const dirty = textEditable && editorValue !== baseContent;
  const assetUrl = readAssetUrl(fileContent);

  useEffect(() => {
    if (!selectedFileId && defaultFileId) {
      setSelectedFileId(defaultFileId);
    }
  }, [defaultFileId, selectedFileId]);

  useEffect(() => {
    if (!selectedFileId) {
      setLoadedFileId(null);
      setFileContent(null);
      setEditorValue("");
      setBaseContent("");
      setBaseHash(null);
      setSaveState("saved");
      return;
    }

    let cancelled = false;
    setSaveState("loading");
    setErrorText(null);
    getWorkspacePrismFile(workspaceId, selectedFileId)
      .then((content) => {
        if (cancelled) return;
        const inline = content.current_version?.content_inline ?? "";
        setLoadedFileId(selectedFileId);
        setFileContent(content);
        setEditorValue(inline);
        setBaseContent(inline);
        setBaseHash(content.file.content_hash ?? content.current_version?.content_hash ?? null);
        setSaveState("saved");
      })
      .catch((error) => {
        if (cancelled) return;
        setSaveState("error");
        setErrorText(error instanceof Error ? error.message : "文件加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFileId, workspaceId]);

  const saveNow = useCallback(async () => {
    if (!selectedFileId || !textEditable || !dirty) return;
    setSaveState("saving");
    setErrorText(null);
    try {
      const result = await saveWorkspacePrismFile(workspaceId, selectedFileId, {
        content_inline: editorValue,
        expected_current_hash: baseHash,
      });
      setFileContent((current) => current
        ? {
            ...current,
            file: result.file,
            current_version: result.version ?? current.current_version ?? null,
          }
        : {
            file: result.file,
            current_version: result.version ?? null,
          });
      setBaseContent(editorValue);
      setBaseHash(result.file.content_hash ?? result.version?.content_hash ?? null);
      setSaveState("saved");
      onSurfaceChanged?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setSaveState(message.includes("409") || message.includes("changed") ? "conflict" : "error");
      setErrorText(message);
    }
  }, [baseHash, dirty, editorValue, onSurfaceChanged, selectedFileId, textEditable, workspaceId]);

  useEffect(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!dirty) {
      setSaveState((current) => current === "dirty" ? "saved" : current);
      return undefined;
    }
    setSaveState((current) => current === "saving" ? current : "dirty");
    saveTimerRef.current = window.setTimeout(() => {
      void saveNow();
    }, AUTOSAVE_DELAY_MS);
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [dirty, saveNow]);

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
      setSelectedFileId(result.file.id);
      onSurfaceChanged?.();
    } catch (error) {
      setSaveState("error");
      setErrorText(error instanceof Error ? error.message : "新建文件失败");
    }
  }, [onSurfaceChanged, workspaceId]);

  return (
    <section
      data-testid="prism-workspace-shell"
      className="grid h-full min-h-0 grid-cols-[260px_minmax(320px,1fr)_minmax(320px,0.9fr)] bg-[var(--wjn-surface)] text-[var(--wjn-text)]"
    >
      <aside className="flex min-h-0 flex-col border-r border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)]">
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
                  onClick={() => setSelectedFileId(file.id)}
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

      <main className="flex min-h-0 flex-col border-r border-[var(--wjn-line)]">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-4">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{activeFile?.path ?? "WenjinPrism"}</div>
            {activeFile?.content_hash ? (
              <div className="truncate text-xs text-[var(--wjn-text-muted)]">{activeFile.content_hash}</div>
            ) : null}
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--wjn-text-muted)]">
            {saveState === "saving" || saveState === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : saveState === "error" || saveState === "conflict" ? (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            ) : null}
            <span data-testid="prism-save-state">{saveLabel(saveState)}</span>
          </div>
        </div>
        {errorText ? (
          <div className="border-b border-[rgba(185,28,28,0.18)] bg-[rgba(254,242,242,0.86)] px-4 py-2 text-xs text-[var(--wjn-danger)]">
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
              data-testid="prism-file-editor"
              value={editorValue}
              onChange={(event) => setEditorValue(event.target.value)}
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

      <aside className="flex min-h-0 flex-col bg-[var(--wjn-surface)]">
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
