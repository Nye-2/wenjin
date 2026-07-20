"use client";

/* eslint-disable @next/next/no-img-element -- Authenticated Blob URLs cannot use Next Image optimization. */

import { ExternalLink, FileText, Image as ImageIcon, LoaderCircle, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useState, type MouseEvent } from "react";

import { getMissionReviewPreview } from "@/lib/api/missions";
import type { MissionReviewItemView, MissionVisualReviewMetadata } from "@/lib/api/mission-types";

const IMAGE_MIME_TYPES = new Set(["image/png", "image/webp", "image/svg+xml"]);
const PDF_MIME_TYPE = "application/pdf";

interface AcademicVisualReviewPreviewProps {
  missionId: string;
  item: MissionReviewItemView;
}

export function AcademicVisualReviewPreview({ missionId, item }: AcademicVisualReviewPreviewProps) {
  const metadata = item.visual;
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadedMimeType, setLoadedMimeType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const metadataMimeType = metadata?.mimeType ?? null;

  useEffect(() => {
    if (!metadata || !item.previewAvailable) return;
    let active = true;
    let nextObjectUrl: string | null = null;
    setObjectUrl(null);
    setLoadedMimeType(null);
    setError(null);

    void getMissionReviewPreview({ missionId, reviewItemId: item.id })
      .then(({ blob, mimeType }) => {
        if (!active) return;
        const resolvedMimeType = mimeType || metadataMimeType || "";
        if (!IMAGE_MIME_TYPES.has(resolvedMimeType) && resolvedMimeType !== PDF_MIME_TYPE) {
          throw new Error("暂不支持此预览格式");
        }
        nextObjectUrl = URL.createObjectURL(blob);
        setLoadedMimeType(resolvedMimeType);
        setObjectUrl(nextObjectUrl);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "视觉预览加载失败");
      });

    return () => {
      active = false;
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl);
    };
  }, [item.id, item.previewAvailable, metadataMimeType, missionId]);

  const metadataLines = useMemo(() => metadata ? visualMetadataLines(metadata) : [], [metadata]);
  if (!metadata) return null;

  const openPreview = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (objectUrl) window.open(objectUrl, "_blank", "noopener,noreferrer");
  };

  const isImage = loadedMimeType ? IMAGE_MIME_TYPES.has(loadedMimeType) : false;
  const isPdf = loadedMimeType === PDF_MIME_TYPE;
  const canOpenExternally = Boolean(objectUrl && loadedMimeType !== "image/svg+xml");

  return (
    <section className="mt-3 overflow-hidden rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)]" aria-label="学术视觉预览">
      <div className="flex min-h-40 items-center justify-center bg-[var(--wjn-surface)] p-2">
        {!objectUrl && !error && item.previewAvailable ? (
          <span className="flex items-center gap-2 text-xs text-[var(--wjn-text-muted)]">
            <LoaderCircle size={14} className="animate-spin motion-reduce:animate-none" /> 正在加载预览
          </span>
        ) : null}
        {!item.previewAvailable ? (
          <span className="px-4 py-8 text-center text-xs leading-5 text-[var(--wjn-text-muted)]">该视觉候选暂无可用预览</span>
        ) : null}
        {error ? (
          <span className="px-4 py-8 text-center text-xs leading-5 text-[var(--wjn-error)]">{error}</span>
        ) : null}
        {objectUrl && isImage ? (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setZoomed((value) => !value);
            }}
            className={`group flex w-full cursor-zoom-in items-center justify-center overflow-auto ${zoomed ? "max-h-[70vh] cursor-zoom-out" : "max-h-80"}`}
            aria-label={zoomed ? "缩小视觉预览" : "放大视觉预览"}
          >
            {/* Authenticated bytes are exposed only through this short-lived object URL. */}
            <img
              src={objectUrl}
              alt={metadata.altText ?? metadata.caption ?? item.title}
              className={zoomed ? "h-auto max-w-none" : "max-h-76 w-auto max-w-full object-contain"}
            />
          </button>
        ) : null}
        {objectUrl && isPdf ? (
          <button type="button" onClick={openPreview} className="flex min-h-36 w-full flex-col items-center justify-center gap-3 text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-accent-strong)]">
            <FileText size={28} />
            <span className="text-xs font-medium">查看 PDF 预览</span>
          </button>
        ) : null}
      </div>

      <div className="border-t border-[var(--wjn-line)] px-3 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--wjn-text)]">
              <ImageIcon size={13} className="shrink-0 text-[var(--wjn-accent)]" />
              {visualKindLabel(metadata)}
            </div>
            {metadata.caption ? <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">{metadata.caption}</p> : null}
            {metadataLines.length ? <p className="mt-1 text-[10px] leading-4 text-[var(--wjn-text-muted)]">{metadataLines.join(" · ")}</p> : null}
          </div>
          <span className="flex shrink-0 items-center gap-1">
            {objectUrl && isImage ? (
              <button
                type="button"
                title={zoomed ? "缩小" : "放大"}
                aria-label={zoomed ? "缩小" : "放大"}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setZoomed((value) => !value);
                }}
                className="flex h-7 w-7 items-center justify-center rounded text-[var(--wjn-text-muted)] hover:bg-[var(--wjn-surface)] hover:text-[var(--wjn-text)]"
              >
                {zoomed ? <ZoomOut size={14} /> : <ZoomIn size={14} />}
              </button>
            ) : null}
            {canOpenExternally ? (
              <button type="button" title="在新窗口查看" aria-label="在新窗口查看" onClick={openPreview} className="flex h-7 w-7 items-center justify-center rounded text-[var(--wjn-text-muted)] hover:bg-[var(--wjn-surface)] hover:text-[var(--wjn-text)]">
                <ExternalLink size={14} />
              </button>
            ) : null}
          </span>
        </div>
        {metadata.altText ? <p className="sr-only">图片说明：{metadata.altText}</p> : null}
      </div>
    </section>
  );
}

