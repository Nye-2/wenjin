"use client";

import { Check, CheckSquare, XCircle } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";

interface CommitActionBarProps {
  committed: boolean;
  committing: boolean;
  onAcceptAll: () => void;
  onAcceptSelected: () => void;
  onDiscard: () => void;
  allowAcceptAll?: boolean;
  selectedCount?: number;
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
  allowAcceptAll = true,
  selectedCount,
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

  const selectedActionDisabled = committing || selectedCount === 0;

  return (
    <ActionBar
      className="justify-start"
      primary={{
        label: allowAcceptAll ? acceptAllLabel : acceptSelectedLabel,
        onClick: allowAcceptAll ? onAcceptAll : onAcceptSelected,
        disabled: allowAcceptAll ? committing : selectedActionDisabled,
        icon: allowAcceptAll ? Check : CheckSquare,
      }}
      secondary={
        allowAcceptAll
          ? [
              {
                label: acceptSelectedLabel,
                onClick: onAcceptSelected,
                disabled: selectedActionDisabled,
                icon: CheckSquare,
              },
            ]
          : []
      }
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
