import { create } from "zustand";

import type {
  LatexAppliedFileChange,
  LatexCompileEngine,
  LatexCompileResult,
  LatexFileChange,
  LatexFileItem,
  LatexProject,
  LatexTemplate,
} from "@/lib/api";
import {
  applyLatexFileChange,
  compileLatexProject,
  createLatexFolder,
  createLatexProject,
  deleteLatexProject,
  deleteLatexPath,
  discardLatexFileChange,
  fetchLatexProjectBlob,
  fetchLatexCompiledPdfBlob,
  getLatexProject,
  getLatexProjectTree,
  listLatexProjects,
  listLatexTemplates,
  readLatexFile,
  renameLatexPath,
  previewLatexFileChange,
  revertLatexFileChange,
  saveLatexFileOrder,
  uploadLatexArchive,
  uploadLatexFiles,
  writeLatexFile,
} from "@/lib/api";

interface LatexState {
  projects: LatexProject[];
  templates: LatexTemplate[];
  project: LatexProject | null;
  tree: LatexFileItem[];
  activeFilePath: string | null;
  activeFileKind: "text" | "blob" | null;
  activeFileContent: string;
  activeFileSavedContent: string;
  activeBlobUrl: string | null;
  fileChanges: LatexFileChange[];
  appliedFileChanges: LatexAppliedFileChange[];
  compileResult: LatexCompileResult | null;
  compileLog: string;
  compiledPdfUrl: string | null;
  isProjectsLoading: boolean;
  isProjectLoading: boolean;
  isFileLoading: boolean;
  isSaving: boolean;
  isCompiling: boolean;
  error: string | null;
  fetchProjects: () => Promise<void>;
  fetchTemplates: () => Promise<void>;
  createProject: (payload: { name: string; template_id?: string | null }) => Promise<LatexProject>;
  loadProject: (projectId: string) => Promise<void>;
  setReviewState: (
    fileChanges: LatexFileChange[],
    appliedFileChanges: LatexAppliedFileChange[],
  ) => void;
  openFile: (path: string) => Promise<void>;
  setActiveFileContent: (content: string) => void;
  saveActiveFile: () => Promise<void>;
  createFile: (path: string) => Promise<void>;
  createFolder: (path: string) => Promise<void>;
  renamePath: (fromPath: string, toPath: string) => Promise<void>;
  deletePath: (path: string) => Promise<void>;
  saveOrder: (folder: string, order: string[]) => Promise<void>;
  uploadFiles: (files: File[], folder?: string) => Promise<void>;
  uploadDirectory: (files: File[], folder?: string) => Promise<void>;
  uploadArchive: (archive: File, folder?: string) => Promise<void>;
  applyFileChange: (
    logicalKey: string,
  ) => Promise<void>;
  discardFileChange: (logicalKey: string) => Promise<void>;
  revertFileChange: (logicalKey: string, revertSignature: string) => Promise<void>;
  deleteProject: () => Promise<void>;
  compileProject: (engine?: LatexCompileEngine) => Promise<void>;
  clearCompiledPdf: () => void;
  clearActiveBlob: () => void;
  clearError: () => void;
}

function isTextFilePath(path: string): boolean {
  return [".tex", ".bib", ".cls", ".sty", ".txt", ".md", ".json", ".yaml", ".yml"]
    .some((suffix) => path.toLowerCase().endsWith(suffix));
}

function normalizeCompileResult(result: LatexCompileResult): LatexCompileResult {
  if (result.ok) {
    return result;
  }

  const combined = `${result.error || ""}\n${result.log || ""}`.toLowerCase();
  if (
    result.engine === "pdflatex"
    && (
      combined.includes("ctex-engine-pdftex.def")
      || combined.includes("cjkutf8.sty")
      || combined.includes("cjkpunct")
      || combined.includes("cjkspace")
      || combined.includes("ctexart.cls")
    )
  ) {
    return {
      ...result,
      error:
        "PDFLaTeX cannot compile this ctex/CJK Chinese manuscript in the current runtime. Use XeLaTeX for Chinese or mixed-language documents.",
    };
  }

  return result;
}

