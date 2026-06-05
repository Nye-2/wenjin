import { Trash2 } from "lucide-react";

import { LatexFileTree } from "@/components/latex/LatexFileTree";
import { LatexToolbar } from "@/components/latex/LatexToolbar";
import { DisclosureSection } from "@/components/ui/disclosure-section";
import { OverflowMenu } from "@/components/ui/overflow-menu";
import type { LatexFileItem } from "@/lib/api";

export function LatexResourceRail({
  tree,
  selectedPath,
  isProjectLoading,
  isDeletingProject,
  projectName,
  currentFolderLabel,
  onOpenFile,
  onSelectPath,
  onRenamePath,
  onDeletePath,
  onReorder,
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  onUploadDirectory,
  onUploadArchive,
  onDeleteProject,
}: {
  tree: LatexFileItem[];
  selectedPath: string | null;
  isProjectLoading: boolean;
  isDeletingProject: boolean;
  projectName?: string | null;
  currentFolderLabel: string;
  onOpenFile: (path: string) => void;
  onSelectPath: (path: string, type: "file" | "dir") => void;
  onRenamePath: (fromPath: string, toPath: string) => Promise<void>;
  onDeletePath: (path: string) => Promise<void>;
  onReorder: (folder: string, order: string[]) => Promise<void>;
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
        <div className="mb-2 flex items-center justify-between gap-2 px-1">
          <p className="text-xs font-semibold text-[var(--wjn-text-secondary)]">
            文件
          </p>
          <OverflowMenu
            items={[
              {
                label: isDeletingProject ? "删除中..." : "删除项目",
                icon: Trash2,
                tone: "danger",
                disabled: !projectName || isDeletingProject || isProjectLoading,
                onClick: () => void onDeleteProject(),
              },
            ]}
          />
        </div>
        <DisclosureSection label="添加文件">
          <LatexToolbar
            onCreateFile={onCreateFile}
            onCreateFolder={onCreateFolder}
            onUploadFiles={onUploadFiles}
            onUploadDirectory={onUploadDirectory}
            onUploadArchive={onUploadArchive}
            disableActions={isProjectLoading}
            currentFolderLabel={currentFolderLabel}
          />
        </DisclosureSection>
      </div>
    </aside>
  );
}
