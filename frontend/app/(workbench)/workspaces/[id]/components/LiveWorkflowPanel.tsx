"use client";

import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import type { WorkspaceFeature } from "@/lib/api/types";
import { ExecutionCardList } from "./ExecutionCardList";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceFeature[];
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
  features: WorkspaceFeature[];
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
