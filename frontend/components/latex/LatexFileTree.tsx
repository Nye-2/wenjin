"use client";

import { useEffect, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileImage,
  FilePenLine,
  FileText,
  Folder,
  FolderOpen,
  GripVertical,
  MoreHorizontal,
  Trash2,
} from "lucide-react";

import type { LatexFileItem } from "@/lib/api";

interface TreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children: TreeNode[];
}

interface LatexFileTreeProps {
  items: LatexFileItem[];
  selectedPath: string | null;
  onOpenFile: (path: string) => void;
  onSelectPath: (path: string, type: "file" | "dir") => void;
  onRenamePath: (fromPath: string, toPath: string) => Promise<void>;
  onDeletePath: (path: string) => Promise<void>;
  onReorder: (folder: string, order: string[]) => Promise<void>;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
  name: string;
}

function buildTree(items: LatexFileItem[]): TreeNode {
  const root: TreeNode = { name: "", path: "", type: "dir", children: [] };
  const nodeMap = new Map<string, TreeNode>([["", root]]);

  for (const item of items) {
    const parts = item.path.split("/").filter(Boolean);
    let currentPath = "";
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      const nextPath = currentPath ? `${currentPath}/${part}` : part;
      if (!nodeMap.has(nextPath)) {
        const isLeaf = index === parts.length - 1;
        const node: TreeNode = {
          name: part,
          path: nextPath,
          type: isLeaf ? item.type : "dir",
          children: [],
        };
        nodeMap.get(currentPath)?.children.push(node);
        nodeMap.set(nextPath, node);
      }
      currentPath = nextPath;
    }
  }

  return root;
}

function fileIcon(path: string): "image" | "code" | "text" {
  const lower = path.toLowerCase();
  if ([".png", ".jpg", ".jpeg", ".svg", ".pdf", ".webp", ".gif"].some((suffix) => lower.endsWith(suffix))) {
    return "image";
  }
  if ([".tex", ".bib", ".cls", ".sty"].some((suffix) => lower.endsWith(suffix))) {
    return "code";
  }
  return "text";
}

