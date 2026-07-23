"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  PackagePlus,
  Stamp,
  XCircle,
} from "lucide-react";

import type { MissionCardBlock } from "@/lib/api/blocks";
import {
  commitMissionReviews,
  decideMissionReviews,
  getMissionView,
} from "@/lib/api/missions";

const cardShell: React.CSSProperties = {
  margin: "8px 0",
  maxWidth: "92%",
  borderRadius: "var(--wjn-radius-lg)",
  border: "1px solid var(--wjn-line)",
  background: "var(--wjn-surface)",
  boxShadow: "var(--wjn-shadow-sm)",
  padding: "12px 14px",
  fontFamily: "var(--wjn-font-sans)",
};

const titleRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 13,
  fontWeight: 650,
  color: "var(--wjn-text)",
};

const detailText: React.CSSProperties = {
  marginTop: 6,
  fontSize: 12,
  lineHeight: 1.7,
  color: "var(--wjn-text-secondary)",
};

const actionRow: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  marginTop: 10,
};

function CardButton({
  label,
  tone = "normal",
  disabled,
  onClick,
}: {
  label: string;
  tone?: "primary" | "normal" | "warn";
  disabled?: boolean;
  onClick: () => void;
}) {
  const palette =
    tone === "primary"
      ? { background: "var(--wjn-blue)", color: "#f5f1e8", border: "var(--wjn-blue)" }
      : tone === "warn"
        ? { background: "var(--wjn-error-soft)", color: "var(--wjn-error)", border: "rgba(179,52,62,0.22)" }
        : { background: "var(--wjn-surface)", color: "var(--wjn-text-secondary)", border: "var(--wjn-line)" };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: "6px 14px",
        borderRadius: "var(--wjn-radius-pill)",
        border: `1px solid ${palette.border}`,
        background: palette.background,
        color: palette.color,
        fontSize: 12.5,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        fontFamily: "var(--wjn-font-sans)",
      }}
    >
      {label}
    </button>
  );
}

type ReviewOutcome = "accepted" | "rejected" | "needs_more_evidence";

