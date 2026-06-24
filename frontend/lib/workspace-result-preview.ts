import {
  isRawRuntimePayloadText,
  safeRuntimeText,
  safeStructuredFallback,
} from "./runtime-payload-safety";

type PreviewMode =
  | "markdown"
  | "plain_text"
  | "outline"
  | "citation"
  | "structured_json"
  | "image";

type PreviewKind =
  | "document"
  | "figure"
  | "library_item"
  | "memory_fact"
  | "decision"
  | "task";

export interface WorkspaceRoomTarget {
  room: "documents" | "library";
  itemId?: string | null;
  query?: string | null;
}

export interface WorkspaceResultPreview {
  id: string;
  source: "staged_output" | "review_item" | "document_room" | "library_room";
  kind: PreviewKind;
  data?: Record<string, unknown> | null;
  title: string;
  subtitle: string | null;
  badge: string | null;
  previewMode: PreviewMode;
  previewText: string | null;
  previewPath?: string | null;
  metadata?: Record<string, unknown> | null;
  metadataLines: string[];
  defaultChecked: boolean;
  canCommit: boolean;
  canOpenRoom: boolean;
  roomTarget?: WorkspaceRoomTarget;
}

type StagedOutput = {
  id?: unknown;
  kind?: unknown;
  preview?: unknown;
  default_checked?: unknown;
  data?: unknown;
};

function readString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function firstNonNull(...values: Array<string | null>): string | null {
  for (const value of values) {
    if (value) {
      return value;
    }
  }
  return null;
}

function safeContentText(value: unknown): string | null {
  const text = readString(value);
  if (!text || isRawRuntimePayloadText(text)) {
    return null;
  }
  return text;
}

export function buildWorkspaceResultPreviewsFromOutputs(
  outputs: unknown,
): WorkspaceResultPreview[] {
  if (!Array.isArray(outputs)) {
    return [];
  }

  return outputs.flatMap((item) => {
    const output = readObject(item) as StagedOutput | null;
    if (!output) {
      return [];
    }
    const id = readString(output.id);
    const kind = readString(output.kind) as PreviewKind | null;
    if (!id || !kind) {
      return [];
    }
    const data = readObject(output.data);
    const preview = safeRuntimeText(output.preview);
    const defaultChecked = output.default_checked !== false;

    switch (kind) {
      case "document":
        if (isFigureDocument(data)) {
          return [
            buildFigurePreview({
              id,
              preview,
              defaultChecked,
              data,
            }),
          ];
        }
        return [
          buildDocumentPreview({
            id,
            preview,
            defaultChecked,
            data,
          }),
        ];
      case "figure":
        return [
          buildFigurePreview({
            id,
            preview,
            defaultChecked,
            data,
          }),
        ];
      case "library_item":
        return [
          buildLibraryPreview({
            id,
            preview,
            defaultChecked,
            data,
          }),
        ];
      case "memory_fact":
        return [
          {
            id,
            source: "staged_output",
            kind,
            title: preview ?? "记忆片段",
            subtitle: safeRuntimeText(data?.category),
            badge: "记忆",
            data,
            previewMode: "plain_text",
            previewText:
              safeRuntimeText(data?.content) ??
              preview ??
              safeStructuredFallback(data, "已生成记忆片段"),
            metadataLines: [],
            defaultChecked,
            canCommit: true,
            canOpenRoom: false,
          },
        ];
      case "decision":
        return [
          {
            id,
            source: "staged_output",
            kind,
            title: preview ?? safeRuntimeText(data?.key) ?? "决策记录",
            subtitle: safeRuntimeText(data?.key),
            badge: "决策",
            data,
            previewMode: "plain_text",
            previewText:
              safeRuntimeText(data?.value) ??
              preview ??
              safeStructuredFallback(data, "已生成决策记录"),
            metadataLines: [],
            defaultChecked,
            canCommit: true,
            canOpenRoom: false,
          },
        ];
      case "task":
        return [
          {
            id,
            source: "staged_output",
            kind,
            title: preview ?? safeRuntimeText(data?.title) ?? "任务项",
            subtitle: safeRuntimeText(data?.priority)
              ? `Priority ${safeRuntimeText(data?.priority)}`
              : null,
            badge: "任务",
            data,
            previewMode: "plain_text",
            previewText:
              safeRuntimeText(data?.description) ??
              preview ??
              safeStructuredFallback(data, "已生成任务项"),
            metadataLines: [],
            defaultChecked,
            canCommit: true,
            canOpenRoom: false,
          },
        ];
      default:
        return [];
    }
  });
}

