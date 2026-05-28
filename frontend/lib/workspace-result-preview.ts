type PreviewMode =
  | "markdown"
  | "plain_text"
  | "outline"
  | "citation"
  | "json_fallback";

type PreviewKind =
  | "document"
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
  source: "staged_output" | "document_room" | "library_room";
  kind: PreviewKind;
  data?: Record<string, unknown> | null;
  title: string;
  subtitle: string | null;
  badge: string | null;
  previewMode: PreviewMode;
  previewText: string | null;
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
    const preview = readString(output.preview);
    const defaultChecked = output.default_checked !== false;

    switch (kind) {
      case "document":
        return [
          buildDocumentPreview({
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
            title: preview ?? "Memory fact",
            subtitle: readString(data?.category),
            badge: "Memory",
            data,
            previewMode: "plain_text",
            previewText:
              readString(data?.content) ?? preview ?? JSON.stringify(data, null, 2),
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
            title: preview ?? readString(data?.key) ?? "Decision",
            subtitle: readString(data?.key),
            badge: "Decision",
            data,
            previewMode: "plain_text",
            previewText:
              readString(data?.value) ?? preview ?? JSON.stringify(data, null, 2),
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
            title: preview ?? readString(data?.title) ?? "Task",
            subtitle: readString(data?.priority)
              ? `Priority ${readString(data?.priority)}`
              : null,
            badge: "Task",
            data,
            previewMode: "plain_text",
            previewText:
              readString(data?.description) ??
              preview ??
              JSON.stringify(data, null, 2),
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

export function buildDocumentRoomPreview(
  document: Record<string, unknown>,
): WorkspaceResultPreview {
  const metadata = readObject(document.metadata_json);
  const mimeType = readString(document.mime_type);
  const docKind = readString(document.doc_kind) ?? readString(document.kind);
  const content = readString(metadata?.content);
  return {
    id: readString(document.id) ?? "document",
    source: "document_room",
    kind: "document",
    title: readString(document.name) ?? "Untitled document",
    subtitle: docKind ? capitalize(docKind) : mimeType,
    badge: "Document",
    data: document,
    previewMode: resolveDocumentPreviewMode(mimeType, docKind, content),
    previewText: content,
    metadataLines: [mimeType, docKind ? capitalize(docKind) : null].filter(
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
    title: readString(item.title) ?? "Untitled reference",
    subtitle: authors.length > 0 ? authors.join(", ") : null,
    badge: "Reference",
    data: item,
    previewMode: "citation",
    previewText: readString(item.abstract),
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
  const name = readString(data?.name);
  const mimeType = readString(data?.mime_type);
  const docKind = readString(data?.doc_kind);
  const content = readString(data?.content);

  return {
    id,
    source: "staged_output",
    kind: "document",
    title: firstNonNull(preview, name, id) ?? "Document",
    subtitle: name && preview !== name ? name : docKind ? capitalize(docKind) : null,
    badge: "Document",
    data,
    previewMode: resolveDocumentPreviewMode(mimeType, docKind, content),
    previewText: firstNonNull(content, preview),
    metadataLines: [mimeType, docKind ? capitalize(docKind) : null].filter(
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
  const title = firstNonNull(readString(data?.title), preview, id) ?? "Reference";
  const authors = readStringArray(data?.authors);
  const year = typeof data?.year === "number" ? String(data.year) : null;
  const abstract = readString(data?.abstract);

  return {
    id,
    source: "staged_output",
    kind: "library_item",
    title,
    subtitle: authors.length > 0 ? authors.join(", ") : null,
    badge: "Reference",
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

function resolveDocumentPreviewMode(
  mimeType: string | null,
  docKind: string | null,
  content: string | null,
): PreviewMode {
  if (!content) {
    return "json_fallback";
  }
  if (docKind === "outline") {
    return "outline";
  }
  if (mimeType?.includes("markdown")) {
    return "markdown";
  }
  return "plain_text";
}

function capitalize(value: string): string {
  if (!value) {
    return value;
  }
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}
