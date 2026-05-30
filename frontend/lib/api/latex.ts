import { authorizedFetch, apiClient, readErrorMessage } from "@/lib/api/client";
import type {
  LatexCompileEngine,
  LatexCompileResult,
  LatexFileChangeApplyResponse,
  LatexFileChangeDiscardResponse,
  LatexFileChangePreviewResponse,
  LatexFileChangeRevertResponse,
  LatexProtectedSectionResponse,
  LatexFeedbackItem,
  LatexFeedbackRewriteApplyResponse,
  LatexFeedbackRewritePreviewResponse,
  LatexFeedbackRewriteRevertResponse,
  LatexFeedbackMapResponse,
  LatexFileItem,
  LatexProject,
  LatexProjectCreate,
  LatexTemplate,
} from "@/lib/api/types";

interface UploadLatexFilesOptions {
  flatten_root_directory?: boolean;
}

function normalizeUploadPath(rawPath: string): string {
  return rawPath.replace(/\\/g, "/").replace(/^\/+/, "").trim();
}

function resolveDirectoryRootPrefix(paths: string[]): string | null {
  if (!paths.length) {
    return null;
  }
  const first = paths[0].split("/").filter(Boolean);
  if (first.length < 2) {
    return null;
  }
  const root = first[0];
  for (const currentPath of paths) {
    const parts = currentPath.split("/").filter(Boolean);
    if (parts.length < 2 || parts[0] !== root) {
      return null;
    }
  }
  return root;
}

function buildUploadEntries(
  files: File[],
  options?: UploadLatexFilesOptions,
): Array<{ file: File; relativePath: string }> {
  const entries = files.map((file) => {
    const webkitRelativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    const rawPath = normalizeUploadPath(webkitRelativePath || file.name);
    return {
      file,
      relativePath: rawPath || normalizeUploadPath(file.name),
    };
  });

  if (!options?.flatten_root_directory) {
    return entries;
  }

  const rootPrefix = resolveDirectoryRootPrefix(entries.map((entry) => entry.relativePath));
  if (!rootPrefix) {
    return entries;
  }

  const stripPrefix = `${rootPrefix}/`;
  return entries.map((entry) => {
    const nextPath = entry.relativePath.startsWith(stripPrefix)
      ? entry.relativePath.slice(stripPrefix.length)
      : entry.relativePath;
    return {
      file: entry.file,
      relativePath: nextPath || normalizeUploadPath(entry.file.name),
    };
  });
}

function collectFolderHintsFromEntries(entries: Array<{ relativePath: string }>): string[] {
  const folders = new Set<string>();
  for (const entry of entries) {
    const parts = entry.relativePath.split("/").filter(Boolean);
    if (parts.length <= 1) {
      continue;
    }
    for (let index = 1; index < parts.length; index += 1) {
      const folder = parts.slice(0, index).join("/");
      if (folder) {
        folders.add(folder);
      }
    }
  }
  return Array.from(folders).sort((left, right) => {
    const depthDelta = left.split("/").length - right.split("/").length;
    return depthDelta !== 0 ? depthDelta : left.localeCompare(right);
  });
}

export async function listLatexProjects(params?: {
  include_trashed?: boolean;
}): Promise<{ projects: LatexProject[] }> {
  const response = await apiClient.get("/prism/latex-adapter/projects", { params });
  return response.data;
}

export async function createLatexProject(
  payload: LatexProjectCreate,
): Promise<LatexProject> {
  const response = await apiClient.post("/prism/latex-adapter/projects", payload);
  return response.data;
}

export async function getLatexProject(projectId: string): Promise<LatexProject> {
  const response = await apiClient.get(`/prism/latex-adapter/projects/${projectId}`);
  return response.data;
}

export async function updateLatexProject(
  projectId: string,
  payload: Partial<LatexProjectCreate> & {
    main_file?: string;
    tags?: string[];
    archived?: boolean;
    trashed?: boolean;
    file_order?: Record<string, string[]>;
  },
): Promise<LatexProject> {
  const response = await apiClient.patch(`/prism/latex-adapter/projects/${projectId}`, payload);
  return response.data;
}

