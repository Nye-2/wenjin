import { API_SERVER_BASE_URL } from "@/lib/api-base";

function isAbsoluteUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function normalizeRelativeUrl(value: string): string {
  if (!value.startsWith("/")) {
    return `/${value}`;
  }
  return value;
}

function sandboxPathToPublicUrl(path: string): string | null {
  const prefix = "/mnt/user-data/";
  if (!path.startsWith(prefix)) {
    return null;
  }

  const relative = path.slice(prefix.length).replace(/^\/+/, "");
  return `/uploads/sandboxes/default/${relative}`;
}

export function resolvePublicAssetUrl(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const sandboxUrl = sandboxPathToPublicUrl(trimmed);
  const normalized = sandboxUrl ?? normalizeRelativeUrl(trimmed);
  if (isAbsoluteUrl(trimmed)) {
    return trimmed;
  }

  if (API_SERVER_BASE_URL) {
    return `${API_SERVER_BASE_URL}${normalized}`;
  }
  return normalized;
}

export function extractArtifactFileUrl(
  content: Record<string, unknown> | null | undefined
): string | null {
  if (!content) {
    return null;
  }

  const directCandidates = [
    content.file_url,
    content.stored_url,
    content.thread_url,
    content.public_url,
    content.pdf_url,
    content.file_path,
    content.pdf_path,
  ];
  for (const candidate of directCandidates) {
    if (typeof candidate === "string") {
      const resolved = resolvePublicAssetUrl(candidate);
      if (resolved) {
        return resolved;
      }
    }
  }

  const renderData =
    content.render_data && typeof content.render_data === "object"
      ? (content.render_data as Record<string, unknown>)
      : null;
  if (renderData) {
    const nestedCandidates = [
      renderData.file_url,
      renderData.stored_url,
      renderData.thread_url,
      renderData.public_url,
      renderData.file_path,
    ];
    for (const candidate of nestedCandidates) {
      if (typeof candidate === "string") {
        const resolved = resolvePublicAssetUrl(candidate);
        if (resolved) {
          return resolved;
        }
      }
    }
  }

  return null;
}

export function isPdfUrl(url: string | null | undefined): boolean {
  return Boolean(url && /\.pdf($|\?)/i.test(url));
}

export function isImageUrl(url: string | null | undefined): boolean {
  return Boolean(url && /\.(png|jpg|jpeg|gif|svg|webp)($|\?)/i.test(url));
}
