"use client";

import { useEffect, useState, type ReactNode } from "react";
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
  getSignedAssetUrl,
  isImageUrl,
  isPdfUrl,
  openAuthorizedAsset,
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
      <p className="text-sm text-[var(--wjn-text-muted)]">
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
      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--wjn-text-secondary)]">
        {formatPrimitive(value)}
      </p>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="text-sm text-[var(--wjn-text-muted)]">暂无内容</p>;
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
              className="rounded-full bg-[var(--wjn-surface)] px-2.5 py-1 text-xs text-[var(--wjn-text-secondary)]"
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
            className="rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-3"
          >
            <p className="mb-2 text-xs font-medium text-[var(--wjn-text)]">
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
        <pre className="overflow-x-auto rounded-lg bg-[var(--wjn-surface)] p-3 text-xs leading-6 text-[var(--wjn-text-secondary)]">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, entryValue]) => entryValue !== undefined
    );
    if (entries.length === 0) {
      return <p className="text-sm text-[var(--wjn-text-muted)]">暂无内容</p>;
    }

    return (
      <div className="space-y-3">
        {entries.map(([key, entryValue]) => (
          <div
            key={key}
            className="rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-3"
          >
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--wjn-text)]">
              {formatLabel(key)}
            </p>
            {renderContent(entryValue, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-lg bg-[var(--wjn-surface)] p-3 text-xs leading-6 text-[var(--wjn-text-secondary)]">
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
  const [signedFileUrl, setSignedFileUrl] = useState<string | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    if (!open || !fileUrl) {
      const resetHandle = window.setTimeout(() => {
        if (!cancelled) {
          setSignedFileUrl(null);
          setAssetError(null);
        }
      }, 0);
      return () => {
        cancelled = true;
        window.clearTimeout(resetHandle);
      };
    }

    const startHandle = window.setTimeout(() => {
      if (cancelled) {
        return;
      }
      setAssetError(null);
      void getSignedAssetUrl(fileUrl)
        .then((value) => {
          if (!cancelled) {
            setSignedFileUrl(value);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setSignedFileUrl(null);
            setAssetError(
              error instanceof Error ? error.message : "生成文件访问链接失败"
            );
          }
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(startHandle);
    };
  }, [fileUrl, open]);

  const showPdfPreview = isPdfUrl(signedFileUrl);
  const showImagePreview = isImageUrl(signedFileUrl);

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
            <div className="mb-4 rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void openAuthorizedAsset(fileUrl)}
                  className="rounded-md bg-[var(--wjn-navy)] px-3 py-1.5 text-sm text-white"
                >
                  打开文件
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void openAuthorizedAsset(
                      `${fileUrl}${fileUrl.includes("?") ? "&" : "?"}download=true`
                    )
                  }
                  className="rounded-md border border-[var(--wjn-line)] px-3 py-1.5 text-sm text-[var(--wjn-text-secondary)]"
                >
                  下载文件
                </button>
                <span className="text-xs text-[var(--wjn-text-muted)] break-all">
                  {signedFileUrl ?? fileUrl}
                </span>
              </div>
              {assetError ? (
                <p className="mt-2 text-xs text-red-600">{assetError}</p>
              ) : null}
            </div>
          )}

          {showPdfPreview && (
            <div className="mb-4 overflow-hidden rounded-lg border border-[var(--wjn-line)] bg-white">
              <iframe
                src={signedFileUrl ?? undefined}
                title={artifact?.title || "PDF Preview"}
                className="h-[540px] w-full"
              />
            </div>
          )}

          {showImagePreview && (
            <div className="mb-4 overflow-hidden rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={signedFileUrl!}
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
