"use client";

import { type Model } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ModelSelectorProps {
  id: string;
  label?: string;
  models: Model[];
  selectedModel: string | null;
  onChange: (modelId: string | null) => void;
  isLoading?: boolean;
  loadError?: string | null;
  disabled?: boolean;
  className?: string;
}

export function ModelSelector({
  id,
  label = "模型",
  models,
  selectedModel,
  onChange,
  isLoading = false,
  loadError = null,
  disabled = false,
  className,
}: ModelSelectorProps) {
  const selectDisabled = disabled || isLoading || models.length === 0;

  return (
    <div className={cn("space-y-1", className)}>
      <label className="block text-xs text-[var(--wjn-text-muted)]" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        value={selectedModel ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
        disabled={selectDisabled}
        className="w-full rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-3 py-2 text-sm text-[var(--wjn-text)] focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-60"
      >
        {isLoading ? (
          <option value="">模型加载中...</option>
        ) : models.length === 0 ? (
          <option value="">暂无可用模型</option>
        ) : (
          models.map((model) => (
            <option key={model.name} value={model.name}>
              {model.display_name}
            </option>
          ))
        )}
      </select>
      {loadError ? (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          模型列表加载失败，将使用后端默认模型。
        </p>
      ) : null}
    </div>
  );
}