export function buildWorkspaceResultPreviewsFromReviewItems(
  reviewItems: unknown,
): WorkspaceResultPreview[] {
  if (!Array.isArray(reviewItems)) {
    return [];
  }

  return reviewItems.flatMap((value) => {
    const item = readObject(value);
    if (!item || !isSandboxFigureReviewItem(item)) {
      return [];
    }
    const id = readString(item.id);
    if (!id) {
      return [];
    }
    const target = readObject(item.target);
    const preview = readObject(item.preview);
    const source = readObject(item.source);
    const reproducibility = readObject(item.reproducibility);
    const previewPath = firstWorkspaceImagePath(
      readString(preview?.path),
      readString(target?.path),
      readString(item.summary),
    );
    if (!previewPath) {
      return [];
    }
    const rawTitle = readString(item.title);
    const rawSummary = readString(item.summary);
    const title =
      safeRuntimeText(rawTitle) ??
      (rawTitle ? "图表产物" : pathBasename(previewPath) ?? "图表产物");
    const summary = safeRuntimeText(rawSummary);
    const mimeType = readString(preview?.mime_type);
    const contentHash = firstNonNull(
      readString(preview?.content_hash),
      readString(reproducibility?.content_hash),
    );
    const sourceScript = readString(reproducibility?.source_script);
    const datasetPaths = readStringArray(reproducibility?.dataset_paths);
    const metadata: Record<string, unknown> = {
      review_item_id: id,
      sandbox_artifact_id: readString(target?.sandbox_artifact_id),
      source_task_id: readString(source?.task_id),
      mime_type: mimeType,
      content_hash: contentHash,
      source_script: sourceScript,
      dataset_paths: datasetPaths,
    };
    const metadataLines = [
      mimeType,
      sourceScript ? pathBasename(sourceScript) : null,
      datasetPaths.length > 0
        ? `数据 ${datasetPaths.map((path) => pathBasename(path) ?? path).join(", ")}`
        : null,
      contentHash,
    ].filter((line): line is string => Boolean(line));

    return [
      {
        id: `review:${id}`,
        source: "review_item",
        kind: "figure",
        title,
        subtitle: summary && summary !== title && summary !== previewPath ? summarizeText(summary) : null,
        badge: "图表",
        data: {
          ...target,
          path: previewPath,
          preview_path: previewPath,
          mime_type: mimeType,
          content_hash: contentHash,
          artifact_kind: "figure",
          review_item: item,
        },
        previewMode: "image",
        previewPath,
        previewText: summary ?? (rawSummary ? "待确认产物" : previewPath),
        metadata,
        metadataLines,
        defaultChecked: false,
        canCommit: false,
        canOpenRoom: false,
      },
    ];
  });
}

export function buildDocumentRoomPreview(
  document: Record<string, unknown>,
): WorkspaceResultPreview {
  const metadata = readObject(document.metadata_json);
  const mimeType = readString(document.mime_type);
  const docKind = readString(document.doc_kind) ?? readString(document.kind);
  const content = safeContentText(metadata?.content);
  return {
    id: readString(document.id) ?? "document",
    source: "document_room",
    kind: "document",
    title: readString(document.name) ?? "未命名文档",
    subtitle: docKind ? documentKindLabel(docKind) : mimeType,
    badge: "文档",
    data: document,
    previewMode: resolveDocumentPreviewMode(mimeType, docKind, content),
    previewText: content ?? safeStructuredFallback(metadata, "已生成文档候选"),
    metadataLines: [mimeType, docKind ? documentKindLabel(docKind) : null].filter(
      (value): value is string => Boolean(value),
    ),
    defaultChecked: false,
    canCommit: false,
    canOpenRoom: false,
    roomTarget: {
      room: "documents",
      itemId: readString(document.id),
      query: readString(document.name),
    },
  };
}

