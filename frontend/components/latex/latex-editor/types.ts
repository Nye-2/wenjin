import type { LatexFeedbackRewriteUndoPayload } from "@/lib/api";

export interface PdfDraftSelection {
  text: string;
  page: number;
  rects: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
}

export interface LastRewriteUndoState extends LatexFeedbackRewriteUndoPayload {
  file_path: string;
  feedback_id: string;
}

export type PrismSurfaceMode = "edit" | "compare" | "review" | "focus";
export type PrismInspectorTab = "assist" | "review" | "compile" | "agent";
