"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  BookOpen,
  Calendar,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  Loader2,
  Upload,
  Users,
} from "lucide-react";
import {
  type PaperExtractionSubmission,
  uploadPaperFile,
} from "@/lib/api";
import { resolvePublicAssetUrl } from "@/lib/public-assets";
import { cn } from "@/lib/utils";
import { type Paper, useWorkspaceStore } from "@/stores/workspace";

interface PaperItemProps {
  paper: Paper;
  index: number;
}

interface UploadState {
  id: string;
  name: string;
  status: "uploading" | "success" | "error";
  error?: string;
  extraction?: PaperExtractionSubmission | null;
}

function formatExtractionLabel(status: string): string {
  switch (status) {
    case "scheduled":
      return "抽取已排队";
    case "existing":
      return "复用抽取任务";
    case "failed":
      return "抽取排队失败";
    default:
      return status;
  }
}

function isPdfFile(file: File): boolean {
  return /\.pdf$/i.test(file.name) || file.type === "application/pdf";
}

function PaperItem({ paper, index }: PaperItemProps) {
  const fileUrl = resolvePublicAssetUrl(paper.file_url ?? null);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="group rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 transition-all hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-surface)]"
    >
      <h4 className="mb-2 line-clamp-2 text-sm font-medium text-[var(--text-primary)]">
        {paper.title}
      </h4>

      {paper.authors.length > 0 && (
        <div className="mb-1 flex items-center gap-1 text-xs text-[var(--text-secondary)]">
          <Users className="h-3 w-3" />
          <span className="truncate">
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 && ` +${paper.authors.length - 3}`}
          </span>
        </div>
      )}

      <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
        {paper.year && (
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>{paper.year}</span>
          </div>
        )}
        {paper.venue && (
          <div className="flex items-center gap-1">
            <BookOpen className="h-3 w-3" />
            <span className="truncate">{paper.venue}</span>
          </div>
        )}
      </div>

      <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
        <a
          href={fileUrl ?? undefined}
          target="_blank"
          rel="noreferrer"
          aria-disabled={!fileUrl}
          className={cn(
            "flex items-center gap-1 text-xs",
            fileUrl
              ? "text-[var(--accent-primary)] hover:text-[var(--accent-secondary)]"
              : "pointer-events-none text-[var(--text-muted)]"
          )}
        >
          <ExternalLink className="h-3 w-3" />
          {fileUrl ? "View" : "No file"}
        </a>
      </div>
    </motion.div>
  );
}