function visualKindLabel(metadata: MissionVisualReviewMetadata): string {
  if (metadata.artifactKind === "chart") return "数据图表";
  if (metadata.artifactKind === "table") return "学术表格";
  return "学术图像";
}

function visualMetadataLines(metadata: MissionVisualReviewMetadata): string[] {
  const strategy = metadata.strategy ? strategyLabel(metadata.strategy) : null;
  const renderer = metadata.rendererId ? `渲染：${metadata.rendererId}` : null;
  const source = metadata.sourceLabels.length ? `来源：${metadata.sourceLabels.slice(0, 2).join("、")}` : null;
  const reproducibility = metadata.reproducibilityStatus
    ? `复现：${reproducibilityLabel(metadata.reproducibilityStatus)}`
    : null;
  const evidence = metadata.evidenceLevel ? evidenceLevelLabel(metadata.evidenceLevel) : null;
  return [metadata.figureType, strategy, evidence, renderer, source, reproducibility].filter((value): value is string => Boolean(value));
}

function evidenceLevelLabel(level: string): string {
  const labels: Record<string, string> = {
    evidence: "数据图",
    explanatory: "说明图",
    decorative: "视觉辅助",
  };
  return labels[level] ?? level;
}

function strategyLabel(strategy: string): string {
  const labels: Record<string, string> = {
    matplotlib: "Matplotlib",
    seaborn: "Seaborn",
    graphviz: "Graphviz",
    python_schematic: "Python 绘制",
    llm_image: "AI 学术插图",
    hybrid: "混合绘制",
  };
  return labels[strategy] ?? strategy;
}

function reproducibilityLabel(status: string): string {
  const labels: Record<string, string> = {
    reproducible: "可复现",
    verified: "已验证",
    complete: "材料完整",
    pending: "待验证",
    not_reproducible: "非数据产物",
    not_applicable: "不适用",
  };
  return labels[status] ?? status;
}
