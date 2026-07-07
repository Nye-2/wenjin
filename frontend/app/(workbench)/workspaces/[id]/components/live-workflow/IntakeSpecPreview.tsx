import { CheckCircle2, FileText } from "lucide-react";

import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import type { IntakeSpecV1 } from "@/lib/intake-spec";

import { styles } from "./styles";

export function IntakeSpecPreview({
  spec,
  isSending,
  onApprove,
}: {
  spec: IntakeSpecV1 | null;
  isSending: boolean;
  onApprove: (spec: IntakeSpecV1) => void;
}) {
  if (!spec) {
    return (
      <div style={styles.viewStack}>
        <section style={styles.primarySection}>
          <div style={styles.emptyState}>
            <FileText size={24} color="var(--wjn-text-muted)" />
            <div style={styles.emptyTitle}>还没有澄清 Spec</div>
            <div style={styles.emptyDetail}>
              与左侧助手说明目标后，生成的 Spec 会在这里预览。
            </div>
          </div>
        </section>
      </div>
    );
  }

  const ready = spec.status === "ready" && spec.missing_fields.length === 0;
  const statusLabel = ready ? "可执行" : "待补充";
  const statusColor = ready ? "var(--wjn-accent-strong)" : "var(--wjn-review)";

  return (
    <div style={styles.viewStack}>
      <section style={styles.primarySection}>
        <div style={styles.sectionHeaderCompact}>
          <div style={{ minWidth: 0 }}>
            <div style={styles.sectionSubtitle}>澄清文档</div>
            <div
              style={{
                ...styles.sectionTitle,
                margin: 0,
                overflowWrap: "anywhere",
              }}
            >
              {spec.title}
            </div>
          </div>
          <span
            style={{
              ...styles.statusPill,
              color: statusColor,
              background: ready
                ? "var(--wjn-accent-soft)"
                : "rgba(198, 138, 26, 0.1)",
              border: ready
                ? "1px solid var(--wjn-accent-line)"
                : "1px solid rgba(198, 138, 26, 0.18)",
            }}
          >
            {statusLabel}
          </span>
        </div>

        {spec.missing_fields.length > 0 ? (
          <div style={styles.guidanceNoteWarning}>
            还缺少：{spec.missing_fields.join("、")}
          </div>
        ) : null}

        {spec.assumptions.length > 0 ? (
          <div style={{ ...styles.guidanceNote, marginTop: 10 }}>
            默认假设：{spec.assumptions.join("；")}
          </div>
        ) : null}

        <button
          type="button"
          aria-label="同意，开始执行"
          disabled={!ready || isSending}
          onClick={() => onApprove(spec)}
          style={{
            ...styles.iconTextButton,
            marginTop: 12,
            background: ready ? "var(--wjn-blue)" : "var(--wjn-surface)",
            border: ready ? "1px solid var(--wjn-blue)" : styles.iconTextButton.border,
            color: ready ? "#FFFFFF" : "var(--wjn-text-muted)",
            opacity: !ready || isSending ? 0.56 : 1,
            cursor: !ready || isSending ? "not-allowed" : "pointer",
          }}
        >
          <CheckCircle2 size={14} />
          <span>同意，开始执行</span>
        </button>
      </section>

      <section style={styles.section}>
        <MarkdownRenderer content={spec.markdown} className="prose-chat" />
      </section>
    </div>
  );
}
