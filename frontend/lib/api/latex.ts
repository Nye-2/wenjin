import { authorizedFetch, apiClient, readErrorMessage } from "@/lib/api/client";
import type {
  LatexCompileResult,
  LatexFeedbackItem,
  LatexFeedbackMapResponse,
  LatexFeedbackRewriteResponse,
  LatexFileItem,
  LatexProject,
  LatexProjectCreate,
  LatexTemplate,
} from "@/lib/api/types";

export async function listLatexProjects(params?: {
  include_trashed?: boolean;
}): Promise<{ projects: LatexProject[] }> {
  const response = await apiClient.get("/latex/projects", { params });
  return response.data;
}

export async function createLatexProject(
  payload: LatexProjectCreate,
): Promise<LatexProject> {
  const response = await apiClient.post("/latex/projects", payload);
  return response.data;
}

export async function getLatexProject(projectId: string): Promise<LatexProject> {
  const response = await apiClient.get(`/latex/projects/${projectId}`);
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
  const response = await apiClient.patch(`/latex/projects/${projectId}`, payload);
  return response.data;
}

export async function deleteLatexProject(projectId: string): Promise<void> {
  await apiClient.delete(`/latex/projects/${projectId}`);
}

export async function permanentlyDeleteLatexProject(projectId: string): Promise<void> {
  await apiClient.delete(`/latex/projects/${projectId}/permanent`);
}

export async function getLatexProjectTree(
  projectId: string,
): Promise<{ items: LatexFileItem[]; file_order: Record<string, string[]> }> {
  const response = await apiClient.get(`/latex/projects/${projectId}/tree`);
  return response.data;
}

export async function readLatexFile(
  projectId: string,
  path: string,
): Promise<{ content: string }> {
  const response = await apiClient.get(`/latex/projects/${projectId}/file`, {
    params: { path },
  });
  return response.data;
}

export async function writeLatexFile(
  projectId: string,
  path: string,
  content: string,
): Promise<void> {
  await apiClient.put(`/latex/projects/${projectId}/file`, { path, content });
}

export async function createLatexFolder(
  projectId: string,
  path: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.post(`/latex/projects/${projectId}/folder`, { path });
  return response.data;
}

export async function renameLatexPath(
  projectId: string,
  fromPath: string,
  toPath: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.post(`/latex/projects/${projectId}/rename`, {
    from: fromPath,
    to: toPath,
  });
  return response.data;
}

export async function deleteLatexPath(
  projectId: string,
  path: string,
): Promise<{ ok: boolean; path: string }> {
  const response = await apiClient.delete(`/latex/projects/${projectId}/path`, {
    params: { path },
  });
  return response.data;
}

export async function saveLatexFileOrder(
  projectId: string,
  folder: string,
  order: string[],
): Promise<void> {
  await apiClient.post(`/latex/projects/${projectId}/file-order`, {
    folder,
    order,
  });
}

export async function uploadLatexFiles(
  projectId: string,
  files: File[],
  basePath?: string,
): Promise<{ ok: boolean; files: string[] }> {
  const form = new FormData();
  for (const file of files) {
    const relativePath =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
      file.name;
    form.append("files", file, relativePath);
  }
  if (basePath) {
    form.append("base_path", basePath);
  }
  const response = await apiClient.post(
    `/latex/projects/${projectId}/upload`,
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
    engine: "xelatex" | "pdflatex";
  },
): Promise<LatexCompileResult> {
  const response = await apiClient.post(`/latex/projects/${projectId}/compile`, payload);
  return response.data;
}

export async function fetchLatexCompiledPdfBlob(
  projectId: string,
  historyId: string,
): Promise<Blob> {
  const response = await authorizedFetch(
    `/api/latex/projects/${projectId}/compile/${historyId}/pdf`,
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
    `/api/latex/projects/${projectId}/compile/${historyId}/synctex`,
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
    `/api/latex/projects/${projectId}/blob?path=${encodeURIComponent(path)}`,
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Failed to load project blob"));
  }
  return response.blob();
}

export async function listLatexTemplates(): Promise<{ templates: LatexTemplate[] }> {
  const response = await apiClient.get("/latex/templates");
  return response.data;
}

export async function resolveLatexConflict(
  projectId: string,
  payload: {
    logical_key: string;
    strategy: "keep_current" | "accept_feature";
    feature_content?: string | null;
  },
): Promise<{ ok: boolean; path: string; strategy: string }> {
  const response = await apiClient.post(
    `/latex/projects/${projectId}/resolve-conflict`,
    payload,
  );
  return response.data;
}

export async function getLatexProjectFeedback(
  projectId: string,
): Promise<{ ok: boolean; items: LatexFeedbackItem[] }> {
  const response = await apiClient.get(`/latex/projects/${projectId}/feedback`);
  return response.data;
}

export async function saveLatexProjectFeedback(
  projectId: string,
  items: LatexFeedbackItem[],
): Promise<{ ok: boolean }> {
  const response = await apiClient.put(`/latex/projects/${projectId}/feedback`, { items });
  return response.data;
}

export async function rewriteLatexFeedback(
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
    apply?: boolean;
  },
): Promise<LatexFeedbackRewriteResponse> {
  const response = await apiClient.post(`/latex/projects/${projectId}/feedback/rewrite`, payload);
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
  const response = await apiClient.post(`/latex/projects/${projectId}/feedback/map`, payload);
  return response.data;
}