function renderFileIcon(kind: "folder" | "folder-open" | "image" | "code" | "text") {
  if (kind === "folder") {
    return <Folder className="h-4 w-4 shrink-0" />;
  }
  if (kind === "folder-open") {
    return <FolderOpen className="h-4 w-4 shrink-0" />;
  }
  if (kind === "image") {
    return <FileImage className="h-4 w-4 shrink-0" />;
  }
  if (kind === "code") {
    return <FileCode2 className="h-4 w-4 shrink-0" />;
  }
  return <FileText className="h-4 w-4 shrink-0" />;
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function joinRenamedPath(path: string, nextName: string): string {
  const parts = path.split("/");
  parts[parts.length - 1] = nextName;
  return parts.join("/");
}

function FileTreeRow({
  node,
  parentFolder,
  siblingPaths,
  level,
  selectedPath,
  expanded,
  setExpanded,
  editingPath,
  editingValue,
  setEditingPath,
  setEditingValue,
  setContextMenu,
  onOpenFile,
  onSelectPath,
  onRenamePath,
  onDeletePath,
  onReorder,
}: {
  node: TreeNode;
  parentFolder: string;
  siblingPaths: string[];
  level: number;
  selectedPath: string | null;
  expanded: Record<string, boolean>;
  setExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  editingPath: string | null;
  editingValue: string;
  setEditingPath: React.Dispatch<React.SetStateAction<string | null>>;
  setEditingValue: React.Dispatch<React.SetStateAction<string>>;
  setContextMenu: React.Dispatch<React.SetStateAction<ContextMenuState | null>>;
  onOpenFile: (path: string) => void;
  onSelectPath: (path: string, type: "file" | "dir") => void;
  onRenamePath: (fromPath: string, toPath: string) => Promise<void>;
  onDeletePath: (path: string) => Promise<void>;
  onReorder: (folder: string, order: string[]) => Promise<void>;
}) {
  const isDirectory = node.type === "dir";
  const hasChildren = node.children.length > 0;
  const isExpanded = expanded[node.path] ?? level < 1;
  const isActive = selectedPath === node.path;
  const iconKind = isDirectory
    ? (isExpanded ? "folder-open" : "folder")
    : fileIcon(node.path);
  const isEditing = editingPath === node.path;

  async function commitRename() {
    const nextName = editingValue.trim();
    if (!nextName || nextName === node.name) {
      setEditingPath(null);
      setEditingValue("");
      return;
    }
    await onRenamePath(node.path, joinRenamedPath(node.path, nextName));
    setEditingPath(null);
    setEditingValue("");
  }

  return (
    <div>
      <button
        type="button"
        draggable={node.path.length > 0}
        onContextMenu={(event) => {
          event.preventDefault();
          setContextMenu({
            x: event.clientX,
            y: event.clientY,
            path: node.path,
            name: node.name,
          });
          onSelectPath(node.path, node.type);
        }}
        onDragStart={(event) => {
          event.dataTransfer.setData("text/plain", node.path);
        }}
        onDragOver={(event) => {
          if (siblingPaths.length > 1) {
            event.preventDefault();
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          const draggedPath = event.dataTransfer.getData("text/plain");
          if (!draggedPath || draggedPath === node.path || !siblingPaths.includes(draggedPath)) {
            return;
          }
          const nextOrder = siblingPaths.filter((path) => path !== draggedPath);
          const targetIndex = nextOrder.indexOf(node.path);
          nextOrder.splice(targetIndex, 0, draggedPath);
          void onReorder(
            parentFolder,
            nextOrder.map((path) => basename(path)),
          );
        }}
        onClick={() => {
          onSelectPath(node.path, node.type);
          if (isDirectory) {
            setExpanded((current) => ({
              ...current,
              [node.path]: !isExpanded,
            }));
            return;
          }
          onOpenFile(node.path);
        }}
        className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition-colors ${
          isActive
            ? "bg-[rgba(31,66,99,0.08)] text-[var(--brand-navy)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
        }`}
        style={{ paddingLeft: `${12 + level * 16}px` }}
      >
        <GripVertical className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
        {isDirectory ? (
          hasChildren ? (
            isExpanded ? (
              <ChevronDown className="h-4 w-4 shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0" />
            )
          ) : (
            <span className="h-4 w-4 shrink-0" />
          )
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        {renderFileIcon(iconKind)}
        {isEditing ? (
          <input
            autoFocus
            value={editingValue}
            onChange={(event) => setEditingValue(event.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void commitRename();
              }
              if (event.key === "Escape") {
                setEditingPath(null);
                setEditingValue("");
              }
            }}
            className="min-w-0 flex-1 rounded-md border border-[var(--border-default)] bg-white px-2 py-1 text-sm"
            onClick={(event) => event.stopPropagation()}
          />
        ) : (
          <span className="truncate">{node.name}</span>
        )}
        {node.path ? (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <span
                onClick={(event) => event.stopPropagation()}
                className="ml-auto rounded-md p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface)] hover:text-[var(--brand-navy)]"
              >
                <MoreHorizontal className="h-4 w-4" />
              </span>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                sideOffset={6}
                className="z-50 min-w-[140px] rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1 shadow-[0_12px_32px_rgba(19,34,53,0.14)]"
              >
                <DropdownMenu.Item
                  onSelect={() => {
                    setEditingPath(node.path);
                    setEditingValue(node.name);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none transition-colors hover:bg-[var(--bg-surface)]"
                >
                  <FilePenLine className="h-4 w-4" />
                  重命名
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  onSelect={() => {
                    if (!window.confirm(`确认删除 ${node.name} 吗？`)) {
                      return;
                    }
                    void onDeletePath(node.path);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-600 outline-none transition-colors hover:bg-red-500/10"
                >
                  <Trash2 className="h-4 w-4" />
                  删除
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        ) : null}
      </button>

      {isDirectory && isExpanded
        ? node.children.map((child) => (
            <FileTreeRow
              key={child.path}
              node={child}
              parentFolder={node.path}
              siblingPaths={node.children.map((item) => item.path)}
              level={level + 1}
              selectedPath={selectedPath}
              expanded={expanded}
              setExpanded={setExpanded}
              editingPath={editingPath}
              editingValue={editingValue}
              setEditingPath={setEditingPath}
              setEditingValue={setEditingValue}
              setContextMenu={setContextMenu}
              onOpenFile={onOpenFile}
              onSelectPath={onSelectPath}
              onRenamePath={onRenamePath}
              onDeletePath={onDeletePath}
              onReorder={onReorder}
            />
          ))
        : null}
    </div>
  );
}

export function LatexFileTree({
  items,
  selectedPath,
  onOpenFile,
  onSelectPath,
  onRenamePath,
  onDeletePath,
  onReorder,
}: LatexFileTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const root = buildTree(items);

  useEffect(() => {
    if (!contextMenu) {
      return;
    }
    function dismiss() {
      setContextMenu(null);
    }
    window.addEventListener("click", dismiss);
    window.addEventListener("contextmenu", dismiss);
    window.addEventListener("keydown", dismiss);
    return () => {
      window.removeEventListener("click", dismiss);
      window.removeEventListener("contextmenu", dismiss);
      window.removeEventListener("keydown", dismiss);
    };
  }, [contextMenu]);

  return (
    <div className="space-y-1.5">
      {root.children.map((node) => (
        <FileTreeRow
          key={node.path}
          node={node}
          parentFolder=""
          siblingPaths={root.children.map((item) => item.path)}
          level={0}
          selectedPath={selectedPath}
          expanded={expanded}
          setExpanded={setExpanded}
          editingPath={editingPath}
          editingValue={editingValue}
          setEditingPath={setEditingPath}
          setEditingValue={setEditingValue}
          setContextMenu={setContextMenu}
          onOpenFile={onOpenFile}
          onSelectPath={onSelectPath}
          onRenamePath={onRenamePath}
          onDeletePath={onDeletePath}
          onReorder={onReorder}
        />
      ))}
      {contextMenu ? (
        <div
          className="fixed z-[80] min-w-[150px] rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1 shadow-[0_12px_32px_rgba(19,34,53,0.14)]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            onClick={() => {
              setEditingPath(contextMenu.path);
              setEditingValue(contextMenu.name);
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--bg-surface)]"
          >
            <FilePenLine className="h-4 w-4" />
            重命名
          </button>
          <button
            type="button"
            onClick={() => {
              setContextMenu(null);
              if (!window.confirm(`确认删除 ${contextMenu.name} 吗？`)) {
                return;
              }
              void onDeletePath(contextMenu.path);
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-600 hover:bg-red-500/10"
          >
            <Trash2 className="h-4 w-4" />
            删除
          </button>
        </div>
      ) : null}
    </div>
  );
}
