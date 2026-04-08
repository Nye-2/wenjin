import { API_BASE_URL, API_SERVER_BASE_URL } from "@/lib/api-base";
import { authorizedFetch, readErrorMessage } from "@/lib/api/client";

const SIGNED_ASSET_URL_CACHE = new Map<string, string>();

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

function hasSignedAssetParams(url: string): boolean {
  return /(?:\?|&)(?:exp|sig)=/i.test(url);
}

function isProtectedAssetUrl(url: string): boolean {
  try {
    const parsed = new URL(url, typeof window !== "undefined" ? window.location.origin : "http://localhost");
    return (
      parsed.pathname.startsWith("/api/workspaces/") &&
      parsed.pathname.includes("/files/")
    ) || (
      parsed.pathname.startsWith("/api/threads/") &&
      parsed.pathname.includes("/artifacts/")
    );
  } catch {
    return false;
  }
}

export async function getSignedAssetUrl(
  url: string,
): Promise<string> {
  const normalizedUrl = resolvePublicAssetUrl(url);
  if (!normalizedUrl) {
    throw new Error("无效文件地址");
  }
  if (!isProtectedAssetUrl(normalizedUrl) || hasSignedAssetParams(normalizedUrl)) {
    return normalizedUrl;
  }

  const cached = SIGNED_ASSET_URL_CACHE.get(normalizedUrl);
  if (cached) {
    return cached;
  }

  const response = await authorizedFetch(`${API_BASE_URL}/assets/sign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: normalizedUrl }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "生成签名链接失败"));
  }

  const payload = (await response.json()) as { signed_url?: string };
  const signedUrl = resolvePublicAssetUrl(payload.signed_url ?? null);
  if (!signedUrl) {
    throw new Error("签名链接无效");
  }
  SIGNED_ASSET_URL_CACHE.set(normalizedUrl, signedUrl);
  return signedUrl;
}

export async function openAuthorizedAsset(
  url: string,
  options: {
    target?: "_blank" | "_self";
  } = {},
): Promise<void> {
  const { target = "_blank" } = options;
  const normalizedUrl = await getSignedAssetUrl(url);

  const popup =
    typeof window !== "undefined" && target === "_blank"
      ? window.open("", "_blank", "noopener,noreferrer")
      : null;

  try {
    if (target === "_self") {
      window.location.assign(normalizedUrl);
    } else if (popup) {
      popup.location.href = normalizedUrl;
    } else {
      window.open(normalizedUrl, "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    popup?.close();
    throw error;
  }
}
