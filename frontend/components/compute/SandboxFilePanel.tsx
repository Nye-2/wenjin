"use client";

import { FolderOpen, ExternalLink } from "lucide-react";
import { readString, fileLabel, fileMeta, sandboxStatusLabel } from "./utils";
import type { ComputeFileProjection } from "@/lib/api";

interface SandboxFilePanelProps {
  files: ComputeFileProjection[];
  sandbox: {
    status?: string | null;
    session_id?: string | null;
    required?: boolean;
  } | null;
}

export function SandboxFilePanel({ files, sandbox }: SandboxFilePanelProps) {
  return (
    <section className="compute-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FolderOpen className="h-4 w-4 text-compute-cyan" />
          <h4 className="text-sm font-semibold text-compute-text-primary">
            Sandbox 文件
          </h4>
        </div>
        <span className="shrink-0 text-[11px] text-compute-text-muted">
          {sandboxStatusLabel(sandbox?.status)}
        </span>
      </div>
      {readString(sandbox?.session_id) ? (
        <p className="mt-2 truncate text-[11px] text-compute-text-muted">
          {readString(sandbox?.session_id)}
        </p>
      ) : null}
      {sandbox?.required && !readString(sandbox?.session_id) ? (
        <p className="mt-2 rounded-lg border border-compute-gold/20 bg-compute-gold/10 px-2.5 py-2 text-[11px] text-compute-gold">
          当前 feature runtime profile 要求 sandbox；等待执行环境绑定或产出文件。
        </p>
      ) : null}
      <div className="mt-3 space-y-2">
        {files.length > 0 ? (
          files.slice(0, 8).map((file) => {
            const label = fileLabel(file);
            const url = readString(file.url);
            const path = readString(file.path);
            return (
              <div
                key={file.id}
                className="rounded-xl border border-compute-border bg-compute-surface px-3 py-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-compute-text-primary">
                      {label}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-compute-text-muted">
                      {fileMeta(file)}
                    </p>
                  </div>
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="shrink-0 rounded-md border border-compute-border p-1.5 text-compute-text-secondary hover:border-compute-cyan hover:text-compute-cyan"
                      title="打开文件"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </div>
                {path && path !== label ? (
                  <p className="mt-1 line-clamp-2 break-all text-[11px] leading-5 text-compute-text-secondary">
                    {path}
                  </p>
                ) : null}
              </div>
            );
          })
        ) : (
          <p className="rounded-xl border border-dashed border-compute-border px-3 py-4 text-center text-xs text-compute-text-muted">
            当前执行没有发布 sandbox 文件。
          </p>
        )}
      </div>
    </section>
  );
}
