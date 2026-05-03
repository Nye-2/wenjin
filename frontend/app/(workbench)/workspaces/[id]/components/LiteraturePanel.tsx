"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Info,
  Loader2,
  Upload,
  Users,
} from "lucide-react";
import {
  getReferenceOutline,
  syncReferenceBibtexToPrism,
  type ReferenceAsset,
  type ReferencePreprocessSubmission,
  uploadReferenceFile,
} from "@/lib/api";
import { openAuthorizedAsset, resolvePublicAssetUrl } from "@/lib/public-assets";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { type Reference, useWorkspaceStore } from "@/stores/workspace";

interface OutlineNode {
  id: string;
  section_path: string;
  title: string;
  level: number;
  page_start?: number | null;
  page_end?: number | null;
}

interface ReferenceItemProps {
  reference: Reference;
  index: number;
  isOpening: boolean;
  onOpen: (reference: Reference) => void | Promise<void>;
  isExpanded: boolean;
  outline: OutlineNode[] | null;
  isLoadingOutline: boolean;
  onToggleExpand: (reference: Reference) => void;
  onViewDetail: (reference: Reference) => void;
}

interface UploadState {
  id: string;
  name: string;
  status: "uploading" | "success" | "error";
  error?: string;
  preprocess?: ReferencePreprocessSubmission | null;
}

function isPdfFile(file: File): boolean {
  return /\.pdf$/i.test(file.name) || file.type === "application/pdf";
}

function formatPreprocessLabel(status: string): string {
  switch (status) {
    case "succeeded":
      return "索引完成";
    case "pending":
      return "等待解析";
    case "running":
      return "正在解析";
    case "failed":
      return "解析失败";
    case "skipped":
      return "未解析";
    default:
      return status;
  }
}

function formatLibraryStatus(status: string): string {
  switch (status) {
    case "core":
      return "核心";
    case "included":
      return "已纳入";
    case "candidate":
      return "候选";
    case "used_in_draft":
      return "已引用";
    case "excluded":
      return "已排除";
    default:
      return status;
  }
}

function formatEvidenceLevel(level: string): string {
  switch (level) {
    case "indexed_fulltext":
      return "全文索引";
    case "uploaded_fulltext":
      return "已上传全文";
    case "external_verified":
      return "外部核验";
    case "metadata_only":
      return "元数据";
    default:
      return level;
  }
}

function formatFulltextStatus(status: string): string {
  switch (status) {
    case "indexed":
      return "全文可检索";
    case "preprocessing":
      return "解析中";
    case "uploaded":
      return "已上传";
    case "failed":
      return "解析失败";
    case "none":
      return "无全文";
    default:
      return status;
  }
}

