"use client";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
}

export function LiveWorkflowPanel({
  workspaceId,
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  return (
    <div
      data-testid={testId}
      className={className}
      style={{
        background: "var(--v2-bg-gradient)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Light orbs */}
      <div
        style={{
          position: "absolute",
          top: "10%",
          left: "15%",
          width: 300,
          height: 300,
          background: "var(--v2-orb-purple)",
          borderRadius: "50%",
          filter: "blur(50px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "15%",
          right: "20%",
          width: 250,
          height: 250,
          background: "var(--v2-orb-blue)",
          borderRadius: "50%",
          filter: "blur(45px)",
        }}
      />
      <div
        className="flex items-center justify-center h-full text-sm relative z-10"
        style={{ color: "var(--v2-text-tertiary)" }}
      >
        Workflow
      </div>
    </div>
  );
}