function ReviewRequestCard({ block }: { block: MissionCardBlock }) {
  const itemIds = useMemo(() => block.review_item_ids ?? [], [block.review_item_ids]);
  const count = block.count ?? itemIds.length;
  const [outcome, setOutcome] = useState<ReviewOutcome | null>(null);
  const [acting, setActing] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  // 以权威投影校准卡片状态：刷新/重开后，已处理的候选不再展示操作按钮。
  useEffect(() => {
    let cancelled = false;
    if (!itemIds.length || outcome) return;
    void getMissionView(block.mission_id)
      .then((view) => {
        if (cancelled) return;
        const targets = view.reviewItems.filter((item) => itemIds.includes(item.id));
        if (!targets.length) return;
        const decided = targets.find((item) =>
          item.status === "accepted" || item.status === "committed" ||
          item.status === "rejected" || item.status === "needs_more_evidence",
        );
        const allHandled = targets.every(
          (item) => item.status !== "pending",
        );
        if (allHandled) {
          const status = decided?.status;
          setOutcome(
            status === "rejected"
              ? "rejected"
              : status === "needs_more_evidence"
                ? "needs_more_evidence"
                : "accepted",
          );
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [block.mission_id, itemIds, outcome]);

  const act = useCallback(
    async (decision: ReviewOutcome) => {
      if (!itemIds.length || acting) return;
      setActing(true);
      setErrorText(null);
      try {
        await decideMissionReviews({
          missionId: block.mission_id,
          decisions: itemIds.map((reviewItemId) => ({ reviewItemId, decision })),
        });
        if (decision === "accepted") {
          await commitMissionReviews({ missionId: block.mission_id, reviewItemIds: itemIds });
        }
        setOutcome(decision);
      } catch (error) {
        setErrorText(error instanceof Error ? error.message : "操作失败，请稍后重试");
      } finally {
        setActing(false);
      }
    },
    [acting, block.mission_id, itemIds],
  );

  const outcomeLabel =
    outcome === "accepted"
      ? "已确认并保存"
      : outcome === "rejected"
        ? "已驳回"
        : outcome === "needs_more_evidence"
          ? "已要求补证，任务将继续"
          : null;

  return (
    <div style={{ ...cardShell, borderColor: "rgba(181,133,47,0.30)", background: "var(--wjn-review-soft)" }} data-testid="mission-card-review-request">
      <div style={{ ...titleRow, color: "var(--wjn-review)" }}>
        <Stamp size={15} aria-hidden="true" />
        {outcomeLabel ?? `${count} 项产出待你确认`}
      </div>
      {block.summary ? <p style={detailText}>{block.summary}</p> : null}
      {!outcome && itemIds.length > 0 ? (
        <div style={actionRow}>
          <CardButton label={acting ? "处理中…" : "确认并保存"} tone="primary" disabled={acting} onClick={() => void act("accepted")} />
          <CardButton label="需要补证" disabled={acting} onClick={() => void act("needs_more_evidence")} />
          <CardButton label="驳回" tone="warn" disabled={acting} onClick={() => void act("rejected")} />
        </div>
      ) : null}
      {acting ? (
        <div style={{ ...detailText, display: "flex", alignItems: "center", gap: 6 }}>
          <LoaderCircle size={13} className="animate-spin" aria-hidden="true" />
          正在提交你的决定…
        </div>
      ) : null}
      {errorText ? <p style={{ ...detailText, color: "var(--wjn-error)" }}>{errorText}</p> : null}
    </div>
  );
}

export function MissionCard({
  block,
  onMaterialAction,
}: {
  block: MissionCardBlock;
  onMaterialAction?: () => void;
}) {
  if (block.card === "stage_passed") {
    return (
      <div style={cardShell} data-testid="mission-card-stage-passed">
        <div style={{ ...titleRow, color: "var(--wjn-accent-strong)" }}>
          <CheckCircle2 size={15} aria-hidden="true" />
          {block.stage_title ? `「${block.stage_title}」已通过验收` : "阶段已通过验收"}
        </div>
        {typeof block.evidence_count === "number" && block.evidence_count > 0 ? (
          <p style={detailText}>已查证 {block.evidence_count} 份材料。</p>
        ) : null}
      </div>
    );
  }

  if (block.card === "review_request") {
    return <ReviewRequestCard block={block} />;
  }

  if (block.card === "material_request") {
    return (
      <div style={{ ...cardShell, borderColor: "rgba(181,133,47,0.30)" }} data-testid="mission-card-material-request">
        <div style={{ ...titleRow, color: "var(--wjn-review)" }}>
          <PackagePlus size={15} aria-hidden="true" />
          {block.title ?? "需要你补充材料"}
        </div>
        {block.summary ? <p style={detailText}>{block.summary}</p> : null}
        <div style={actionRow}>
          <CardButton label="去补充材料" tone="primary" onClick={() => onMaterialAction?.()} />
        </div>
      </div>
    );
  }

  if (block.card === "terminal") {
    const failed = block.status === "failed";
    const cancelled = block.status === "cancelled";
    return (
      <div style={cardShell} data-testid="mission-card-terminal">
        <div
          style={{
            ...titleRow,
            color: failed ? "var(--wjn-error)" : cancelled ? "var(--wjn-text-secondary)" : "var(--wjn-accent-strong)",
          }}
        >
          {failed ? (
            <XCircle size={15} aria-hidden="true" />
          ) : cancelled ? (
            <CircleAlert size={15} aria-hidden="true" />
          ) : (
            <CheckCircle2 size={15} aria-hidden="true" />
          )}
          {failed
            ? "任务未能完成，点进展查看原因"
            : cancelled
              ? "任务已停止"
              : `研究已完成${(block.mission_title ?? block.title) ? `：${block.mission_title ?? block.title}` : ""}`}
        </div>
      </div>
    );
  }

  return null;
}
