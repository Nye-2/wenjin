"use client";

import { useEffect, useRef, useState } from "react";
import { Archive, FolderPlus, Save, Sparkles, SquarePen, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { LatexCompileEngine } from "@/lib/api";

interface LatexToolbarProps {
  engine: LatexCompileEngine;
  onEngineChange: (engine: LatexCompileEngine) => void;
  onSave: () => void;
  onCompile: () => void;
  onCreateFile: (path: string) => Promise<void>;
  onCreateFolder: (path: string) => Promise<void>;
  onUploadFiles: (files: File[]) => Promise<void>;
  onUploadDirectory: (files: File[]) => Promise<void>;
  onUploadArchive: (archive: File) => Promise<void>;
  isSaving: boolean;
  isCompiling: boolean;
  disableActions: boolean;
  currentFolderLabel: string;
  engineHint?: string;
}

export function LatexToolbar({
  engine,
  onEngineChange,
  onSave,
  onCompile,
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  onUploadDirectory,
  onUploadArchive,
  isSaving,
  isCompiling,
  disableActions,
  currentFolderLabel,
  engineHint,
}: LatexToolbarProps) {
  const [newFilePath, setNewFilePath] = useState("");
  const [newFolderPath, setNewFolderPath] = useState("");
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!directoryInputRef.current) {
      return;
    }
    directoryInputRef.current.setAttribute("webkitdirectory", "");
    directoryInputRef.current.setAttribute("directory", "");
  }, []);

  return (
    <div className="rounded-lg border border-white/50 bg-white/75 p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={engine}
          onChange={(event) => onEngineChange(event.target.value as LatexCompileEngine)}
          className="h-9 rounded-md border border-[var(--border-default)] bg-white/90 px-2 text-sm"
        >
          <option value="xelatex">XeLaTeX（中文推荐）</option>
          <option value="pdflatex">PDFLaTeX（英文兼容）</option>
        </select>

        <Button size="sm" variant="outline" onClick={onSave} disabled={disableActions || isSaving}>
          <Save className="mr-2 h-4 w-4" />
          {isSaving ? "保存中..." : "保存"}
        </Button>

        <Button size="sm" onClick={onCompile} disabled={disableActions || isCompiling || isSaving}>
          <Sparkles className="mr-2 h-4 w-4" />
          {isCompiling ? "编译中..." : "编译"}
        </Button>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">
        {engineHint || "中文或中英混排稿件默认使用 XeLaTeX。PDFLaTeX 主要用于英文模板兼容。"}
      </p>

      <details className="mt-2">
        <summary className="inline-flex cursor-pointer list-none items-center gap-2 rounded-md px-2 py-1 text-xs text-[var(--text-muted)] hover:bg-white/70">
          文件操作
          <span className="text-[var(--v2-text-tertiary)]">{currentFolderLabel}</span>
        </summary>
        <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[var(--border-default)] bg-white/70 px-2.5 py-1.5 text-xs text-[var(--text-primary)] transition-colors hover:bg-white">
          <Upload className="h-4 w-4" />
          上传文件
          <input
            type="file"
            multiple
            className="hidden"
            onChange={async (event) => {
              const files = Array.from(event.target.files || []);
              if (!files.length) {
                return;
              }
              await onUploadFiles(files);
              event.currentTarget.value = "";
            }}
          />
        </label>

        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[var(--border-default)] bg-white/70 px-2.5 py-1.5 text-xs text-[var(--text-primary)] transition-colors hover:bg-white">
          <FolderPlus className="h-4 w-4" />
          上传目录
          <input
            ref={directoryInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={async (event) => {
              const files = Array.from(event.target.files || []);
              if (!files.length) {
                return;
              }
              await onUploadDirectory(files);
              event.currentTarget.value = "";
            }}
          />
        </label>

        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[var(--border-default)] bg-white/70 px-2.5 py-1.5 text-xs text-[var(--text-primary)] transition-colors hover:bg-white">
          <Archive className="h-4 w-4" />
          上传 ZIP
          <input
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={async (event) => {
              const archive = event.target.files?.[0] || null;
              if (!archive) {
                return;
              }
              await onUploadArchive(archive);
              event.currentTarget.value = "";
            }}
          />
        </label>
        </div>

      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        <div className="flex gap-2">
          <Input
            value={newFilePath}
            onChange={(event) => setNewFilePath(event.target.value)}
            placeholder="新文件路径，例如 sections/intro.tex"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={disableActions || isCreatingFile || !newFilePath.trim()}
            onClick={async () => {
              setIsCreatingFile(true);
              try {
                await onCreateFile(newFilePath.trim());
                setNewFilePath("");
              } finally {
                setIsCreatingFile(false);
              }
            }}
          >
            <SquarePen className="mr-2 h-4 w-4" />
            新文件
          </Button>
        </div>

        <div className="flex gap-2">
          <Input
            value={newFolderPath}
            onChange={(event) => setNewFolderPath(event.target.value)}
            placeholder="新目录路径，例如 sections/appendix"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={disableActions || isCreatingFolder || !newFolderPath.trim()}
            onClick={async () => {
              setIsCreatingFolder(true);
              try {
                await onCreateFolder(newFolderPath.trim());
                setNewFolderPath("");
              } finally {
                setIsCreatingFolder(false);
              }
            }}
          >
            <FolderPlus className="mr-2 h-4 w-4" />
            新文件夹
          </Button>
        </div>
      </div>
      </details>
    </div>
  );
}
