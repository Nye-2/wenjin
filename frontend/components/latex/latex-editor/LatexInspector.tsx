"use client";

import type { ComponentProps } from "react";

import { PrismAssistPanel } from "./PrismAssistPanel";
import { PrismFloatingAssist } from "./PrismFloatingAssist";

export { LatexRewritePreviewPanel } from "./LatexRewritePreviewPanel";

type PrismAssistPanelProps = ComponentProps<typeof PrismAssistPanel>;

interface LatexInspectorProps extends PrismAssistPanelProps {
  selectedCharacterCount: number;
  pendingRewriteCount: number;
  hasError: boolean;
  onOpenPanel: () => void;
  onAnnotateSelection: () => void;
  onOpenQuickRewrite: () => void;
  onOpenDeepAssist: () => void;
}

export function LatexInspector({
  selectedCharacterCount,
  pendingRewriteCount,
  hasError,
  onOpenPanel,
  onAnnotateSelection,
  onOpenQuickRewrite,
  onOpenDeepAssist,
  ...panelProps
}: LatexInspectorProps) {
  return (
    <>
      <PrismFloatingAssist
        isPanelOpen={panelProps.open}
        selectedCharacterCount={selectedCharacterCount}
        pendingRewriteCount={pendingRewriteCount}
        runningJobCount={panelProps.runningJobCount}
        hasError={hasError}
        onOpen={onOpenPanel}
        onAnnotate={onAnnotateSelection}
        onQuickRewrite={onOpenQuickRewrite}
        onDeepAssist={onOpenDeepAssist}
      />

      <PrismAssistPanel {...panelProps} />
    </>
  );
}
