"use client";

import type { ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Artifact } from "@/stores/workspace";
import {
  extractArtifactFileUrl,
  isImageUrl,
  isPdfUrl,
} from "@/lib/public-assets";

interface ArtifactDetailDialogProps {
  artifact: Artifact | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatLabel(key: string): string {
  return key.replace(/[_-]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPrimitive(value: string | number | boolean | null): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function renderContent(value: unknown, depth: number = 0): ReactNode {
  if (value === null || value === undefined) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        暂无内容
      </p>
    );
  }

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return (
      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
        {formatPrimitive(value)}
      </p>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    const primitiveArray = value.every(
      (item) =>
        item === null ||
        ["string", "number", "boolean"].includes(typeof item)
    );
    if (primitiveArray) {
      return (
        <div className="flex flex-wrap gap-2">
          {value.map((item, index) => (
            <span
              key={`${formatPrimitive(item as string | number | boolean | null)}-${index}`}
              className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
            >
              {formatPrimitive(item as string | number | boolean | null)}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div
            key={index}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium text-[var(--text-primary)]">
              {Array.isArray(item)
                ? `Item ${index + 1}`
                : typeof item === "object" && item
                  ? formatPrimitive(
                      ((item as Record<string, unknown>).title ??
                        (item as Record<string, unknown>).name ??
                        (item as Record<string, unknown>).id ??
                        `Item ${index + 1}`) as
                        | string
                        | number
                        | boolean
                        | null
                    )
                  : `Item ${index + 1}`}
            </p>
            {renderContent(item, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    if (depth >= 3) {
      return (
        <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, entryValue]) => entryValue !== undefined
    );
    if (entries.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    return (
      <div className="space-y-3">
        {entries.map(([key, entryValue]) => (
          <div
            key={key}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-primary)]">
              {formatLabel(key)}
            </p>
            {renderContent(entryValue, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function ArtifactDetailDialog({
  artifact,
  open,
  onOpenChange,
}: ArtifactDetailDialogProps) {
  const content =
    artifact?.content && typeof artifact.content === "object"
      ? (artifact.content as Record<string, unknown>)
      : null;
  const fileUrl = extractArtifactFileUrl(content);
  const showPdfPreview = isPdfUrl(fileUrl);
  const showImagePreview = isImageUrl(fileUrl);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {artifact?.title || (artifact ? `未命名 ${artifact.type}` : "产出详情")}
          </DialogTitle>
          <DialogDescription>
            {artifact
              ? `${artifact.type} · ${new Date(artifact.created_at).toLocaleString("zh-CN")}`
              : "查看工作区产出详情"}
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-y-auto pr-1">
          {fileUrl && (
            <div className="mb-4 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
              <div className="flex flex-wrap items-center gap-3">
                <a
                  href={fileUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-md bg-[var(--accent-primary)] px-3 py-1.5 text-sm text-white"
                >
                  打开文件
                </a>
                <a
                  href={fileUrl}
                  download
                  className="rounded-md border border-[var(--border-default)] px-3 py-1.5 text-sm text-[var(--text-secondary)]"
                >
                  下载文件
                </a>
                <span className="text-xs text-[var(--text-muted)] break-all">
                  {fileUrl}
                </span>
              </div>
            </div>
          )}

          {showPdfPreview && (
            <div className="mb-4 overflow-hidden rounded-lg border border-[var(--border-default)] bg-white">
              <iframe
                src={fileUrl ?? undefined}
                title={artifact?.title || "PDF Preview"}
                className="h-[540px] w-full"
              />
            </div>
          )}

          {showImagePreview && (
            <div className="mb-4 overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={fileUrl!}
                alt={artifact?.title || "Artifact Preview"}
                className="max-h-[540px] w-full rounded-lg object-contain"
              />
            </div>
          )}

          {artifact ? renderContent(artifact.content) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