function formatCount(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k citations`;
  }
  return `${value} citations`;
}

function primaryReferenceAsset(reference: Reference): ReferenceAsset | null {
  const assets = Array.isArray(reference.assets) ? reference.assets : [];
  return (
    assets.find((asset) => asset.asset_type === "pdf" && asset.public_url) ??
    assets.find((asset) => asset.public_url) ??
    null
  );
}

function primaryReferenceUrl(reference: Reference): string | null {
  const asset = primaryReferenceAsset(reference);
  return resolvePublicAssetUrl(asset?.public_url ?? null) ?? resolvePublicAssetUrl(reference.url ?? null);
}

function ReferenceItem({
  reference,
  index,
  isOpening,
  onOpen,
  isExpanded,
  outline,
  isLoadingOutline,
  onToggleExpand,
  onViewDetail,
}: ReferenceItemProps) {
  const url = primaryReferenceUrl(reference);
  const citationCount = formatCount(reference.citation_count);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.035, duration: 0.25 }}
      className="group rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 transition-all hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-surface)]"
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
          {formatLibraryStatus(reference.library_status)}
        </span>
        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
          {formatEvidenceLevel(reference.evidence_level)}
        </span>
        <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
          {formatFulltextStatus(reference.fulltext_status)}
        </span>
      </div>

      <button
        type="button"
        onClick={() => onToggleExpand(reference)}
        className="mb-2 flex w-full items-start gap-1 text-left"
      >
        {isExpanded ? (
          <ChevronDown className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--text-muted)]" />
        ) : (
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--text-muted)]" />
        )}
        <h4 className="line-clamp-2 text-sm font-medium text-[var(--text-primary)]">
          {reference.title || "未命名参考文献"}
        </h4>
      </button>

      {reference.authors.length > 0 && (
        <div className="mb-1 flex items-center gap-1 text-xs text-[var(--text-secondary)]">
          <Users className="h-3 w-3" />
          <span className="truncate">
            {reference.authors.slice(0, 3).join(", ")}
            {reference.authors.length > 3 && ` +${reference.authors.length - 3}`}
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--text-muted)]">
        {reference.year ? (
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>{reference.year}</span>
          </div>
        ) : null}
        {reference.venue ? (
          <div className="flex min-w-0 items-center gap-1">
            <BookOpen className="h-3 w-3" />
            <span className="truncate">{reference.venue}</span>
          </div>
        ) : null}
        {citationCount ? <span>{citationCount}</span> : null}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
        {reference.citation_key ? (
          <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5">
            @{reference.citation_key}
          </span>
        ) : null}
        {reference.doi ? (
          <span className="max-w-full truncate rounded-full bg-[var(--bg-muted)] px-2 py-0.5">
            DOI {reference.doi}
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={() => void onOpen(reference)}
          disabled={!url || isOpening}
          aria-disabled={!url || isOpening}
          className={cn(
            "flex items-center gap-1 text-xs",
            url && !isOpening
              ? "text-[var(--accent-primary)] hover:text-[var(--accent-secondary)]"
              : "cursor-not-allowed text-[var(--text-muted)]"
          )}
        >
          {isOpening ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <ExternalLink className="h-3 w-3" />
          )}
          {isOpening ? "打开中" : url ? "查看来源" : "无可打开来源"}
        </button>
        <button
          type="button"
          onClick={() => onViewDetail(reference)}
          className="flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <Info className="h-3 w-3" />
          详情
        </button>
      </div>

      {isExpanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 overflow-hidden border-t border-[var(--border-default)] pt-2"
        >
          {isLoadingOutline ? (
            <div className="flex items-center gap-2 py-2 text-xs text-[var(--text-muted)]">
              <Loader2 className="h-3 w-3 animate-spin" />
              加载目录索引…
            </div>
          ) : outline && outline.length > 0 ? (
            <div className="space-y-1">
              {outline.map((node) => (
                <div
                  key={node.id}
                  className="flex items-start gap-2 text-xs"
                  style={{ paddingLeft: `${(node.level - 1) * 12}px` }}
                >
                  <span className="mt-0.5 flex-shrink-0 text-[10px] text-[var(--text-muted)]">
                    {node.section_path}
                  </span>
                  <span className="flex-1 truncate text-[var(--text-secondary)]">
                    {node.title}
                  </span>
                  {node.page_start ? (
                    <span className="flex-shrink-0 text-[10px] text-[var(--text-muted)]">
                      p.{node.page_start}
                      {node.page_end && node.page_end !== node.page_start
                        ? `–${node.page_end}`
                        : ""}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="py-1 text-xs text-[var(--text-muted)]">
              暂无目录索引
            </p>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}

function UploadStatusCard({ upload }: { upload: UploadState }) {
  const preprocess = upload.preprocess;
  const isFailed = upload.status === "error" || preprocess?.status === "failed";

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
              ? "正在上传并登记到参考库..."
              : upload.status === "error"
                ? upload.error || "上传失败"
                : "文件已进入参考库"}
          </p>

          {preprocess ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                  preprocess.status === "failed"
                    ? "bg-red-500/10 text-red-600"
                    : preprocess.status === "succeeded"
                      ? "bg-emerald-500/10 text-emerald-600"
                      : "bg-amber-500/10 text-amber-600"
                )}
              >
                {preprocess.status === "failed" ? (
                  <AlertCircle className="h-3 w-3" />
                ) : preprocess.status === "succeeded" ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <Clock3 className="h-3 w-3" />
                )}
                {formatPreprocessLabel(preprocess.status)}
              </span>
              {preprocess.task_id ? (
                <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                  任务 {preprocess.task_id.slice(0, 8)}
                </span>
              ) : null}
            </div>
          ) : null}

          {preprocess?.message ? (
            <p
              className={cn(
                "mt-2 text-[11px]",
                preprocess.status === "failed"
                  ? "text-red-600/90"
                  : "text-[var(--text-secondary)]"
              )}
            >
              {preprocess.message}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface LiteraturePanelProps {
  workspaceId: string;
  embedded?: boolean;
}

export function LiteraturePanel({
  workspaceId,
  embedded = false,
}: LiteraturePanelProps) {
  const references = useWorkspaceStore((state) => state.references);
  const fetchReferences = useWorkspaceStore((state) => state.fetchReferences);
  const isReferencesLoading = useWorkspaceStore((state) => state.isReferencesLoading);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [recentUploads, setRecentUploads] = useState<UploadState[]>([]);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [isSyncingBibtex, setIsSyncingBibtex] = useState(false);
  const [openingReferenceId, setOpeningReferenceId] = useState<string | null>(null);
  const [expandedReferenceId, setExpandedReferenceId] = useState<string | null>(null);
  const [referenceOutlines, setReferenceOutlines] = useState<Map<string, OutlineNode[]>>(new Map());
  const [loadingOutlineId, setLoadingOutlineId] = useState<string | null>(null);
  const [selectedReference, setSelectedReference] = useState<Reference | null>(null);

  useEffect(() => {
    if (workspaceId) {
      void fetchReferences(workspaceId);
    }
  }, [workspaceId, fetchReferences]);

  const isUploading = recentUploads.some(
    (upload) => upload.status === "uploading"
  );
  const indexedCount = references.filter(
    (reference) => reference.fulltext_status === "indexed"
  ).length;
  const coreCount = references.filter(
    (reference) => reference.library_status === "core"
  ).length;

  const handleOpenPicker = () => {
    if (!isUploading) {
      fileInputRef.current?.click();
    }
  };

  const handleOpenReference = async (reference: Reference) => {
    const url = primaryReferenceUrl(reference);
    if (!url) {
      setPanelError("当前参考文献没有可访问的来源。");
      return;
    }

    setPanelError(null);
    setOpeningReferenceId(reference.id);
    try {
      await openAuthorizedAsset(url);
    } catch (error) {
      setPanelError(
        error instanceof Error ? error.message : "打开参考文献失败，请稍后再试"
      );
    } finally {
      setOpeningReferenceId((current) =>
        current === reference.id ? null : current
      );
    }
  };

  const handleToggleExpand = async (reference: Reference) => {
    const nextId = expandedReferenceId === reference.id ? null : reference.id;
    setExpandedReferenceId(nextId);

    if (nextId && !referenceOutlines.has(reference.id)) {
      setLoadingOutlineId(reference.id);
      try {
        const result = await getReferenceOutline(workspaceId, reference.id);
        const items = ((result.items || []) as unknown) as OutlineNode[];
        setReferenceOutlines((prev) => {
          const next = new Map(prev);
          next.set(reference.id, items);
          return next;
        });
      } catch {
        setReferenceOutlines((prev) => {
          const next = new Map(prev);
          next.set(reference.id, []);
          return next;
        });
      } finally {
        setLoadingOutlineId((current) =>
          current === reference.id ? null : current
        );
      }
    }
  };

  const handleSyncBibtex = async () => {
    setPanelError(null);
    setSyncNotice(null);
    setIsSyncingBibtex(true);
    try {
      const result = await syncReferenceBibtexToPrism(workspaceId);
      setSyncNotice(`已同步 ${result.reference_count} 条参考文献到 refs.bib。`);
    } catch (error) {
      setPanelError(
        error instanceof Error ? error.message : "同步 refs.bib 失败"
      );
    } finally {
      setIsSyncingBibtex(false);
    }
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
      setPanelError(`仅支持 PDF 文件：${invalidFile.name}`);
      return;
    }

    setPanelError(null);
    let shouldRefresh = false;

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
        const response = await uploadReferenceFile(workspaceId, file);
        shouldRefresh = true;
        setRecentUploads((current) =>
          current.map((upload) =>
            upload.id === uploadId
              ? {
                  ...upload,
                  status: "success",
                  preprocess: response.preprocess ?? null,
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
        setPanelError(message);
      }
    }

    if (shouldRefresh) {
      await fetchReferences(workspaceId);
    }
  };

  return (
    <div
      className={cn(
        "flex h-full flex-col bg-[var(--bg-elevated)] backdrop-blur-xl",
        embedded
          ? "min-h-0"
          : "w-[320px] border-l border-[var(--border-default)]"
      )}
    >
      <div className="border-b border-[var(--border-default)] p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
            <FileText className="h-5 w-5 text-[var(--accent-primary)]" />
            {embedded ? "参考库" : "文献中心"}
          </h2>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void handleSyncBibtex()}
              disabled={isSyncingBibtex || references.length === 0}
              title="同步 refs.bib 到 WenjinPrism"
              className="rounded-lg bg-[var(--bg-muted)] p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSyncingBibtex ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Database className="h-4 w-4" />
              )}
            </button>
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
        </div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {references.length} 条参考文献，{indexedCount} 条已建立全文索引，{coreCount} 条标记为核心。
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          上传 PDF 或完成 Semantic Scholar 调研后，条目会进入当前 workspace 的隔离参考库。
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
        {panelError ? (
          <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-600">
            {panelError}
          </div>
        ) : null}

        {syncNotice ? (
          <div className="mb-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
            {syncNotice}
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
          {isReferencesLoading ? (
            <div className="flex items-center justify-center py-8">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="h-6 w-6 rounded-full border-2 border-[var(--accent-primary)] border-t-transparent"
              />
            </div>
          ) : references.length === 0 ? (
            <div className="py-8 text-center">
              <FileText className="mx-auto mb-2 h-10 w-10 text-[var(--text-muted)]" />
              <p className="text-sm text-[var(--text-secondary)]">
                {embedded ? "还没有参考文献" : "当前参考库为空"}
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                上传 PDF，或运行文献调研后自动沉淀 Semantic Scholar 结果。
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
                上传 PDF
              </motion.button>
            </div>
          ) : (
            <div className="space-y-2">
              {references.map((reference, index) => (
                <ReferenceItem
                  key={reference.id}
                  reference={reference}
                  index={index}
                  isOpening={openingReferenceId === reference.id}
                  onOpen={handleOpenReference}
                  isExpanded={expandedReferenceId === reference.id}
                  outline={referenceOutlines.get(reference.id) ?? null}
                  isLoadingOutline={loadingOutlineId === reference.id}
                  onToggleExpand={handleToggleExpand}
                  onViewDetail={setSelectedReference}
                />
              ))}
            </div>
          )}
        </AnimatePresence>
      </div>

      <Dialog open={!!selectedReference} onOpenChange={() => setSelectedReference(null)}>
        <DialogContent className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selectedReference?.title || "文献详情"}</DialogTitle>
            <DialogDescription>
              {selectedReference?.authors && selectedReference.authors.length > 0
                ? selectedReference.authors.join(", ")
                : "未知作者"}
              {selectedReference?.year ? ` · ${selectedReference.year}` : ""}
            </DialogDescription>
          </DialogHeader>
          {selectedReference && (
            <div className="space-y-4 text-sm">
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                  {formatLibraryStatus(selectedReference.library_status)}
                </span>
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
                  {formatEvidenceLevel(selectedReference.evidence_level)}
                </span>
                <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                  {formatFulltextStatus(selectedReference.fulltext_status)}
                </span>
              </div>
              {selectedReference.venue ? (
                <div className="flex items-center gap-2 text-[var(--text-secondary)]">
                  <BookOpen className="h-4 w-4" />
                  <span>{selectedReference.venue}</span>
                </div>
              ) : null}
              {selectedReference.doi ? (
                <div className="text-[var(--text-muted)]">
                  DOI: {selectedReference.doi}
                </div>
              ) : null}
              {selectedReference.citation_key ? (
                <div className="rounded-md bg-[var(--bg-muted)] px-3 py-2 font-mono text-xs text-[var(--text-secondary)]">
                  @{selectedReference.citation_key}
                </div>
              ) : null}
              {selectedReference.abstract ? (
                <div>
                  <h5 className="mb-1 text-xs font-medium text-[var(--text-primary)]">摘要</h5>
                  <p className="max-h-40 overflow-y-auto text-xs text-[var(--text-secondary)]">
                    {selectedReference.abstract}
                  </p>
                </div>
              ) : null}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
