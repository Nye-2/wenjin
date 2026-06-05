export type PrismAssistRoute = "quick" | "deep";

export function choosePrismAssistRoute(input: {
  selectedTextLength: number;
  comment: string;
  scope: "selection" | "section";
  force?: PrismAssistRoute;
}): PrismAssistRoute {
  if (input.force) {
    return input.force;
  }
  if (input.selectedTextLength > 2500) {
    return "deep";
  }
  if (input.scope === "section" && input.selectedTextLength > 1200) {
    return "deep";
  }
  if (/整体|全文|多节|文献|审稿|投稿|贡献|实验|证据|结构/.test(input.comment)) {
    return "deep";
  }
  return "quick";
}
