"use client";

import { useState, useMemo, useId } from "react";

// ── Types ───────────────────────────────────────────────────────────────────

type ResultOutput =
  | {
      id: string;
      kind: "library_item";
      preview: string;
      default_checked: boolean;
      data: {
        title: string;
        authors: string[];
        year?: number;
        doi?: string;
        url?: string;
        abstract?: string;
        metadata?: Record<string, unknown>;
      };
    }
  | {
      id: string;
      kind: "document";
      preview: string;
      default_checked: boolean;
      data: {
        name: string;
        mime_type: string;
        storage_path: string;
        size_bytes: number;
        parent_id?: string;
        doc_kind: "draft" | "outline" | "figure" | "export";
      };
    }
  | {
      id: string;
      kind: "memory_fact";
      preview: string;
      default_checked: boolean;
      data: { content: string; category: string; confidence: number };
    }
  | {
      id: string;
      kind: "decision";
      preview: string;
      default_checked: boolean;
      data: { key: string; value: string; confidence: number };
    }
  | {
      id: string;
      kind: "task";
      preview: string;
      default_checked: boolean;
      data: { title: string; description?: string; priority?: number };
    };

interface ResultCardFullData {
  execution_id: string;
  capability_id?: string;
  capability_name?: string;
  status: "completed" | "failed_partial" | "cancelled";
  duration_seconds?: number;
  narrative?: string;
  outputs: ResultOutput[];
  errors?: Array<{ message: string; phase?: string }>;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const KIND_LABELS: Record<ResultOutput["kind"], string> = {
  library_item: "Library Items",
  document: "Documents",
  memory_fact: "Memory Facts",
  decision: "Decisions",
  task: "Tasks",
};

function groupByKind(outputs: ResultOutput[]): Map<string, ResultOutput[]> {
  const map = new Map<string, ResultOutput[]>();
  for (const output of outputs) {
    const group = map.get(output.kind) ?? [];
    group.push(output);
    map.set(output.kind, group);
  }
  return map;
}

function generateUUID(): string {
  // crypto.randomUUID is available in modern browsers and jsdom 20+
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ── Component ───────────────────────────────────────────────────────────────

interface ResultCardProps {
  data: ResultCardFullData;
}

export function ResultCard({ data }: ResultCardProps) {
  const {
    execution_id,
    capability_name,
    status,
    duration_seconds,
    narrative,
    outputs,
  } = data;

  // Idempotency key: generated once per mount
  const [idempotencyKey] = useState(() => generateUUID());

  // Checkbox state: initialize from default_checked
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    for (const output of outputs) {
      if (output.default_checked) {
        ids.add(output.id);
      }
    }
    return ids;
  });

  // Commit state
  const [committed, setCommitted] = useState(false);
  const [committing, setCommitting] = useState(false);

  // Group outputs by kind (memoized)
  const grouped = useMemo(() => groupByKind(outputs), [outputs]);

