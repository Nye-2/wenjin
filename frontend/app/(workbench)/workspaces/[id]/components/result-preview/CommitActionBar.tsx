"use client";

interface CommitActionBarProps {
  committed: boolean;
  committing: boolean;
  onAcceptAll: () => void;
  onAcceptSelected: () => void;
  onDiscard: () => void;
  acceptAllLabel?: string;
  acceptSelectedLabel?: string;
  discardLabel?: string;
  committedLabel?: string;
  acceptAllDisabled?: boolean;
  acceptAllTitle?: string;
}

export function CommitActionBar({
  committed,
  committing,
  onAcceptAll,
  onAcceptSelected,
  onDiscard,
  acceptAllLabel = "保存全部",
  acceptSelectedLabel = "保存勾选项",
  discardLabel = "暂不保存",
  committedLabel = "已保存到工作区",
  acceptAllDisabled = false,
  acceptAllTitle,
}: CommitActionBarProps) {
  if (committed) {
    return (
      <div
        style={{
          fontSize: 12.5,
          fontWeight: 600,
          color: "var(--v2-status-success-deep)",
        }}
      >
        {committedLabel}
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
      }}
    >
      <button
        type="button"
        onClick={onAcceptAll}
        disabled={committing || acceptAllDisabled}
        title={acceptAllTitle}
        style={{
          ...primaryButton,
          ...(committing || acceptAllDisabled ? disabledButton : null),
        }}
      >
        {acceptAllLabel}
      </button>
      <button
        type="button"
        onClick={onAcceptSelected}
        disabled={committing}
        style={secondaryButton}
      >
        {acceptSelectedLabel}
      </button>
      <button
        type="button"
        onClick={onDiscard}
        disabled={committing}
        style={ghostButton}
      >
        {discardLabel}
      </button>
    </div>
  );
}

const primaryButton: React.CSSProperties = {
  border: "1px solid var(--v2-accent-purple-700)",
  background: "var(--v2-accent-purple-700)",
  color: "#FFFFFF",
  borderRadius: "var(--v2-radius-pill)",
  padding: "8px 14px",
  fontSize: 12.5,
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryButton: React.CSSProperties = {
  border: "1px solid rgba(124, 58, 237, 0.18)",
  background: "rgba(124, 58, 237, 0.08)",
  color: "var(--v2-accent-purple-700)",
  borderRadius: "var(--v2-radius-pill)",
  padding: "8px 14px",
  fontSize: 12.5,
  fontWeight: 600,
  cursor: "pointer",
};

const ghostButton: React.CSSProperties = {
  border: "1px solid rgba(20, 20, 30, 0.08)",
  background: "rgba(255, 255, 255, 0.72)",
  color: "var(--v2-text-secondary)",
  borderRadius: "var(--v2-radius-pill)",
  padding: "8px 14px",
  fontSize: 12.5,
  fontWeight: 500,
  cursor: "pointer",
};

const disabledButton: React.CSSProperties = {
  opacity: 0.48,
  cursor: "not-allowed",
};
