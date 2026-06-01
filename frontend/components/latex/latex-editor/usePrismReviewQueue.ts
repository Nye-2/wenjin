import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  LatexAppliedFileChange,
  LatexFileChange,
  LatexFileChangePreviewResponse,
  LatexProject,
} from "@/lib/api";
import { previewLatexFileChange } from "@/lib/api";
import {
  fileChangeToPrismReviewItem,
} from "@/components/prism/PrismReviewList";
import { readClientErrorMessage } from "./clientErrors";

interface SearchParamsLike {
  get(name: string): string | null;
}

interface UsePrismReviewQueueOptions {
  projectId: string;
  project: LatexProject | null;
  activeFilePath: string | null;
  fileChanges: LatexFileChange[];
  appliedFileChanges: LatexAppliedFileChange[];
  searchParams: SearchParamsLike;
  openFile: (path: string) => Promise<void>;
  applyFileChange: (logicalKey: string) => Promise<void>;
  discardFileChange: (logicalKey: string) => Promise<void>;
  revertFileChange: (logicalKey: string, revertSignature: string) => Promise<void>;
  onReviewStateChanged?: () => void;
}

export function usePrismReviewQueue({
  projectId,
  project,
  activeFilePath,
  fileChanges,
  appliedFileChanges,
  searchParams,
  openFile,
  applyFileChange,
  discardFileChange,
  revertFileChange,
  onReviewStateChanged,
}: UsePrismReviewQueueOptions) {
  const fileChangesRef = useRef<HTMLDivElement | null>(null);
  const lastFileChangeFocusKey = useRef("");
  const [fileChangePreviews, setFileChangePreviews] = useState<Record<string, LatexFileChangePreviewResponse>>({});
  const [busyFileChangeKey, setBusyFileChangeKey] = useState<string | null>(null);
  const [fileChangeError, setFileChangeError] = useState("");

  const pendingReviewItems = useMemo(
    () => fileChanges.map((change) => fileChangeToPrismReviewItem(change)),
    [fileChanges],
  );

  const appliedReviewItems = useMemo(
    () =>
      appliedFileChanges.map((change) =>
        fileChangeToPrismReviewItem({
          ...change,
          status: change.status || "applied",
          title: change.title || `已写入稿件修改: ${change.path}`,
          reason: change.reason || "可撤回的写入记录",
        }),
      ),
    [appliedFileChanges],
  );

  const previewProjectFileChange = useCallback(async (change: LatexFileChange) => {
    if (!project) {
      return;
    }
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      const preview = await previewLatexFileChange(project.id, {
        logical_key: change.logical_key,
      });
      setFileChangePreviews((prev) => ({
        ...prev,
        [change.logical_key]: preview,
      }));
    } catch (err) {
      setFileChangeError(`生成写入 diff 失败: ${readClientErrorMessage(err)}`);
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [project]);

  const focusedReviewItemId = searchParams.get("review_item_id")?.trim() || null;
  const focusedLogicalKey = searchParams.get("logical_key")?.trim() || null;

  useEffect(() => {
    if (
      !project ||
      searchParams.get("focus") !== "file_changes" ||
      fileChanges.length === 0
    ) {
      return;
    }

    const targetChange =
      fileChanges.find(
        (change) =>
          (focusedReviewItemId && change.id === focusedReviewItemId) ||
          (focusedLogicalKey && change.logical_key === focusedLogicalKey),
      ) ?? null;
    const focusKey = [
      projectId,
      project.id,
      focusedReviewItemId ?? "",
      focusedLogicalKey ?? "",
      targetChange?.logical_key ?? "all",
      fileChanges.length,
    ].join(":");
    if (lastFileChangeFocusKey.current === focusKey) {
      return;
    }
    lastFileChangeFocusKey.current = focusKey;

    fileChangesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (!targetChange) {
      return;
    }
    if (targetChange.path && activeFilePath !== targetChange.path) {
      void openFile(targetChange.path);
    }
    void previewProjectFileChange(targetChange);
  }, [
    activeFilePath,
    fileChanges,
    focusedLogicalKey,
    focusedReviewItemId,
    openFile,
    previewProjectFileChange,
    project,
    projectId,
    searchParams,
  ]);

  const clearPreview = useCallback((logicalKey: string) => {
    setFileChangePreviews((prev) => {
      const next = { ...prev };
      delete next[logicalKey];
      return next;
    });
  }, []);

  const applyPendingFileChange = useCallback(async (change: LatexFileChange) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await applyFileChange(change.logical_key);
      onReviewStateChanged?.();
      clearPreview(change.logical_key);
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [applyFileChange, clearPreview, onReviewStateChanged]);

  const discardPendingFileChange = useCallback(async (change: LatexFileChange) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await discardFileChange(change.logical_key);
      onReviewStateChanged?.();
      clearPreview(change.logical_key);
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [clearPreview, discardFileChange, onReviewStateChanged]);

  const revertAppliedFileChange = useCallback(async (change: {
    logical_key: string;
    revert_signature: string;
  }) => {
    setBusyFileChangeKey(change.logical_key);
    setFileChangeError("");
    try {
      await revertFileChange(change.logical_key, change.revert_signature);
      onReviewStateChanged?.();
      clearPreview(change.logical_key);
    } finally {
      setBusyFileChangeKey(null);
    }
  }, [clearPreview, onReviewStateChanged, revertFileChange]);

  const scrollToReviewQueue = useCallback(() => {
    fileChangesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return {
    fileChangesRef,
    fileChangePreviews,
    busyFileChangeKey,
    fileChangeError,
    focusedReviewItemId,
    focusedLogicalKey,
    pendingReviewItems,
    appliedReviewItems,
    previewProjectFileChange,
    applyPendingFileChange,
    discardPendingFileChange,
    revertAppliedFileChange,
    scrollToReviewQueue,
  };
}
