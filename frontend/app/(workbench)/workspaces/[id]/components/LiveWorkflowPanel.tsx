"use client";

import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import type { WorkspaceCapability } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { ExecutionCardList } from "./ExecutionCardList";
import { WorkspaceActionLink } from "./WorkspaceActionLink";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceCapability[];
  className?: string;
  "data-testid"?: string;
}

export function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
  features = [],
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  const focusedRunId = useRunUiStore((state) => state.focusedRunId);
  const activeRunId = useRunUiStore((state) => state.activeRunId);
  const focusedRecord = useExecutionStore((state) =>
    focusedRunId ? state.executions.get(focusedRunId) ?? null : null,
  );
  const runView = focusedRecord ? runViewFromExecution(focusedRecord) : null;
  const hasCurrentRun = Boolean(focusedRunId || activeRunId);

  return (
    <div
      className={className}
      data-testid={testId}
      style={{
        position: "relative",
        height: "100%",
        background:
          "linear-gradient(135deg, #E0EFFF 0%, #F0F4FF 50%, #E8E0FF 100%)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Decorative light orbs */}
      <div
        style={{
          position: "absolute",
          top: -80,
          left: -80,
          width: 300,
          height: 300,
          borderRadius: "50%",
          background: "rgba(139,92,246,0.4)",
          filter: "blur(50px)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: -60,
          right: -60,
          width: 250,
          height: 250,
          borderRadius: "50%",
          background: "rgba(56,189,248,0.35)",
          filter: "blur(45px)",
          pointerEvents: "none",
        }}
      />

      {/* Content area */}
      <div
        style={{
          position: "relative",
          flex: 1,
          overflow: "auto",
          padding: "20px 24px",
        }}
      >
        {hasCurrentRun ? (
          <div
            data-testid="workflow-current-run"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              marginBottom: 12,
              padding: "10px 12px",
              borderRadius: "var(--v2-radius-lg)",
              border: "1px solid var(--v2-glass-border)",
              background: "rgba(255, 255, 255, 0.7)",
              boxShadow: "var(--v2-glass-shadow)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  color: "var(--v2-text-tertiary)",
                  fontWeight: 600,
                  marginBottom: 2,
                }}
              >
                Current run
              </div>
              <div
                style={{
                  fontSize: 15,
                  color: "var(--v2-text-primary)",
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {runView?.title ?? "Lead Agent 执行中"}
              </div>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 650,
                  color: "var(--v2-accent-purple-700)",
                  background: "var(--v2-accent-purple-100)",
                  borderRadius: "var(--v2-radius-pill)",
                  padding: "2px 8px",
                }}
              >
                {runView?.status ?? "launching"}
              </span>
              {runView?.hasPrismChanges ? (
                <WorkspaceActionLink
                  href={`/workspaces/${workspaceId}/prism`}
                  style={{
                    color: "var(--v2-accent-blue-700)",
                    fontSize: 12,
                    fontWeight: 650,
                    textDecoration: "none",
                  }}
                >
                  Prism 待审
                </WorkspaceActionLink>
              ) : null}
              <WorkspaceActionLink
                href={`/workspaces/${workspaceId}?room=runs`}
                style={{
                  color: "var(--v2-accent-blue-700)",
                  fontSize: 12,
                  fontWeight: 650,
                  textDecoration: "none",
                }}
              >
                Runs
              </WorkspaceActionLink>
            </div>
          </div>
        ) : null}
        <ExecutionCardList workspaceId={workspaceId} />
        {typeConfig && <ProductIntro typeConfig={typeConfig} features={features} />}
      </div>
    </div>
  );
}

/* ── ProductIntro — idle / suggestion area ── */

function iconToEmoji(icon: string | undefined): string {
  const map: Record<string, string> = {
    search: "\u{1F50D}",
    microscope: "\u{1F52C}",
    pen: "✍️",
    "book-open": "\u{1F4DA}",
    list: "\u{1F4CB}",
    image: "\u{1F4CA}",
    "shield-check": "\u{1F440}",
    compass: "\u{1F9ED}",
    layout: "\u{1F5C2}️",
    edit: "✏️",
    code: "\u{1F4BB}",
    package: "\u{1F4E6}",
    file: "\u{1F4C4}",
  };
  if (!icon) return "✨";
  return map[icon] ?? "✨";
}

function ProductIntro({
  typeConfig,
  features,
}: {
  typeConfig: WorkspaceTypeConfig;
  features: WorkspaceCapability[];
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "24px 0 16px",
      }}
    >
      {/* Title */}
      <div
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: "var(--v2-text-primary)",
          marginBottom: 4,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        {typeConfig.title}
      </div>
      {typeConfig.panelSubtitle && (
        <div
          style={{
            fontSize: 12,
            color: "var(--v2-text-tertiary)",
            marginBottom: 20,
            fontFamily: "var(--v2-font-sans)",
          }}
        >
          {typeConfig.panelSubtitle}
        </div>
      )}

      {/* Feature cards — 2-column grid */}
      {features.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 10,
            width: "100%",
            maxWidth: 420,
          }}
        >
          {features.slice(0, 6).map((f) => (
            <div
              key={f.id}
              style={{
                padding: "14px 16px",
                borderRadius: "var(--v2-radius-lg)",
                background: "var(--v2-glass-bg-elevated)",
                backdropFilter: "blur(10px)",
                WebkitBackdropFilter: "blur(10px)",
                border: "1px solid var(--v2-glass-border)",
                boxShadow: "var(--v2-glass-shadow)",
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--v2-text-primary)",
                  marginBottom: 4,
                  fontFamily: "var(--v2-font-sans)",
                }}
              >
                {iconToEmoji(f.icon)} {f.name}
              </div>
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--v2-text-tertiary)",
                  lineHeight: 1.4,
                  fontFamily: "var(--v2-font-sans)",
                }}
              >
                {f.description}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