  // Toggle a single checkbox
  function toggle(id: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // Commit handler
  async function commit(body: object) {
    if (committed || committing) return;
    setCommitting(true);
    try {
      await fetch(`/api/executions/${execution_id}/commit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify(body),
      });
      setCommitted(true);
    } finally {
      setCommitting(false);
    }
  }

  const statusLabel =
    status === "completed" ? "完成" : status === "failed_partial" ? "部分完成" : "已取消";

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.statusIcon}>
          {status === "completed" ? "✓" : status === "failed_partial" ? "!" : "×"}
        </span>
        <span style={styles.headerTitle}>
          {capability_name ?? "Execution"} {statusLabel}
        </span>
        {duration_seconds != null && (
          <span style={styles.duration}>{duration_seconds}s</span>
        )}
      </div>

      {/* Narrative */}
      {narrative && <div style={styles.narrative}>{narrative}</div>}

      {/* Grouped outputs */}
      {Array.from(grouped.entries()).map(([kind, items]) => (
        <div key={kind} style={styles.group}>
          <div style={styles.groupHeader}>
            {KIND_LABELS[kind as ResultOutput["kind"]] ?? kind} ({items.length})
          </div>
          {items.map((output) => (
            <label key={output.id} style={styles.outputRow}>
              <input
                type="checkbox"
                checked={checkedIds.has(output.id)}
                onChange={() => toggle(output.id)}
                disabled={committed}
                style={styles.checkbox}
              />
              <span style={styles.previewText}>{output.preview}</span>
            </label>
          ))}
        </div>
      ))}

      {/* Actions */}
      <div style={styles.actions}>
        {committed ? (
          <span style={styles.confirmed}>已保存</span>
        ) : (
          <>
            <button
              style={styles.btnAcceptAll}
              onClick={() => commit({ accept_all: true })}
              disabled={committing}
            >
              全部接受
            </button>
            <button
              style={styles.btnAcceptSelected}
              onClick={() => commit({ accepted_ids: Array.from(checkedIds) })}
              disabled={committing}
            >
              仅勾选项
            </button>
            <button
              style={styles.btnDiscard}
              onClick={() => commit({ accepted_ids: [] })}
              disabled={committing}
            >
              全弃
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: "var(--v2-space-5)",
    background: "var(--v2-glass-bg)",
    backdropFilter: "var(--v2-glass-blur)",
    WebkitBackdropFilter: "var(--v2-glass-blur)",
    borderRadius: "var(--v2-radius-lg)",
    border: "1px solid var(--v2-glass-border)",
    boxShadow: "var(--v2-glass-shadow)",
    margin: "var(--v2-space-2) 0",
    fontFamily: "var(--v2-font-sans)",
    fontSize: 13,
    color: "var(--v2-text-primary)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
    fontWeight: 500,
  },
  statusIcon: {
    color: "var(--v2-status-success-deep)",
    fontSize: 14,
  },
  headerTitle: {
    fontVariantNumeric: "tabular-nums",
  },
  duration: {
    marginLeft: "auto",
    fontSize: 12,
    color: "var(--v2-text-tertiary)",
    fontVariantNumeric: "tabular-nums",
  },
  narrative: {
    color: "var(--v2-text-secondary)",
    fontSize: 12.5,
    marginBottom: "var(--v2-space-3)",
    lineHeight: 1.5,
  },
  group: {
    marginTop: "var(--v2-space-3)",
  },
  groupHeader: {
    fontSize: 12,
    textTransform: "uppercase",
    color: "var(--v2-text-tertiary)",
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  outputRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "5px 6px",
    borderRadius: "var(--v2-radius-sm)",
    cursor: "pointer",
    transition: "background var(--v2-duration-fast) var(--v2-ease-standard)",
  },
  checkbox: {
    accentColor: "var(--v2-accent-purple-700)",
    cursor: "pointer",
    margin: 0,
  },
  previewText: {
    fontSize: 13,
    color: "var(--v2-text-primary)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: "var(--v2-space-2)",
    marginTop: "var(--v2-space-4)",
    paddingTop: "var(--v2-space-3)",
    borderTop: "1px solid var(--v2-border-soft)",
  },
  confirmed: {
    fontSize: 13,
    color: "var(--v2-status-success-deep)",
    fontWeight: 500,
  },
  btnAcceptAll: {
    padding: "6px 14px",
    borderRadius: "var(--v2-radius-sm)",
    border: "none",
    background: "var(--v2-accent-purple-700)",
    color: "#FFFFFF",
    fontSize: 12.5,
    fontWeight: 500,
    cursor: "pointer",
    fontFamily: "var(--v2-font-sans)",
  },
  btnAcceptSelected: {
    padding: "6px 14px",
    borderRadius: "var(--v2-radius-sm)",
    border: "1px solid var(--v2-accent-purple-700)",
    background: "transparent",
    color: "var(--v2-accent-purple-700)",
    fontSize: 12.5,
    fontWeight: 500,
    cursor: "pointer",
    fontFamily: "var(--v2-font-sans)",
  },
  btnDiscard: {
    padding: "6px 14px",
    borderRadius: "var(--v2-radius-sm)",
    border: "none",
    background: "transparent",
    color: "var(--v2-text-tertiary)",
    fontSize: 12.5,
    fontWeight: 500,
    cursor: "pointer",
    fontFamily: "var(--v2-font-sans)",
  },
};