export async function deleteLatexProject(projectId: string): Promise<void> {
  await apiClient.delete(`/prism/latex-adapter/projects/${projectId}`);
}

export async function permanentlyDeleteLatexProject(projectId: string): Promise<void> {
  await apiClient.delete(`/prism/latex-adapter/projects/${projectId}/permanent`);
}

export async function getLatexProjectTree(
  projectId: string,
): Promise<{ items: LatexFileItem[]; file_order: Record<string, string[]> }> {
  const response = await apiClient.get(`/prism/latex-adapter/projects/${projectId}/tree`);
  return response.data;
}

export async function readLatexFile(
  projectId: string,
  path: string,
): Promise<{ content: string }> {
  const response = await apiClient.get(`/prism/latex-adapter/projects/${projectId}/file`, {
    params: { path },
  });
  return response.data;
}

export async function writeLatexFile(
  projectId: string,
  path: string,
  content: string,
): Promise<void> {
  await apiClient.put(`/prism/latex-adapter/projects/${projectId}/file`, { path, content });
}

export async function createLatexFolder(
  projectId: string,
  path: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/folder`, { path });
  return response.data;
}

export async function renameLatexPath(
  projectId: string,
  fromPath: string,
  toPath: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/rename`, {
    from: fromPath,
    to: toPath,
  });
  return response.data;
}

export async function deleteLatexPath(
  projectId: string,
  path: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.delete(`/prism/latex-adapter/projects/${projectId}/path`, {
    params: { path },
  });
  return response.data;
}

export async function saveLatexFileOrder(
  projectId: string,
  folder: string,
  order: string[],
): Promise<void> {
  await apiClient.post(`/prism/latex-adapter/projects/${projectId}/file-order`, {
    folder,
    order,
  });
}

export async function uploadLatexFiles(
  projectId: string,
  files: File[],
  basePath?: string,
  options?: UploadLatexFilesOptions,
): Promise<{ ok: boolean; files: string[] }> {
  const entries = buildUploadEntries(files, options);
  const folders = collectFolderHintsFromEntries(entries);
  const form = new FormData();
  for (const entry of entries) {
    form.append("files", entry.file, entry.relativePath);
  }
  if (basePath) {
    form.append("base_path", basePath);
  }
  for (const folder of folders) {
    if (folder.trim()) {
      form.append("folders", folder.trim());
    }
  }
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/upload`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return response.data;
}

export async function uploadLatexArchive(
  projectId: string,
  archive: File,
  basePath?: string,
): Promise<{ ok: boolean; files: string[] }> {
  const form = new FormData();
  form.append("archive", archive, archive.name);
  if (basePath) {
    form.append("base_path", basePath);
  }
  form.append("strip_root", "true");
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/upload-archive`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return response.data;
}

export async function compileLatexProject(
  projectId: string,
  payload: {
    main_file?: string | null;
    engine: LatexCompileEngine;
  },
): Promise<LatexCompileResult> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/compile`, payload);
  return response.data;
}

export async function fetchLatexCompiledPdfBlob(
  projectId: string,
  historyId: string,
): Promise<Blob> {
  const response = await authorizedFetch(
    `/api/prism/latex-adapter/projects/${projectId}/compile/${historyId}/pdf`,
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Failed to load compiled PDF"));
  }
  return response.blob();
}

export async function fetchLatexCompiledSynctexBlob(
  projectId: string,
  historyId: string,
): Promise<Blob> {
  const response = await authorizedFetch(
    `/api/prism/latex-adapter/projects/${projectId}/compile/${historyId}/synctex`,
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Failed to load synctex file"));
  }
  return response.blob();
}

export async function fetchLatexProjectBlob(
  projectId: string,
  path: string,
): Promise<Blob> {
  const response = await authorizedFetch(
    `/api/prism/latex-adapter/projects/${projectId}/blob?path=${encodeURIComponent(path)}`,
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Failed to load project blob"));
  }
  return response.blob();
}

export async function listLatexTemplates(): Promise<{ templates: LatexTemplate[] }> {
  const response = await apiClient.get("/prism/latex-adapter/templates");
  return response.data;
}

export async function previewLatexFileChange(
  projectId: string,
  payload: {
    logical_key: string;
  },
): Promise<LatexFileChangePreviewResponse> {
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/file-changes/preview`,
    payload,
  );
  return response.data;
}

