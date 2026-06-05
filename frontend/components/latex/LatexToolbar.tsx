"use client";

import { useEffect, useRef, useState } from "react";
import { Archive, FolderPlus, SquarePen, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface LatexToolbarProps {
  onCreateFile: (path: string) => Promise<void>;
  onCreateFolder: (path: string) => Promise<void>;
  onUploadFiles: (files: File[]) => Promise<void>;
  onUploadDirectory: (files: File[]) => Promise<void>;
  onUploadArchive: (archive: File) => Promise<void>;
  disableActions: boolean;
  currentFolderLabel: string;
}

export function LatexToolbar({
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  onUploadDirectory,
  onUploadArchive,
  disableActions,
  currentFolderLabel,
}: LatexToolbarProps) {
  const [newFilePath, setNewFilePath] = useState("");
  const [newFolderPath, setNewFolderPath] = useState("");
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);
  const fileActionLabelClass = cn(
    "inline-flex cursor-pointer items-center gap-2 rounded-md border border-[var(--wjn-line)] bg-white/70 px-2.5 py-1.5 text-xs text-[var(--wjn-text)] transition-colors hover:bg-white",
    disableActions && "pointer-events-none cursor-not-allowed opacity-50",
  );

  useEffect(() => {
    if (!directoryInputRef.current) {
      return;
    }
    directoryInputRef.current.setAttribute("webkitdirectory", "");
    directoryInputRef.current.setAttribute("directory", "");
  }, []);

  return (
    <div className="rounded-lg border border-white/50 bg-white/75 p-3 shadow-sm">
      <div className="mb-2 text-[11px] leading-5 text-[var(--wjn-text-muted)]">
        添加到 {currentFolderLabel}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label
          aria-disabled={disableActions}
          className={fileActionLabelClass}
        >
          <Upload className="h-4 w-4" />
          上传文件
          <input
            type="file"
            multiple
            disabled={disableActions}
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

        <label
          aria-disabled={disableActions}
          className={fileActionLabelClass}
        >
          <FolderPlus className="h-4 w-4" />
          上传目录
          <input
            ref={directoryInputRef}
            type="file"
            multiple
            disabled={disableActions}
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

        <label
          aria-disabled={disableActions}
          className={fileActionLabelClass}
        >
          <Archive className="h-4 w-4" />
          上传 ZIP
          <input
            type="file"
            accept=".zip,application/zip"
            disabled={disableActions}
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

      <div className="mt-2 grid gap-2">
        <div className="grid gap-1.5">
          <Input
            value={newFilePath}
            onChange={(event) => setNewFilePath(event.target.value)}
            aria-label="新文件路径"
            placeholder="新文件路径，例如 sections/intro.tex"
          />
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
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

        <div className="grid gap-1.5">
          <Input
            value={newFolderPath}
            onChange={(event) => setNewFolderPath(event.target.value)}
            aria-label="新文件夹路径"
            placeholder="新目录路径，例如 sections/appendix"
          />
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
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
