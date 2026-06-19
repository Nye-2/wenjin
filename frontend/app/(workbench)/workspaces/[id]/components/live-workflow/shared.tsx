import type { ReactNode } from "react";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  Info,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { RunViewStatus } from "@/lib/execution-run-view";
import { getWorkspaceResultKindMeta } from "@/lib/workspace-result-kind";

import { styles } from "./styles";
import { kindLabel, statusLabel, statusTone } from "./utils";

export function EmptyState({
  title,
  detail,
  compact = false,
}: {
  title: string;
  detail: string;
  compact?: boolean;
}) {
  return (
    <div style={{ ...styles.emptyState, padding: compact ? 16 : 28 }}>
      <BookOpen size={compact ? 18 : 24} color="var(--wjn-text-muted)" />
      <div style={styles.emptyTitle}>{title}</div>
      <div style={styles.emptyDetail}>{detail}</div>
    </div>
  );
}

export function StatusPill({ status }: { status: RunViewStatus | string }) {
  const tone = statusTone(status);
  return <span style={{ ...styles.statusPill, ...tone }}>{statusLabel(status)}</span>;
}

export function NodeStatusDot({ status }: { status: string }) {
  const tone = statusTone(status);
  const Icon =
    status === "completed" ? CheckCircle2 : status === "failed" ? XCircle : Activity;
  return (
    <span style={{ ...styles.nodeDot, color: tone.color }}>
      <Icon size={12} />
    </span>
  );
}

export function ResultKindBadge({ kind }: { kind: string }) {
  const meta = getWorkspaceResultKindMeta(kind);
  return (
    <span
      style={{
        ...styles.kindBadge,
        color: meta.accent,
        background: meta.tint,
        borderColor: meta.border,
      }}
    >
      {kindLabel(kind)}
    </span>
  );
}

export function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div style={styles.metricCard}>
      <Icon size={17} color="var(--wjn-blue)" />
      <div>
        <div style={styles.metricValue}>{value}</div>
        <div style={styles.metricLabel}>{label}</div>
        <div style={styles.metricDetail}>{detail}</div>
      </div>
    </div>
  );
}

export function GuidanceNote({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "warning";
}) {
  return (
    <div
      style={{
        ...styles.guidanceNote,
        ...(tone === "warning" ? styles.guidanceNoteWarning : null),
      }}
    >
      <Info size={13} />
      <span>{children}</span>
    </div>
  );
}

export function InspectorBlock({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <div style={styles.inspectorBlock}>
      <div style={styles.inspectorBlockTitle}>
        <Icon size={13} />
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}
