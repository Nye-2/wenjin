import { Trash2 } from "lucide-react";

import { LatexFileTree } from "@/components/latex/LatexFileTree";
import { LatexToolbar } from "@/components/latex/LatexToolbar";
import { Button } from "@/components/ui/button";
import type { LatexCompileEngine, LatexFileItem } from "@/lib/api";

export function LatexResourceRail({
  tree,
  selectedPath,
  engine,
  isSaving,
  isCompiling,
  isProjectLoading,
  isDeletingProject,
  projectName,
  currentFolderLabel,
  engineHint,
  onOpenFile,
  onSelectPath,
  onRenamePath,
  onDeletePath,
  onReorder,
  onEngineChange,
  onSave,
  onCompile,
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  onUploadDirectory,
  onUploadArchive,
  onDeleteProject,
}: {
  tree: LatexFileItem[];
  selectedPath: string | null;
  engine: LatexCompileEngine;
  isSaving: boolean;
  isCompiling: boolean;
  isProjectLoading: boolean;
  isDeletingProject: boolean;
  projectName?: string | null;
  currentFolderLabel: string;
  engineHint: string;
  onOpenFile: (path: string) => void;
  onSelectPath: (path: string, type: "file" | "dir") => void;
  onRenamePath: (fromPath: string, toPath: string) => Promise<void>;
  onDeletePath: (path: string) => Promise<void>;
  onReorder: (folder: string, order: string[]) => Promise<void>;
  onEngineChange: (engine: LatexCompileEngine) => void;
  onSave: () => void;
  onCompile: () => void;
  onCreateFile: (path: string) => Promise<void>;
  onCreateFolder: (path: string) => Promise<void>;
  onUploadFiles: (files: File[]) => Promise<void>;
  onUploadDirectory: (files: File[]) => Promise<void>;
  onUploadArchive: (archive: File) => Promise<void>;
  onDeleteProject: () => Promise<void>;
}) {
  return (
    <aside className="hidden w-[260px] shrink-0 flex-col border-r border-[var(--wjn-line)] bg-[var(--wjn-bg-rail)] lg:flex">
      <div className="flex h-12 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <p className="text-xs font-semibold text-[var(--wjn-text-secondary)]">资源</p>
        <span className="text-[11px] text-[var(--wjn-text-muted)]">
          {tree.length} 项
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">
        <LatexFileTree
          items={tree}
          selectedPath={selectedPath}
          onOpenFile={onOpenFile}
          onSelectPath={onSelectPath}
          onRenamePath={onRenamePath}
          onDeletePath={onDeletePath}
          onReorder={onReorder}
        />
      </div>
      <div className="border-t border-[var(--wjn-line)] p-2">
        <details>
          <summary className="cursor-pointer rounded-[var(--wjn-radius)] px-2 py-1 text-xs text-[var(--wjn-text-muted)] hover:bg-white">
            文件操作
          </summary>
          <div className="mt-2">
            <LatexToolbar
              engine={engine}
              onEngineChange={onEngineChange}
              onSave={onSave}
              onCompile={onCompile}
              onCreateFile={onCreateFile}
              onCreateFolder={onCreateFolder}
              onUploadFiles={onUploadFiles}
              onUploadDirectory={onUploadDirectory}
              onUploadArchive={onUploadArchive}
              isSaving={isSaving}
              isCompiling={isCompiling}
              disableActions={isProjectLoading}
              currentFolderLabel={currentFolderLabel}
              engineHint={engineHint}
            />
          </div>
        </details>
        <Button
          variant="destructive"
          size="sm"
          className="mt-2 w-full"
          disabled={!projectName || isDeletingProject || isProjectLoading}
          onClick={() => void onDeleteProject()}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          {isDeletingProject ? "删除中..." : "删除项目"}
        </Button>
      </div>
    </aside>
  );
}
