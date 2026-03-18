import { useCallback, useEffect, useState } from "react";

import { listModels, type Model, type ModelPurpose } from "@/lib/api";

interface UseModelSelectionOptions {
  purpose?: ModelPurpose;
  enabled?: boolean;
  persistenceKey?: string;
}

interface UseModelSelectionReturn {
  models: Model[];
  selectedModel: string | null;
  setSelectedModel: (modelId: string | null) => void;
  isLoading: boolean;
  loadError: string | null;
}

export function useModelSelection({
  purpose = "chat",
  enabled = true,
  persistenceKey,
}: UseModelSelectionOptions = {}): UseModelSelectionReturn {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const readPersistedSelection = useCallback((): string | null => {
    if (!persistenceKey || typeof window === "undefined") {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(persistenceKey);
      const normalized = raw?.trim();
      return normalized || null;
    } catch {
      return null;
    }
  }, [persistenceKey]);

  useEffect(() => {
    let cancelled = false;

    const loadModels = async () => {
      if (!enabled) {
        if (cancelled) {
          return;
        }
        setModels([]);
        setSelectedModel(null);
        setIsLoading(false);
        setLoadError(null);
        return;
      }

      setIsLoading(true);
      setLoadError(null);
      try {
        const response = await listModels(purpose);
        if (cancelled) {
          return;
        }

        const nextModels = Array.isArray(response.models) ? response.models : [];
        setModels(nextModels);
        setSelectedModel((prev) => {
          const persisted = readPersistedSelection();
          if (persisted && nextModels.some((model) => model.name === persisted)) {
            return persisted;
          }
          if (prev && nextModels.some((model) => model.name === prev)) {
            return prev;
          }
          const defaultModel = nextModels.find((model) => model.is_default);
          return defaultModel?.name ?? nextModels[0]?.name ?? null;
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setModels([]);
        setSelectedModel(null);
        setLoadError(error instanceof Error ? error.message : "模型列表加载失败");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadModels();
    return () => {
      cancelled = true;
    };
  }, [enabled, purpose, readPersistedSelection]);

  useEffect(() => {
    if (!persistenceKey || typeof window === "undefined") {
      return;
    }
    try {
      if (selectedModel) {
        window.localStorage.setItem(persistenceKey, selectedModel);
      } else {
        window.localStorage.removeItem(persistenceKey);
      }
    } catch {
      // Ignore persistence errors (e.g. private mode/localStorage unavailable).
    }
  }, [persistenceKey, selectedModel]);

  return {
    models,
    selectedModel,
    setSelectedModel,
    isLoading,
    loadError,
  };
}
