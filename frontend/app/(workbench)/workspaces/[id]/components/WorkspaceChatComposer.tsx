"use client";

import type {
  FormEvent,
  KeyboardEvent,
  RefObject,
} from "react";
import { motion } from "framer-motion";
import { Send } from "lucide-react";
import type { Model, ReasoningEffort, Workspace } from "@/lib/api";
import { AgentStatusBar, QuickActions } from "@/components/workspace";
import { SkillSelector } from "./SkillSelector";
import { cn } from "@/lib/utils";

export const WORKSPACE_CHAT_REASONING_EFFORT_OPTIONS: Array<{
  value: ReasoningEffort;
  label: string;
  description: string;
}> = [
  { value: "minimal", label: "Minimal", description: "默认快速响应" },
  { value: "low", label: "Low", description: "轻量推理" },
  { value: "medium", label: "Medium", description: "平衡质量与延迟" },
  { value: "high", label: "High", description: "更强推理，响应更慢" },
];

export function isReasoningEffort(value: string | null): value is ReasoningEffort {
  return WORKSPACE_CHAT_REASONING_EFFORT_OPTIONS.some(
    (option) => option.value === value
  );
}

interface WorkspaceChatComposerProps {
  actionError: string | null;
  isExecuting: boolean;
  recommendedFeatureIds: string[];
  onQuickAction: (featureId: string) => void;
  workspaceType?: Workspace["type"] | null;
  currentSkill: string | null;
  onSelectSkill: (skill: string | null) => void;
  availableModels: Model[];
  selectedModel: string | null;
  onSelectModel: (modelId: string | null) => void;
  isStreaming: boolean;
  supportsReasoningEffort: boolean;
  selectedReasoningEffort: ReasoningEffort | null;
  onSelectReasoningEffort: (value: ReasoningEffort) => void;
  inputValue: string;
  onInputChange: (value: string) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: FormEvent) => void;
}

export function WorkspaceChatComposer({
  actionError,
  isExecuting,
  recommendedFeatureIds,
  onQuickAction,
  workspaceType,
  currentSkill,
  onSelectSkill,
  availableModels,
  selectedModel,
  onSelectModel,
  isStreaming,
  supportsReasoningEffort,
  selectedReasoningEffort,
  onSelectReasoningEffort,
  inputValue,
  onInputChange,
  inputRef,
  onKeyDown,
  onSubmit,
}: WorkspaceChatComposerProps) {
  return (
    <div className="p-4 border-t border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
      <div className="mb-3">
        <AgentStatusBar />
      </div>

      {actionError && (
        <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
          {actionError}
        </div>
      )}

      {!isExecuting && (
        <div className="mb-3 overflow-x-auto pb-2">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
            推荐动作
          </p>
          <QuickActions
            onAction={onQuickAction}
            featureIds={recommendedFeatureIds}
            maxItems={5}
          />
        </div>
      )}

      <div className="mb-3 overflow-x-auto pb-2">
        <SkillSelector
          workspaceType={workspaceType}
          selectedSkill={currentSkill}
          onSelect={onSelectSkill}
        />
      </div>

      <div className="mb-3 flex items-center gap-3">
        <label
          htmlFor="chat-model-select"
          className="text-xs font-medium text-[var(--text-muted)]"
        >
          Chat Model
        </label>
        <select
          id="chat-model-select"
          value={selectedModel ?? ""}
          onChange={(event) => onSelectModel(event.target.value || null)}
          disabled={availableModels.length === 0 || isStreaming}
          className="min-w-[220px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
        >
          {availableModels.length === 0 ? (
            <option value="">No models available</option>
          ) : (
            availableModels.map((model) => (
              <option key={model.name} value={model.name}>
                {model.display_name}
              </option>
            ))
          )}
        </select>
        {supportsReasoningEffort && (
          <>
            <label
              htmlFor="chat-reasoning-select"
              className="text-xs font-medium text-[var(--text-muted)]"
            >
              Reasoning
            </label>
            <select
              id="chat-reasoning-select"
              value={selectedReasoningEffort ?? "minimal"}
              onChange={(event) =>
                onSelectReasoningEffort(
                  isReasoningEffort(event.target.value)
                    ? event.target.value
                    : "minimal"
                )
              }
              disabled={isStreaming}
              className="min-w-[180px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
            >
              {WORKSPACE_CHAT_REASONING_EFFORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} · {option.description}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      <form onSubmit={onSubmit} className="flex gap-3">
        <div className="flex-1 relative">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about your research..."
            disabled={isStreaming}
            rows={1}
            className={cn(
              "w-full px-4 py-3 rounded-xl resize-none",
              "bg-[var(--bg-muted)]/70 backdrop-blur-sm",
              "border border-[var(--border-default)] focus:border-[var(--border-focus)]",
              "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
              "focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20",
              "transition-all duration-200"
            )}
          />
        </div>
        <motion.button
          type="submit"
          disabled={!inputValue.trim() || isStreaming}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className={cn(
            "px-4 py-3 rounded-xl flex items-center justify-center",
            "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white",
            "hover:shadow-lg transition-shadow",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          <Send className="w-5 h-5" />
        </motion.button>
      </form>
    </div>
  );
}