function pickDefaultFile(
  tree: LatexFileItem[],
  project: LatexProject | null,
): string | null {
  const files = tree.filter(
    (item) =>
      item.type === "file" &&
      [".tex", ".bib", ".cls", ".sty", ".txt", ".md"].some((suffix) =>
        item.path.toLowerCase().endsWith(suffix),
      ),
  );
  if (!files.length) {
    return null;
  }
  const mainFile = project?.main_file;
  if (mainFile && files.some((item) => item.path === mainFile)) {
    return mainFile;
  }
  const mainTex = files.find((item) => item.path.endsWith("main.tex"));
  if (mainTex) {
    return mainTex.path;
  }
  return files[0].path;
}

export const useLatexStore = create<LatexState>((set, get) => ({
  projects: [],
  templates: [],
  project: null,
  tree: [],
  activeFilePath: null,
  activeFileKind: null,
  activeFileContent: "",
  activeFileSavedContent: "",
  activeBlobUrl: null,
  fileChanges: [],
  appliedFileChanges: [],
  compileResult: null,
  compileLog: "",
  compiledPdfUrl: null,
  isProjectsLoading: false,
  isProjectLoading: false,
  isFileLoading: false,
  isSaving: false,
  isCompiling: false,
  error: null,

  fetchProjects: async () => {
    set({ isProjectsLoading: true, error: null });
    try {
      const response = await listLatexProjects();
      set({ projects: response.projects, isProjectsLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isProjectsLoading: false });
    }
  },

  fetchTemplates: async () => {
    try {
      const response = await listLatexTemplates();
      set({ templates: response.templates });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  createProject: async (payload) => {
    const project = await createLatexProject(payload);
    set((state) => ({ projects: [project, ...state.projects] }));
    return project;
  },

  loadProject: async (projectId) => {
    set({
      isProjectLoading: true,
      error: null,
      project: null,
      tree: [],
      activeFilePath: null,
      activeFileKind: null,
      activeFileContent: "",
      activeFileSavedContent: "",
      activeBlobUrl: null,
      fileChanges: [],
      appliedFileChanges: [],
      compileResult: null,
      compileLog: "",
    });
    get().clearCompiledPdf();
    get().clearActiveBlob();
    try {
      const [project, treeResponse] = await Promise.all([
        getLatexProject(projectId),
        getLatexProjectTree(projectId),
      ]);
      const defaultFile = pickDefaultFile(treeResponse.items, project);
      set({
        project,
        tree: treeResponse.items,
        fileChanges: [],
        appliedFileChanges: [],
        activeFilePath: defaultFile,
        isProjectLoading: false,
      });
      if (defaultFile) {
        await get().openFile(defaultFile);
      }
    } catch (error) {
      set({ error: (error as Error).message, isProjectLoading: false });
    }
  },

  setReviewState: (fileChanges, appliedFileChanges) => {
    set({
      fileChanges: [...fileChanges],
      appliedFileChanges: [...appliedFileChanges],
    });
  },

  openFile: async (path) => {
    const {
      project,
      activeFilePath,
      activeFileKind,
      activeFileContent,
      activeFileSavedContent,
    } = get();
    if (!project) {
      return;
    }
    if (
      activeFileKind === "text"
      && activeFilePath
      && activeFilePath !== path
      && activeFileContent !== activeFileSavedContent
    ) {
      set({ isSaving: true, error: null });
      try {
        await writeLatexFile(project.id, activeFilePath, activeFileContent);
        set({
          activeFileSavedContent: activeFileContent,
          isSaving: false,
        });
      } catch (error) {
        set({ error: (error as Error).message, isSaving: false });
        return;
      }
    }
    set({ isFileLoading: true, error: null });
    get().clearActiveBlob();
    try {
      if (isTextFilePath(path)) {
        const response = await readLatexFile(project.id, path);
        set({
          activeFilePath: path,
          activeFileKind: "text",
          activeFileContent: response.content,
          activeFileSavedContent: response.content,
          isFileLoading: false,
        });
      } else {
        const blob = await fetchLatexProjectBlob(project.id, path);
        const activeBlobUrl = URL.createObjectURL(blob);
        set({
          activeFilePath: path,
          activeFileKind: "blob",
          activeFileContent: "",
          activeFileSavedContent: "",
          activeBlobUrl,
          isFileLoading: false,
        });
      }
    } catch (error) {
      set({ error: (error as Error).message, isFileLoading: false });
    }
  },

  setActiveFileContent: (content) => {
    set({ activeFileContent: content });
  },

  saveActiveFile: async () => {
    const { project, activeFilePath, activeFileContent, activeFileKind } = get();
    if (!project || !activeFilePath || activeFileKind !== "text") {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await writeLatexFile(project.id, activeFilePath, activeFileContent);
      set({
        activeFileSavedContent: activeFileContent,
        isSaving: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  createFile: async (path) => {
    const { project } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await writeLatexFile(project.id, path, "");
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
      await get().openFile(path);
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  createFolder: async (path) => {
    const { project } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await createLatexFolder(project.id, path);
      const treeResponse = await getLatexProjectTree(project.id);
      set({
        tree: treeResponse.items,
        isSaving: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  renamePath: async (fromPath, toPath) => {
    const { project, activeFilePath } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await renameLatexPath(project.id, fromPath, toPath);
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
      if (activeFilePath === fromPath || activeFilePath?.startsWith(`${fromPath}/`)) {
        const nextActivePath =
          activeFilePath === fromPath
            ? toPath
            : `${toPath}${activeFilePath.slice(fromPath.length)}`;
        await get().openFile(nextActivePath);
      }
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  deletePath: async (path) => {
    const { project, activeFilePath } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await deleteLatexPath(project.id, path);
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      const nextDefaultFile = pickDefaultFile(treeResponse.items, nextProject);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
      if (activeFilePath === path || activeFilePath?.startsWith(`${path}/`)) {
        if (nextDefaultFile) {
          await get().openFile(nextDefaultFile);
        } else {
          get().clearActiveBlob();
          set({
            activeFilePath: null,
            activeFileKind: null,
            activeFileContent: "",
            activeFileSavedContent: "",
          });
        }
      }
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  saveOrder: async (folder, order) => {
    const { project } = get();
    if (!project) {
      return;
    }
    try {
      await saveLatexFileOrder(project.id, folder, order);
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
      });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  uploadFiles: async (files, folder) => {
    const { project } = get();
    if (!project || !files.length) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await uploadLatexFiles(project.id, files, folder, {
        flatten_root_directory: false,
      });
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  uploadDirectory: async (files, folder) => {
    const { project } = get();
    if (!project || !files.length) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await uploadLatexFiles(project.id, files, folder, {
        flatten_root_directory: true,
      });
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  uploadArchive: async (archive, folder) => {
    const { project } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await uploadLatexArchive(project.id, archive, folder);
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set({
        project: nextProject,
        tree: treeResponse.items,
        isSaving: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  applyFileChange: async (logicalKey) => {
    const { project, activeFilePath, activeFileKind } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      const preview = await previewLatexFileChange(project.id, {
        logical_key: logicalKey,
      });
      const applied = await applyLatexFileChange(project.id, {
        logical_key: logicalKey,
        change_signature: preview.change_signature,
      });
      const shouldRefreshActiveFile =
        activeFileKind === "text" && activeFilePath === applied.path;
      const [nextProject, treeResponse, activeFileResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
        shouldRefreshActiveFile
          ? readLatexFile(project.id, applied.path)
          : Promise.resolve(null),
      ]);
      set((state) => {
        const pendingChange = state.fileChanges.find(
          (item) => item.logical_key === logicalKey,
        );
        return {
          project: nextProject,
          tree: treeResponse.items,
          fileChanges: state.fileChanges.filter(
            (item) => item.logical_key !== logicalKey,
          ),
          appliedFileChanges: [
            {
              id: pendingChange?.id ?? null,
              logical_key: applied.undo.logical_key,
              path: applied.undo.path,
              reason: pendingChange?.reason ?? null,
              status: "applied",
              title: pendingChange?.title ?? pendingChange?.path ?? null,
              source_type: pendingChange?.source_type ?? null,
              source_execution_id: pendingChange?.source_execution_id ?? null,
              source_task_id: pendingChange?.source_task_id ?? null,
              previous_hash: applied.undo.previous_hash,
              applied_hash: applied.undo.applied_hash,
              revert_signature: applied.undo.revert_signature,
              applied_at: new Date().toISOString(),
            },
            ...state.appliedFileChanges.filter(
              (item) => item.logical_key !== logicalKey,
            ),
          ],
          ...(activeFileResponse
            ? {
                activeFileContent: activeFileResponse.content,
                activeFileSavedContent: activeFileResponse.content,
              }
            : {}),
          isSaving: false,
        };
      });
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  discardFileChange: async (logicalKey) => {
    const { project } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await discardLatexFileChange(project.id, {
        logical_key: logicalKey,
      });
      const [nextProject, treeResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
      ]);
      set((state) => ({
        project: nextProject,
        tree: treeResponse.items,
        fileChanges: state.fileChanges.filter(
          (item) => item.logical_key !== logicalKey,
        ),
        isSaving: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  revertFileChange: async (logicalKey, revertSignature) => {
    const { project, activeFilePath, activeFileKind } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      const reverted = await revertLatexFileChange(project.id, {
        logical_key: logicalKey,
        revert_signature: revertSignature,
      });
      const shouldRefreshActiveFile =
        activeFileKind === "text" && activeFilePath === reverted.path;
      const [nextProject, treeResponse, activeFileResponse] = await Promise.all([
        getLatexProject(project.id),
        getLatexProjectTree(project.id),
        shouldRefreshActiveFile
          ? readLatexFile(project.id, reverted.path)
          : Promise.resolve(null),
      ]);
      set((state) => ({
        project: nextProject,
        tree: treeResponse.items,
        appliedFileChanges: state.appliedFileChanges.filter(
          (item) => item.logical_key !== logicalKey,
        ),
        isSaving: false,
        ...(activeFileResponse
          ? {
              activeFileContent: activeFileResponse.content,
              activeFileSavedContent: activeFileResponse.content,
            }
          : {}),
      }));
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
    }
  },

  deleteProject: async () => {
    const { project } = get();
    if (!project) {
      return;
    }
    set({ isSaving: true, error: null });
    try {
      await deleteLatexProject(project.id);
      get().clearCompiledPdf();
      get().clearActiveBlob();
      set((state) => ({
        projects: state.projects.filter((item) => item.id !== project.id),
        project: null,
        tree: [],
        activeFilePath: null,
        activeFileKind: null,
        activeFileContent: "",
        activeFileSavedContent: "",
        fileChanges: [],
        appliedFileChanges: [],
        compileResult: null,
        compileLog: "",
        isSaving: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isSaving: false });
      throw error;
    }
  },

  compileProject: async (engine: LatexCompileEngine = "xelatex") => {
    const {
      project,
      activeFilePath,
      activeFileKind,
      activeFileContent,
      activeFileSavedContent,
    } = get();
    if (!project) {
      return;
    }
    if (
      activeFileKind === "text"
      && activeFilePath
      && activeFileContent !== activeFileSavedContent
    ) {
      set({ isSaving: true, error: null });
      try {
        await writeLatexFile(project.id, activeFilePath, activeFileContent);
        set({
          activeFileSavedContent: activeFileContent,
          isSaving: false,
        });
      } catch (error) {
        set({ error: (error as Error).message, isSaving: false });
        return;
      }
    }
    set({ isCompiling: true, error: null });
    get().clearCompiledPdf();
    try {
      const result = await compileLatexProject(project.id, {
        main_file: project.main_file,
        engine,
      });
      const normalizedResult = normalizeCompileResult(result);
      set({
        compileResult: normalizedResult,
        compileLog: normalizedResult.log || "",
      });

      let compiledPdfUrl: string | null = null;
      if (normalizedResult.ok && normalizedResult.history_id) {
        try {
          const blob = await fetchLatexCompiledPdfBlob(project.id, normalizedResult.history_id);
          compiledPdfUrl = URL.createObjectURL(blob);
        } catch (error) {
          set({
            error: `PDF 已编译成功，但预览文件加载失败：${(error as Error).message}`,
            isCompiling: false,
          });
          return;
        }
      } else if (normalizedResult.ok && !normalizedResult.history_id) {
        set({
          error: "PDF 已编译成功，但没有生成可读取的编译历史记录。",
          isCompiling: false,
        });
        return;
      }
      set({
        compiledPdfUrl,
        isCompiling: false,
      });
    } catch (error) {
      set({ error: (error as Error).message, isCompiling: false });
    }
  },

  clearCompiledPdf: () => {
    const current = get().compiledPdfUrl;
    if (current) {
      URL.revokeObjectURL(current);
    }
    set({ compiledPdfUrl: null });
  },

  clearActiveBlob: () => {
    const current = get().activeBlobUrl;
    if (current) {
      URL.revokeObjectURL(current);
    }
    set({ activeBlobUrl: null });
  },

  clearError: () => set({ error: null }),
}));
