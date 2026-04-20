"use client";

import { useEffect, useMemo, useRef } from "react";
import { GlobalWorkerOptions, getDocument, TextLayer, version as pdfjsVersion } from "pdfjs-dist";

import type { LatexPdfAnchor } from "@/lib/api";

interface PdfSelectionPayload {
  text: string;
  page: number;
  rects: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
}

interface PdfFeedbackHighlight {
  id: string;
  selectedText: string;
  pdfAnchor?: LatexPdfAnchor | null;
}

interface LatexPdfPreviewProps {
  pdfUrl: string;
  feedbacks: PdfFeedbackHighlight[];
  activeFeedbackId: string | null;
  transientSelectionAnchor?: LatexPdfAnchor | null;
  transientSelectionText?: string;
  onSelection?: (payload: PdfSelectionPayload) => void;
  className?: string;
}

if (typeof window !== "undefined" && !GlobalWorkerOptions.workerSrc) {
  GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjsVersion}/build/pdf.worker.min.mjs`;
}

function normalizeText(value: string): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

type NormalizedRect = { x: number; y: number; width: number; height: number };

function centerOfRect(rect: NormalizedRect): { x: number; y: number } {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

function mergeRects(rects: NormalizedRect[]): NormalizedRect[] {
  if (rects.length <= 1) {
    return rects;
  }
  const sorted = [...rects].sort((a, b) => (Math.abs(a.y - b.y) < 0.003 ? a.x - b.x : a.y - b.y));
  const merged: NormalizedRect[] = [];
  for (const rect of sorted) {
    const prev = merged[merged.length - 1];
    if (
      prev
      && Math.abs(prev.y - rect.y) < 0.007
      && Math.abs(prev.height - rect.height) < 0.01
      && rect.x <= prev.x + prev.width + 0.006
    ) {
      const nextX = Math.min(prev.x, rect.x);
      const nextY = Math.min(prev.y, rect.y);
      const nextRight = Math.max(prev.x + prev.width, rect.x + rect.width);
      const nextBottom = Math.max(prev.y + prev.height, rect.y + rect.height);
      prev.x = nextX;
      prev.y = nextY;
      prev.width = nextRight - nextX;
      prev.height = nextBottom - nextY;
      continue;
    }
    merged.push({ ...rect });
  }
  return merged;
}

function scoreRectDistance(anchor: NormalizedRect, rects: NormalizedRect[]): number {
  if (!rects.length) {
    return Number.POSITIVE_INFINITY;
  }
  const anchorCenter = centerOfRect(anchor);
  const avg = rects.reduce(
    (acc, rect) => {
      const c = centerOfRect(rect);
      return { x: acc.x + c.x, y: acc.y + c.y };
    },
    { x: 0, y: 0 },
  );
  const targetCenter = { x: avg.x / rects.length, y: avg.y / rects.length };
  return Math.hypot(anchorCenter.x - targetCenter.x, anchorCenter.y - targetCenter.y);
}

function buildRectFromSpan(pageEl: HTMLElement, span: HTMLElement): NormalizedRect | null {
  const pageRect = pageEl.getBoundingClientRect();
  const rect = span.getBoundingClientRect();
  if (pageRect.width <= 0 || pageRect.height <= 0 || rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  return {
    x: (rect.left - pageRect.left) / pageRect.width,
    y: (rect.top - pageRect.top) / pageRect.height,
    width: rect.width / pageRect.width,
    height: rect.height / pageRect.height,
  };
}

function refineRectsBySnippetInPage(
  pageEl: HTMLElement,
  snippet: string,
  anchorRect?: NormalizedRect | null,
): NormalizedRect[] {
  const target = normalizeText(snippet);
  if (!target) {
    return [];
  }
  const spans = Array.from(pageEl.querySelectorAll<HTMLElement>(".latex-pdf-text-layer span"));
  if (!spans.length) {
    return [];
  }

  type SpanMeta = {
    span: HTMLElement;
    text: string;
    start: number;
    end: number;
  };
  const metas: SpanMeta[] = [];
  let combined = "";
  for (const span of spans) {
    const text = normalizeText(span.textContent || "");
    if (!text) continue;
    if (combined.length > 0) {
      combined += " ";
    }
    const actualStart = combined.length;
    combined += text;
    metas.push({
      span,
      text,
      start: actualStart,
      end: actualStart + text.length,
    });
  }
  if (!combined) {
    return [];
  }

  const occurrences: Array<{ start: number; end: number }> = [];
  let cursor = 0;
  while (cursor < combined.length) {
    const found = combined.indexOf(target, cursor);
    if (found < 0) break;
    occurrences.push({ start: found, end: found + target.length });
    if (occurrences.length >= 24) break;
    cursor = found + Math.max(1, target.length);
  }

  if (!occurrences.length) {
    return [];
  }

  let bestRects: NormalizedRect[] = [];
  let bestScore = Number.POSITIVE_INFINITY;
  for (const occ of occurrences) {
    const selectedSpans = metas.filter((meta) => meta.end > occ.start && meta.start < occ.end);
    const rects = selectedSpans
      .map((meta) => buildRectFromSpan(pageEl, meta.span))
      .filter((rect): rect is NormalizedRect => Boolean(rect));
    if (!rects.length) {
      continue;
    }
    const merged = mergeRects(rects);
    const score = anchorRect ? scoreRectDistance(anchorRect, merged) : merged.length;
    if (score < bestScore) {
      bestScore = score;
      bestRects = merged;
    }
  }
  return bestRects;
}

function findFallbackRectByText(
  container: HTMLDivElement,
  selectedText: string,
): { page: number; rect: { x: number; y: number; width: number; height: number } } | null {
  const target = normalizeText(selectedText);
  if (!target) {
    return null;
  }
  const token = target.split(" ").find((part) => part.length >= 3) || target;
  const pages = Array.from(container.querySelectorAll<HTMLElement>(".latex-pdf-page"));
  for (const page of pages) {
    const spans = Array.from(page.querySelectorAll<HTMLElement>(".latex-pdf-text-layer span"));
    for (const span of spans) {
      const spanText = normalizeText(span.textContent || "");
      if (!spanText) continue;
      if (!(spanText.includes(token) || token.includes(spanText))) continue;
      const pageRect = page.getBoundingClientRect();
      const rect = span.getBoundingClientRect();
      if (pageRect.width <= 0 || pageRect.height <= 0) continue;
      return {
        page: Number(page.dataset.pageNumber || 1),
        rect: {
          x: (rect.left - pageRect.left) / pageRect.width,
          y: (rect.top - pageRect.top) / pageRect.height,
          width: rect.width / pageRect.width,
          height: rect.height / pageRect.height,
        },
      };
    }
  }
  return null;
}

export function LatexPdfPreview({
  pdfUrl,
  feedbacks,
  activeFeedbackId,
  transientSelectionAnchor,
  transientSelectionText,
  onSelection,
  className,
}: LatexPdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastScrolledFeedbackRef = useRef<string | null>(null);

  const activeFeedback = useMemo(
    () => feedbacks.find((item) => item.id === activeFeedbackId) || null,
    [activeFeedbackId, feedbacks],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !pdfUrl) return;

    let cancelled = false;
    let loadingTask: ReturnType<typeof getDocument> | null = null;
    const renderedTextLayers: TextLayer[] = [];
    container.innerHTML = "";

    const render = async () => {
      try {
        loadingTask = getDocument(pdfUrl);
        const pdf = await loadingTask.promise;

        const firstPage = await pdf.getPage(1);
        const baseViewport = firstPage.getViewport({ scale: 1 });
        const containerWidth = Math.max(280, container.clientWidth - 24);
        const fitScale = containerWidth / baseViewport.width;

        const renderOnePage = async (pageNum: number) => {
          const page = await pdf.getPage(pageNum);
          const viewport = page.getViewport({ scale: fitScale });
          const outputScale = window.devicePixelRatio || 1;
          const renderViewport = page.getViewport({ scale: fitScale * outputScale });

          const pageEl = document.createElement("div");
          pageEl.className = "latex-pdf-page";
          pageEl.dataset.pageNumber = String(pageNum);
          pageEl.style.width = `${viewport.width}px`;
          pageEl.style.height = `${viewport.height}px`;

          const canvas = document.createElement("canvas");
          canvas.width = Math.floor(renderViewport.width);
          canvas.height = Math.floor(renderViewport.height);
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            return;
          }
          await page.render({ canvasContext: ctx, viewport: renderViewport }).promise;
          pageEl.appendChild(canvas);

          const textLayer = document.createElement("div");
          textLayer.className = "latex-pdf-text-layer";
          textLayer.style.width = `${viewport.width}px`;
          textLayer.style.height = `${viewport.height}px`;
          textLayer.style.setProperty("--scale-factor", String(viewport.scale));
          pageEl.appendChild(textLayer);

          const textContent = await page.getTextContent();
          const layer = new TextLayer({
            textContentSource: textContent,
            container: textLayer,
            viewport,
          });
          renderedTextLayers.push(layer);
          await layer.render();

          if (cancelled) {
            return;
          }
          container.appendChild(pageEl);
        };

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum += 1) {
          if (cancelled) {
            break;
          }
          await renderOnePage(pageNum);
        }
      } catch (err) {
        if (!cancelled) {
          const errorNode = document.createElement("div");
          errorNode.className = "latex-pdf-error";
          errorNode.textContent = `PDF 渲染失败: ${String(err)}`;
          container.replaceChildren(errorNode);
        }
      }
    };

    void render();

    return () => {
      cancelled = true;
      for (const layer of renderedTextLayers) {
        layer.cancel();
      }
      renderedTextLayers.length = 0;
      void loadingTask?.destroy();
      container.innerHTML = "";
    };
  }, [pdfUrl]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.querySelectorAll(".latex-pdf-highlight").forEach((node) => node.remove());

    const drawHighlight = (
      page: number,
      rect: { x: number; y: number; width: number; height: number },
      active: boolean,
    ) => {
      const pageEl = container.querySelector<HTMLElement>(`.latex-pdf-page[data-page-number="${page}"]`);
      if (!pageEl) {
        return;
      }
      const mark = document.createElement("div");
      mark.className = `latex-pdf-highlight ${active ? "active" : "inactive"}`;
      mark.style.left = `${Math.max(0, rect.x) * 100}%`;
      mark.style.top = `${Math.max(0, rect.y) * 100}%`;
      mark.style.width = `${Math.max(0.002, rect.width) * 100}%`;
      mark.style.height = `${Math.max(0.002, rect.height) * 100}%`;
      pageEl.appendChild(mark);
    };

    const drawRects = (page: number, rects: NormalizedRect[], active: boolean) => {
      for (const rect of rects) {
        if (!Number.isFinite(rect.x) || !Number.isFinite(rect.y)) continue;
        drawHighlight(page, rect, active);
      }
    };

    for (const item of feedbacks) {
      const isActive = item.id === activeFeedbackId;
      const anchor = item.pdfAnchor;
      if (anchor?.page && Array.isArray(anchor.rects) && anchor.rects.length > 0) {
        const pageEl = container.querySelector<HTMLElement>(`.latex-pdf-page[data-page-number="${anchor.page}"]`);
        const baseRects = anchor.rects
          .filter((rect) => typeof rect?.x === "number" && typeof rect?.y === "number")
          .map((rect) => ({
            x: Number(rect.x),
            y: Number(rect.y),
            width: Number(rect.width),
            height: Number(rect.height),
          }));
        const firstRect = baseRects[0];
        const shouldRefine =
          Boolean(pageEl)
          && Boolean(item.selectedText || anchor.text)
          && Boolean(firstRect)
          && (firstRect.width * firstRect.height < 0.0016 || (firstRect.width <= 0.03 && firstRect.height <= 0.03));
        if (pageEl && shouldRefine) {
          const refined = refineRectsBySnippetInPage(
            pageEl,
            item.selectedText || anchor.text,
            firstRect,
          );
          if (refined.length > 0) {
            drawRects(anchor.page, refined, isActive);
            continue;
          }
        }
        drawRects(anchor.page, mergeRects(baseRects), isActive);
        continue;
      }
      if (isActive && item.selectedText) {
        const fallback = findFallbackRectByText(container, item.selectedText);
        if (fallback) {
          drawHighlight(fallback.page, fallback.rect, true);
        }
      }
    }

    if (!activeFeedback) {
      let drewTransient = false;
      if (
        transientSelectionAnchor
        && transientSelectionAnchor.page > 0
        && Array.isArray(transientSelectionAnchor.rects)
        && transientSelectionAnchor.rects.length > 0
      ) {
        const pageEl = container.querySelector<HTMLElement>(
          `.latex-pdf-page[data-page-number="${transientSelectionAnchor.page}"]`,
        );
        const baseRects = transientSelectionAnchor.rects.map((rect) => ({
          x: Number(rect.x),
          y: Number(rect.y),
          width: Number(rect.width),
          height: Number(rect.height),
        }));
        const firstRect = baseRects[0];
        if (
          pageEl
          && firstRect
          && transientSelectionText
          && (firstRect.width * firstRect.height < 0.0016 || (firstRect.width <= 0.03 && firstRect.height <= 0.03))
        ) {
          const refined = refineRectsBySnippetInPage(pageEl, transientSelectionText, firstRect);
          if (refined.length > 0) {
            drawRects(transientSelectionAnchor.page, refined, true);
            drewTransient = true;
          } else {
            drawRects(transientSelectionAnchor.page, mergeRects(baseRects), true);
            drewTransient = true;
          }
        } else {
          drawRects(transientSelectionAnchor.page, mergeRects(baseRects), true);
          drewTransient = true;
        }
      }
      const transient = normalizeText(transientSelectionText || "");
      if (transient && !drewTransient) {
        const fallback = findFallbackRectByText(container, transient);
        if (fallback) {
          drawHighlight(fallback.page, fallback.rect, true);
        }
      }
    }

    if (activeFeedback && activeFeedbackId !== lastScrolledFeedbackRef.current) {
      const activeMark = container.querySelector<HTMLElement>(".latex-pdf-highlight.active");
      if (activeMark) {
        activeMark.scrollIntoView({ block: "center", behavior: "smooth" });
        lastScrolledFeedbackRef.current = activeFeedbackId;
      }
    }
  }, [activeFeedback, activeFeedbackId, feedbacks, transientSelectionAnchor, transientSelectionText]);

  return (
    <div
      className={className || ""}
      onMouseUp={() => {
        if (!onSelection) return;
        const container = containerRef.current;
        if (!container) return;
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
        const selectedText = selection.toString().trim();
        if (selectedText.length < 2) return;

        const range = selection.getRangeAt(0);
        const node = range.commonAncestorContainer;
        const element = node.nodeType === Node.ELEMENT_NODE
          ? (node as Element)
          : node.parentElement;
        const pageEl = element?.closest(".latex-pdf-page") as HTMLElement | null;
        if (!pageEl) return;
        const pageRect = pageEl.getBoundingClientRect();
        const page = Number(pageEl.dataset.pageNumber || 1);
        const rects = Array.from(range.getClientRects())
          .filter((rect) => rect.width > 1 && rect.height > 1)
          .map((rect) => ({
            x: (rect.left - pageRect.left) / pageRect.width,
            y: (rect.top - pageRect.top) / pageRect.height,
            width: rect.width / pageRect.width,
            height: rect.height / pageRect.height,
          }))
          .filter(
            (rect) =>
              Number.isFinite(rect.x)
              && Number.isFinite(rect.y)
              && Number.isFinite(rect.width)
              && Number.isFinite(rect.height),
          );
        if (!rects.length) return;
        onSelection({
          text: selectedText,
          page,
          rects,
        });
      }}
    >
      <div ref={containerRef} className="latex-pdf-container" />
      <style jsx global>{`
        .latex-pdf-container {
          height: 78vh;
          min-height: 760px;
          overflow: auto;
          padding: 12px;
          background: #f7f7f7;
        }
        .latex-pdf-page {
          position: relative;
          margin: 0 auto 16px auto;
          background: #fff;
          box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
          overflow: hidden;
          user-select: text;
        }
        .latex-pdf-text-layer {
          position: absolute;
          inset: 0;
          overflow: hidden;
          opacity: 0.2;
          line-height: 1;
        }
        .latex-pdf-text-layer span {
          color: transparent;
          position: absolute;
          white-space: pre;
          transform-origin: 0% 0%;
          cursor: text;
        }
        .latex-pdf-text-layer ::selection {
          background: rgba(180, 134, 63, 0.4);
        }
        .latex-pdf-highlight {
          position: absolute;
          pointer-events: none;
          border-radius: 3px;
        }
        .latex-pdf-highlight.inactive {
          background: rgba(255, 218, 117, 0.25);
        }
        .latex-pdf-highlight.active {
          background: rgba(255, 208, 89, 0.45);
          box-shadow: 0 0 0 1px rgba(180, 134, 63, 0.35);
        }
        .latex-pdf-error {
          color: #b91c1c;
          font-size: 12px;
          padding: 16px;
        }
      `}</style>
    </div>
  );
}
