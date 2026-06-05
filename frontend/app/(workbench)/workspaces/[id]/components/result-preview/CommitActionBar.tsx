"use client";

import { Check, CheckSquare, XCircle } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";

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
}: CommitActionBarProps) {
  if (committed) {
    return (
      <div
        style={{
          fontSize: 12.5,
          fontWeight: 600,
          color: "var(--wjn-success)",
        }}
      >
        {committedLabel}
      </div>
    );
  }

  return (
    <ActionBar
      className="justify-start"
      primary={{
        label: acceptAllLabel,
        onClick: onAcceptAll,
        disabled: committing,
        icon: Check,
      }}
      secondary={[
        {
          label: acceptSelectedLabel,
          onClick: onAcceptSelected,
          disabled: committing,
          icon: CheckSquare,
        },
      ]}
      overflow={[
        {
          label: discardLabel,
          onClick: onDiscard,
          disabled: committing,
          icon: XCircle,
          tone: "danger",
        },
      ]}
    />
  );
}