export function buildLibraryRoomPreview(
  item: Record<string, unknown>,
): WorkspaceResultPreview {
  const authors = readStringArray(item.authors);
  const year = typeof item.year === "number" ? String(item.year) : null;
  return {
    id: readString(item.id) ?? "library-item",
    source: "library_room",
    kind: "library_item",
    title: readString(item.title) ?? "未命名文献",
    subtitle: authors.length > 0 ? authors.join(", ") : null,
    badge: "文献",
    data: item,
    previewMode: "citation",
    previewText: safeRuntimeText(item.abstract) ?? safeRuntimeText(item.title),
    metadataLines: [year, readString(item.doi), readString(item.url)].filter(
      (value): value is string => Boolean(value),
    ),
    defaultChecked: false,
    canCommit: false,
    canOpenRoom: false,
    roomTarget: {
      room: "library",
      itemId: readString(item.id),
      query: readString(item.title),
    },
  };
}

function buildDocumentPreview(options: {
  id: string;
  preview: string | null;
  defaultChecked: boolean;
  data: Record<string, unknown> | null;
}): WorkspaceResultPreview {
  const { id, preview, defaultChecked, data } = options;
  const name = safeRuntimeText(data?.name);
  const mimeType = readString(data?.mime_type);
  const docKind = readString(data?.doc_kind);
  const content = safeContentText(data?.content);
  const previewText =
    firstNonNull(content, preview) ?? safeStructuredFallback(data, "已生成文档候选");

  return {
    id,
    source: "staged_output",
    kind: "document",
    title: firstNonNull(preview, name, id) ?? "文档",
    subtitle: name && preview !== name ? name : docKind ? documentKindLabel(docKind) : null,
    badge: "文档",
    data,
    previewMode: resolveDocumentPreviewMode(mimeType, docKind, content),
    previewText,
    metadataLines: [mimeType, docKind ? documentKindLabel(docKind) : null].filter(
      (value): value is string => Boolean(value),
    ),
    defaultChecked,
    canCommit: true,
    canOpenRoom: true,
    roomTarget: {
      room: "documents",
      query: firstNonNull(preview, name),
    },
  };
}

function buildLibraryPreview(options: {
  id: string;
  preview: string | null;
  defaultChecked: boolean;
  data: Record<string, unknown> | null;
}): WorkspaceResultPreview {
  const { id, preview, defaultChecked, data } = options;
  const title = firstNonNull(safeRuntimeText(data?.title), preview, id) ?? "文献";
  const authors = readStringArray(data?.authors);
  const year = typeof data?.year === "number" ? String(data.year) : null;
  const abstract = safeRuntimeText(data?.abstract);

  return {
    id,
    source: "staged_output",
    kind: "library_item",
    title,
    subtitle: authors.length > 0 ? authors.join(", ") : null,
    badge: "文献",
    data,
    previewMode: "citation",
    previewText: firstNonNull(abstract, preview, title),
    metadataLines: [year, readString(data?.doi), readString(data?.url)].filter(
      (value): value is string => Boolean(value),
    ),
    defaultChecked,
    canCommit: true,
    canOpenRoom: true,
    roomTarget: {
      room: "library",
      query: title,
    },
  };
}