function UploadStatusCard({ upload }: { upload: UploadState }) {
  const extraction = upload.extraction;
  const isFailed = upload.status === "error" || extraction?.status === "failed";
  const isUploading = upload.status === "uploading";

  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2",
        isFailed
          ? "border-red-500/20 bg-red-500/10"
          : "border-[var(--border-default)] bg-[var(--bg-surface)]/70"
      )}
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex-shrink-0">
          {upload.status === "uploading" ? (
            <Loader2 className="h-4 w-4 animate-spin text-[var(--accent-primary)]" />
          ) : isFailed ? (
            <AlertCircle className="h-4 w-4 text-red-500" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-[var(--text-primary)]">
            {upload.name}
          </p>
          <p
            className={cn(
              "mt-1 text-[11px]",
              isFailed ? "text-red-600/90" : "text-[var(--text-secondary)]"
            )}
          >
            {upload.status === "uploading"
              ? "正在上传并登记到文献中心…"
              : upload.status === "error"
                ? upload.error || "上传失败"
                : "文件已入库"}
          </p>

          {extraction ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                  extraction.status === "failed"
                    ? "bg-red-500/10 text-red-600"
                    : extraction.status === "existing"
                      ? "bg-sky-500/10 text-sky-600"
                      : "bg-amber-500/10 text-amber-600"
                )}
              >
                {extraction.status === "failed" ? (
                  <AlertCircle className="h-3 w-3" />
                ) : extraction.status === "existing" ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <Clock3 className="h-3 w-3" />
                )}
                {formatExtractionLabel(extraction.status)}
              </span>
              {extraction.task_id ? (
                <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                  Task {extraction.task_id.slice(0, 8)}
                </span>
              ) : null}
            </div>
          ) : null}

          {extraction?.message ? (
            <p
              className={cn(
                "mt-2 text-[11px]",
                extraction.status === "failed"
                  ? "text-red-600/90"
                  : "text-[var(--text-secondary)]"
              )}
            >
              {extraction.message}
            </p>
          ) : null}

          {isUploading ? (
            <p className="mt-2 text-[10px] text-[var(--text-muted)]">
              上传成功后会自动刷新文献列表，抽取完成后也会通过 workspace 事件流继续刷新。
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface LiteraturePanelProps {
  workspaceId: string;
}

export function LiteraturePanel({ workspaceId }: LiteraturePanelProps) {
  const { papers, fetchPapers, isPapersLoading } = useWorkspaceStore();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [recentUploads, setRecentUploads] = useState<UploadState[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    if (workspaceId) {
      void fetchPapers(workspaceId);
    }
  }, [workspaceId, fetchPapers]);

  const isUploading = recentUploads.some(
    (upload) => upload.status === "uploading"
  );

  const handleOpenPicker = () => {
    if (isUploading) {
      return;
    }
    fileInputRef.current?.click();
  };

  const handleFileSelection = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    const invalidFile = files.find((file) => !isPdfFile(file));
    if (invalidFile) {
      setUploadError(`仅支持 PDF 文件：${invalidFile.name}`);
      return;
    }

    setUploadError(null);
    let shouldRefreshPapers = false;

    for (const file of files) {
      const uploadId = `${Date.now()}-${file.name}-${Math.random().toString(36).slice(2, 8)}`;
      const pendingUpload: UploadState = {
        id: uploadId,
        name: file.name,
        status: "uploading",
      };
      setRecentUploads((current) => [
        pendingUpload,
        ...current,
      ].slice(0, 6));

      try {
        const response = await uploadPaperFile(workspaceId, file);
        shouldRefreshPapers = true;
        setRecentUploads((current) =>
          current.map((upload) =>
            upload.id === uploadId
              ? {
                  ...upload,
                  status: "success",
                  extraction: response.extraction ?? null,
                }
              : upload
          )
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "上传失败，请稍后再试";
        setRecentUploads((current) =>
          current.map((upload) =>
            upload.id === uploadId
              ? {
                  ...upload,
                  status: "error",
                  error: message,
                }
              : upload
          )
        );
        setUploadError(message);
      }
    }

    if (shouldRefreshPapers) {
      await fetchPapers(workspaceId);
    }
  };

  return (
    <div className="flex h-full w-[320px] flex-col border-l border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
      <div className="border-b border-[var(--border-default)] p-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
            <FileText className="h-5 w-5 text-[var(--accent-primary)]" />
            Literature
          </h2>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleOpenPicker}
            disabled={isUploading}
            className={cn(
              "rounded-lg p-2 transition-colors",
              "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20",
              "disabled:cursor-not-allowed disabled:opacity-60"
            )}
          >
            <Upload className="h-4 w-4" />
          </motion.button>
        </div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {papers.length} paper{papers.length !== 1 ? "s" : ""} in workspace
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          上传 PDF 后会自动进入文献中心，并尽力自动触发一级抽取。
        </p>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleFileSelection}
          className="hidden"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {uploadError ? (
          <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-600">
            {uploadError}
          </div>
        ) : null}

        {recentUploads.length > 0 ? (
          <div className="mb-3 space-y-2">
            {recentUploads.map((upload) => (
              <UploadStatusCard key={upload.id} upload={upload} />
            ))}
          </div>
        ) : null}

        <AnimatePresence mode="popLayout">
          {isPapersLoading ? (
            <div className="flex items-center justify-center py-8">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="h-6 w-6 rounded-full border-2 border-[var(--accent-primary)] border-t-transparent"
              />
            </div>
          ) : papers.length === 0 ? (
            <div className="py-8 text-center">
              <FileText className="mx-auto mb-2 h-10 w-10 text-[var(--text-muted)]" />
              <p className="text-sm text-[var(--text-secondary)]">
                No papers yet
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Upload papers to build your reference library
              </p>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleOpenPicker}
                disabled={isUploading}
                className={cn(
                  "mt-4 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                  "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20",
                  "disabled:cursor-not-allowed disabled:opacity-60"
                )}
              >
                <Upload className="mr-2 inline h-4 w-4" />
                Upload Paper
              </motion.button>
            </div>
          ) : (
            <div className="space-y-2">
              {papers.map((paper, index) => (
                <PaperItem key={paper.id} paper={paper} index={index} />
              ))}
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
