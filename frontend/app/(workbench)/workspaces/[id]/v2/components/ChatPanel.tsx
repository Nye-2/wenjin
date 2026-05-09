"use client";

interface ChatPanelProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
}

export function ChatPanel({
  workspaceId,
  className,
  "data-testid": testId,
}: ChatPanelProps) {
  return (
    <div
      data-testid={testId}
      className={className}
      style={{ background: "#FFFFFF" }}
    >
      <div
        className="flex items-center justify-center h-full text-sm"
        style={{ color: "var(--v2-text-tertiary)" }}
      >
        Chat
      </div>
    </div>
  );
}