function buildFigurePreview(options: {
  id: string;
  preview: string | null;
  defaultChecked: boolean;
  data: Record<string, unknown> | null;
}): WorkspaceResultPreview {
  const { id, preview, defaultChecked, data } = options;
  const manifest = readObject(data?.manifest);
  const title =
    firstNonNull(
      safeRuntimeText(data?.title),
      safeRuntimeText(data?.figure_title),
      preview,
      safeRuntimeText(data?.name),
    ) ?? "图表候选";
  const caption = summarizeText(
    firstNonNull(
      safeRuntimeText(data?.caption),
      safeRuntimeText(data?.caption_text),
      safeRuntimeText(manifest?.caption),
    ),
  );
  const previewPath = resolveFigurePreviewPath(data, preview);
  const metadata = buildFigureMetadata(data);

  return {
    id,
    source: "staged_output",
    kind: "figure",
    title,
    subtitle: caption,
    badge: "图表",
    data,
    previewMode: "image",
    previewPath,
    previewText: caption ?? previewPath ?? title,
    metadata,
    metadataLines: [],
    defaultChecked,
    canCommit: true,
    canOpenRoom: true,
    roomTarget: {
      room: "documents",
      query: title,
    },
  };
}

function resolveDocumentPreviewMode(
  mimeType: string | null,
  docKind: string | null,
  content: string | null,
): PreviewMode {
  if (!content) {
    return "structured_json";
  }
  if (docKind === "outline") {
    return "outline";
  }
  if (mimeType?.includes("markdown")) {
    return "markdown";
  }
  return "plain_text";
}

function isFigureDocument(data: Record<string, unknown> | null): boolean {
  const docKind = readString(data?.doc_kind);
  const artifactKind = readString(data?.artifact_kind);
  const mimeType = readString(data?.mime_type);
  return docKind === "figure" || artifactKind === "figure" || isImageMimeType(mimeType);
}

function isImageMimeType(value: string | null): boolean {
  return value?.toLowerCase().startsWith("image/") ?? false;
}

function isSandboxFigureReviewItem(item: Record<string, unknown>): boolean {
  const target = readObject(item.target);
  const preview = readObject(item.preview);
  const kind = readString(item.kind);
  const targetKind = readString(target?.kind);
  if (kind !== "sandbox_artifact" && targetKind !== "sandbox_artifact") {
    return false;
  }
  const path = firstNonNull(
    readString(preview?.path),
    readString(target?.path),
    readString(item.summary),
  );
  return (
    readString(target?.artifact_kind) === "figure" ||
    isImageMimeType(readString(preview?.mime_type)) ||
    Boolean(path && isWorkspaceImagePath(path))
  );
}

function resolveFigurePreviewPath(
  data: Record<string, unknown> | null,
  preview: string | null,
): string | null {
  return firstWorkspaceImagePath(
    readString(data?.primary_path),
    readString(data?.path),
    readString(data?.preview_path),
    readString(data?.artifact_path),
    preview && isWorkspaceImagePath(preview) ? preview : null,
  );
}

function firstWorkspaceImagePath(...values: Array<string | null>): string | null {
  for (const value of values) {
    if (value && isWorkspaceImagePath(value)) {
      return value;
    }
  }
  return null;
}

function isWorkspaceImagePath(value: string): boolean {
  return (
    value.startsWith("/workspace/") &&
    !isRawRuntimePayloadText(value) &&
    /\.(png|jpe?g|webp|gif|svg)$/i.test(value.split("?")[0] ?? value)
  );
}

function pathBasename(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const clean = value.split("?")[0] ?? value;
  return clean.split("/").filter(Boolean).at(-1) ?? null;
}

function summarizeText(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return value.length > 140 ? `${value.slice(0, 137).trimEnd()}...` : value;
}

function buildFigureMetadata(
  data: Record<string, unknown> | null,
): Record<string, unknown> | null {
  const metadata: Record<string, unknown> = {};
  for (const key of ["strategy", "figure_type", "provenance", "provider", "source"]) {
    const value = safeRuntimeText(data?.[key]);
    if (value) {
      metadata[key] = value;
    }
  }
  return Object.keys(metadata).length > 0 ? metadata : null;
}

function documentKindLabel(value: string): string {
  switch (value) {
    case "draft":
      return "初稿";
    case "outline":
      return "大纲";
    case "figure":
      return "图表";
    case "export":
      return "导出";
    case "upload":
      return "上传";
    default:
      return value;
  }
}