export async function applyLatexFileChange(
  projectId: string,
  payload: {
    logical_key: string;
    change_signature: string;
  },
): Promise<LatexFileChangeApplyResponse> {
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/file-changes/apply`,
    payload,
  );
  return response.data;
}

export async function discardLatexFileChange(
  projectId: string,
  payload: {
    logical_key: string;
  },
): Promise<LatexFileChangeDiscardResponse> {
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/file-changes/discard`,
    payload,
  );
  return response.data;
}

export async function revertLatexFileChange(
  projectId: string,
  payload: {
    logical_key: string;
    revert_signature: string;
  },
): Promise<LatexFileChangeRevertResponse> {
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/file-changes/revert`,
    payload,
  );
  return response.data;
}

export async function protectLatexSection(
  projectId: string,
  payload: {
    path: string;
    section_key?: string | null;
    scope: "file" | "section";
    reason?: string | null;
  },
): Promise<LatexProtectedSectionResponse> {
  const response = await apiClient.post(
    `/prism/latex-adapter/projects/${projectId}/protected-sections`,
    payload,
  );
  return response.data;
}

export async function getLatexProjectFeedback(
  projectId: string,
): Promise<{ ok: boolean; items: LatexFeedbackItem[] }> {
  const response = await apiClient.get(`/prism/latex-adapter/projects/${projectId}/feedback`);
  return response.data;
}

export async function saveLatexProjectFeedback(
  projectId: string,
  items: LatexFeedbackItem[],
): Promise<{ ok: boolean }> {
  const response = await apiClient.put(`/prism/latex-adapter/projects/${projectId}/feedback`, { items });
  return response.data;
}

export async function previewLatexFeedbackRewrite(
  projectId: string,
  payload: {
    file_path: string;
    selected_text: string;
    comment: string;
    selection_start?: number;
    selection_end?: number;
    anchor?: {
      selected_text: string;
      prefix: string;
      suffix: string;
      heading_title: string;
      heading_level: string;
      line_hint: number;
    } | null;
    scope?: "selection" | "section";
    model_id?: string | null;
    file_content?: string | null;
  },
): Promise<LatexFeedbackRewritePreviewResponse> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/feedback/rewrite/preview`, payload);
  return response.data;
}

export async function applyLatexFeedbackRewrite(
  projectId: string,
  payload: {
    file_path: string;
    candidate_id: string;
    candidate_signature: string;
    target_start: number;
    target_end: number;
    rewritten_text: string;
    base_file_hash: string;
    base_range_hash: string;
  },
): Promise<LatexFeedbackRewriteApplyResponse> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/feedback/rewrite/apply`, payload);
  return response.data;
}

export async function revertLatexFeedbackRewrite(
  projectId: string,
  payload: {
    file_path: string;
    candidate_id: string;
    revert_start: number;
    revert_end: number;
    rewritten_text: string;
    previous_text: string;
    applied_file_hash: string;
    revert_signature: string;
  },
): Promise<LatexFeedbackRewriteRevertResponse> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/feedback/rewrite/revert`, payload);
  return response.data;
}

export async function mapLatexFeedbackSelection(
  projectId: string,
  payload: {
    file_path: string;
    selected_text: string;
    selection_start?: number;
    selection_end?: number;
    anchor?: {
      selected_text: string;
      prefix: string;
      suffix: string;
      heading_title: string;
      heading_level: string;
      line_hint: number;
    } | null;
    history_id?: string | null;
    pdf_anchor?: {
      page: number;
      text: string;
      rects: Array<{ x: number; y: number; width: number; height: number }>;
    } | null;
    file_content?: string | null;
    source?: "tex" | "pdf";
  },
): Promise<LatexFeedbackMapResponse> {
  const response = await apiClient.post(`/prism/latex-adapter/projects/${projectId}/feedback/map`, payload);
  return response.data;
}
