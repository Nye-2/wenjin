"use client";

import { BookOpen, ExternalLink, RotateCcw } from "lucide-react";
import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { readString, readFileChangeKey, prismStatusLabel, formatShortId } from "./utils";
import type { ComputePrismProjection, LatexFileChangePreviewResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface PrismPanelProps {
  prism: ComputePrismProjection | null;
  resolvingKey: string | null;
  previewingKey: string | null;
  revertingKey: string | null;
  previewByKey: Record<string, LatexFileChangePreviewResponse>;
  onPreview: (change: Record<string, unknown>) => void;
  onApply: (change: Record<string, unknown>) => void;
  onDiscard: (change: Record<string, unknown>) => void;
  onRevert: (change: Record<string, unknown>) => void;
}

export function PrismPanel({
  prism,
  resolvingKey,
  previewingKey,
  revertingKey,
  previewByKey,
  onPreview,
  onApply,
  onDiscard,
  onRevert,
}: PrismPanelProps) {
  return (
    <section className="compute-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-compute-cyan" />
          <h4 className="text-sm font-semibold text-compute-text-primary">
            WenjinPrism
          </h4>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            prism?.status === "ready"
              ? "border-compute-green/25 bg-compute-green/10 text-compute-green"
              : prism?.status === "compile_failed"
                ? "border-compute-red/25 bg-compute-red/10 text-compute-red"
                : prism?.status === "pending_changes"
                  ? "border-compute-gold/25 bg-compute-gold/10 text-compute-gold"
                  : "border-compute-border bg-compute-elevated text-compute-text-secondary"
          )}
        >
          {prismStatusLabel(prism?.status)}
        </span>
      </div>

      {readString(prism?.project_id) ? (
        <div className="mt-3 rounded-xl border border-compute-border bg-compute-surface px-3 py-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-compute-text-primary">
                {formatShortId(readString(prism?.project_id))}
              </p>
              <p className="mt-0.5 truncate text-[11px] text-compute-text-muted">
                {readString(prism?.main_file) ?? "main.tex"}
              </p>
            </div>
            {readString(prism?.url) ? (
              <a
                href={readString(prism?.url) ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded-md border border-compute-border p-1.5 text-compute-text-secondary hover:border-compute-cyan hover:text-compute-cyan"
                title="打开 WenjinPrism"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="mt-3 rounded-xl border border-dashed border-compute-border px-3 py-4 text-center text-xs text-compute-text-muted">
          当前执行未关联 WenjinPrism 主稿工程。
        </p>
      )}

      {prism?.target_files?.length ? (
        <div className="mt-3 space-y-1.5">
          {prism.target_files.slice(0, 5).map((path) => (
            <p
              key={path}
              className="truncate rounded-lg bg-compute-surface px-2.5 py-1.5 text-[11px] text-compute-text-secondary"
            >
              {path}
            </p>
          ))}
        </div>
      ) : null}

      {prism?.compile?.status ? (
        <p className="mt-3 truncate text-[11px] text-compute-text-muted">
          编译：{prism.compile.status}
          {typeof prism.compile.page_count === "number"
            ? ` · ${prism.compile.page_count} 页`
            : ""}
        </p>
      ) : null}

      {/* Pending file changes */}
      {prism?.file_changes?.length ? (
        <div className="mt-3 rounded-xl border border-compute-gold/20 bg-compute-gold/8 px-3 py-2">
          <p className="text-xs font-medium text-compute-gold">
            主稿待确认写入 {prism.file_changes.length}
          </p>
          <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-compute-gold/80">
            {prism.file_changes
              .map((item) => readString(item.path) ?? readString(item.logical_key))
              .filter(Boolean)
              .slice(0, 3)
              .join(", ")}
          </p>
          <div className="mt-2 space-y-2">
            {prism.file_changes.slice(0, 3).map((change) => {
              const logicalKey = readFileChangeKey(change);
              const isResolving = logicalKey !== null && resolvingKey === logicalKey;
              const isPreviewing = logicalKey !== null && previewingKey === logicalKey;
              const preview = logicalKey ? previewByKey[logicalKey] ?? null : null;
              return (
                <div
                  key={logicalKey ?? readString(change.path) ?? "file-change"}
                  className="rounded-lg bg-compute-base/60 px-2.5 py-2"
                >
                  <p className="truncate text-[11px] font-medium text-compute-text-primary">
                    {readString(change.path) ??
                      readString(change.logical_key) ??
                      "未命名写入"}
                  </p>
                  <p className="mt-1 truncate text-[10px] text-compute-text-muted">
                    {readString(change.reason) ?? "feature_proposal"}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!logicalKey || isResolving || isPreviewing}
                      onClick={() => onPreview(change)}
                      className="rounded-md border border-compute-gold/25 bg-compute-elevated px-2 py-1 text-[11px] font-medium text-compute-text-primary hover:border-compute-gold/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isPreviewing
                        ? "预览中..."
                        : preview
                          ? "刷新 diff"
                          : "预览 diff"}
                    </button>
                    <button
                      type="button"
                      disabled={!logicalKey || isResolving}
                      onClick={() => onDiscard(change)}
                      className="rounded-md border border-compute-gold/25 bg-compute-elevated px-2 py-1 text-[11px] font-medium text-compute-text-primary hover:border-compute-gold/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      忽略本次
                    </button>
                    <button
                      type="button"
                      disabled={!logicalKey || isResolving}
                      onClick={() => onApply(change)}
                      className="rounded-md border border-compute-gold/25 bg-compute-gold/10 px-2 py-1 text-[11px] font-medium text-compute-gold hover:border-compute-gold/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      应用到主稿
                    </button>
                  </div>
                  {preview ? (
                    <LatexFileChangeDiffPreview
                      preview={preview}
                      maxOps={4}
                      className="mt-2"
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Applied file changes */}
      {prism?.applied_file_changes?.length ? (
        <div className="mt-3 rounded-xl border border-compute-green/20 bg-compute-green/8 px-3 py-2">
          <p className="text-xs font-medium text-compute-green">
            已写入主稿 {prism.applied_file_changes.length}
          </p>
          <div className="mt-2 space-y-2">
            {prism.applied_file_changes.slice(0, 3).map((change) => {
              const logicalKey = readFileChangeKey(change);
              const revertSignature = readString(change.revert_signature);
              const isReverting = logicalKey !== null && revertingKey === logicalKey;
              return (
                <div
                  key={logicalKey ?? readString(change.path) ?? "applied-file-change"}
                  className="rounded-lg bg-compute-base/60 px-2.5 py-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-medium text-compute-text-primary">
                        {readString(change.path) ??
                          readString(change.logical_key) ??
                          "未命名写入"}
                      </p>
                      <p className="mt-1 truncate text-[10px] text-compute-text-muted">
                        {readString(change.applied_hash) ?? "applied"}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={!logicalKey || !revertSignature || isReverting}
                      onClick={() => onRevert(change)}
                      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-compute-green/25 bg-compute-elevated px-2 py-1 text-[11px] font-medium text-compute-text-primary hover:border-compute-green/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RotateCcw className="h-3 w-3" />
                      {isReverting ? "撤回中..." : "撤回"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}
