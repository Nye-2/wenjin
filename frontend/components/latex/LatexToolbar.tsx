"use client";

import { useEffect, useRef, useState } from "react";
import { FolderPlus, Save, Sparkles, SquarePen, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface LatexToolbarProps {
  engine: "xelatex" | "pdflatex";
  onEngineChange: (engine: "xelatex" | "pdflatex") => void;
  onSave: () => void;
  onCompile: () => void;
  onCreateFile: (path: string) => Promise<void>;
  onCreateFolder: (path: string) => Promise<void>;
  onUploadFiles: (files: File[]) => Promise<void>;
  isSaving: boolean;
  isCompiling: boolean;
  disableActions: boolean;
  currentFolderLabel: string;
}

export function LatexToolbar({
  engine,
  onEngineChange,
  onSave,
  onCompile,
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  isSaving,
  isCompiling,
  disableActions,
  currentFolderLabel,
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
    <div className="rounded-[1.4rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.94)] p-4 shadow-[0_14px_30px_rgba(19,34,53,0.06)]">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={engine}
          onChange={(event) => onEngineChange(event.target.value as "xelatex" | "pdflatex")}
          className="h-10 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 text-sm"
        >
          <option value="xelatex">XeLaTeX</option>
          <option value="pdflatex">PDFLaTeX</option>
        </select>

        <Button variant="outline" onClick={onSave} disabled={disableActions || isSaving}>
          <Save className="mr-2 h-4 w-4" />
          {isSaving ? "保存中..." : "保存"}
        </Button>

        <Button onClick={onCompile} disabled={disableActions || isCompiling}>
          <Sparkles className="mr-2 h-4 w-4" />
          {isCompiling ? "编译中..." : "编译"}
        </Button>

        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-surface)]">
          <Upload className="h-4 w-4" />
          上传到 {currentFolderLabel}
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

        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-surface)]">
          <FolderPlus className="h-4 w-4" />
          上传目录到 {currentFolderLabel}
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
              await onUploadFiles(files);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="flex gap-2">
          <Input
            value={newFilePath}
            onChange={(event) => setNewFilePath(event.target.value)}
            placeholder="新文件路径，例如 sections/intro.tex"
          />
          <Button
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
    </div>
  );
}
