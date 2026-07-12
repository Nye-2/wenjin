export type ContinueThreadBlockAction = {
  action: "continue_thread";
  intent: string;
  source_block_kind: "question_card" | "result_card";
};

export function buildContinueThreadBlockAction(
  intent: string,
  sourceBlockKind: "question_card" | "result_card",
): ContinueThreadBlockAction {
  return {
    action: "continue_thread",
    intent,
    source_block_kind: sourceBlockKind,
  };
}
