"use client";

import type { CSSProperties } from "react";
import { Bot, LockKeyhole, MessageSquareWarning } from "lucide-react";

import type { WriteMode } from "@/lib/change-set-view";

export const WRITE_MODE_LABELS: Record<WriteMode, string> = {
  auto_draft: "自动写入草稿",
  ask_workspace_write: "写入前询问",
  strict_review: "严格审阅",
};

export const WRITE_MODE_DESCRIPTIONS: Record<WriteMode, string> = {
  auto_draft:
    "Sandbox 和低风险草稿可自动进入草稿区；证据、引用、论断和长期记忆仍需确认。",
  ask_workspace_write:
    "Sandbox 可直接运行；写入 Documents、Library、Memory、Tasks 等工作区房间前会先询问。",
  strict_review:
    "所有工作区写入都先进入复核与保存，由你逐项确认后再保存。",
};

const WRITE_MODE_OPTIONS: Array<{
  value: WriteMode;
  Icon: typeof Bot;
}> = [
  { value: "auto_draft", Icon: Bot },
  { value: "ask_workspace_write", Icon: MessageSquareWarning },
  { value: "strict_review", Icon: LockKeyhole },
];

export function writeModeLabel(mode: string | null | undefined): string {
  return isWriteMode(mode) ? WRITE_MODE_LABELS[mode] : WRITE_MODE_LABELS.auto_draft;
}

export function writeModeDescription(mode: string | null | undefined): string {
  return isWriteMode(mode)
    ? WRITE_MODE_DESCRIPTIONS[mode]
    : WRITE_MODE_DESCRIPTIONS.auto_draft;
}

export function isWriteMode(value: unknown): value is WriteMode {
  return (
    value === "auto_draft" ||
    value === "ask_workspace_write" ||
    value === "strict_review"
  );
}

export function normalizeWriteMode(value: unknown): WriteMode {
  return isWriteMode(value) ? value : "auto_draft";
}

export function WriteModeSelector({
  value,
  onChange,
  disabled = false,
}: {
  value: WriteMode;
  onChange: (value: WriteMode) => void;
  disabled?: boolean;
}) {
  return (
    <div style={selectorStyles.group} role="radiogroup" aria-label="写入模式">
      {WRITE_MODE_OPTIONS.map(({ value: option, Icon }) => {
        const selected = value === option;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(option)}
            data-testid={`write-mode-${option}`}
            style={{
              ...selectorStyles.option,
              ...(selected ? selectorStyles.optionSelected : null),
              ...(disabled ? selectorStyles.optionDisabled : null),
            }}
          >
            <span style={selectorStyles.optionTopline}>
              <Icon size={15} />
              <span style={selectorStyles.optionLabel}>{WRITE_MODE_LABELS[option]}</span>
            </span>
            <span style={selectorStyles.optionDescription}>
              {WRITE_MODE_DESCRIPTIONS[option]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

const selectorStyles: Record<string, CSSProperties> = {
  group: {
    display: "grid",
    gap: 8,
  },
  option: {
    display: "grid",
    gap: 5,
    width: "100%",
    minWidth: 0,
    padding: "10px 11px",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface)",
    color: "var(--wjn-text-secondary)",
    textAlign: "left",
    cursor: "pointer",
    fontFamily: "var(--wjn-font-sans)",
  },
  optionSelected: {
    border: "1px solid var(--wjn-accent-line)",
    background: "var(--wjn-accent-soft)",
    color: "var(--wjn-accent-strong)",
  },
  optionDisabled: {
    cursor: "not-allowed",
    opacity: 0.72,
  },
  optionTopline: {
    display: "inline-flex",
    alignItems: "center",
    gap: 7,
    minWidth: 0,
  },
  optionLabel: {
    fontSize: 13,
    fontWeight: 780,
    color: "var(--wjn-text)",
  },
  optionDescription: {
    color: "var(--wjn-text-muted)",
    fontSize: 12,
    lineHeight: 1.45,
  },
};
