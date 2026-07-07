import { Sparkles, Users } from "lucide-react";

import { Button } from "@/components/ui/button";

export function PrismAnnotationComposer({
  contextText,
  draftComment,
  scope,
  canCreate,
  canUseDocumentAssist,
  canDeepAssist,
  hasSelectionContext,
  busy,
  onDraftChange,
  onScopeChange,
  onSaveComment,
  onQuickRewrite,
  onDeepAssist,
}: {
  contextText: string;
  draftComment: string;
  scope: "selection" | "section";
  canCreate: boolean;
  canUseDocumentAssist: boolean;
  canDeepAssist: boolean;
  hasSelectionContext: boolean;
  busy: boolean;
  onDraftChange: (comment: string) => void;
  onScopeChange: (scope: "selection" | "section") => void;
  onSaveComment: () => void;
  onQuickRewrite: () => void;
  onDeepAssist: () => void;
}) {
  return (
    <section className="rounded-lg border border-[var(--wjn-line)] bg-white p-3">
      <div>
        <p className="text-sm font-semibold text-[var(--wjn-text)]">改稿指令</p>
        <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
          {contextText}
        </p>
        {hasSelectionContext ? (
          <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
            已选中一段正文。你可以留下批注，也可以先让问津改这一处。
          </p>
        ) : null}
      </div>
      <textarea
        value={draftComment}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="例如：这段太像模板文风了，请整体改得更像研究者写作。"
        className="mt-3 min-h-[104px] w-full resize-none rounded-lg border border-[var(--wjn-line)] bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-[var(--wjn-accent-line)]"
      />
      {hasSelectionContext ? (
        <div className="mt-2 grid gap-1.5">
          <label className="text-xs text-[var(--wjn-text-muted)]">改稿范围</label>
          <select
            value={scope}
            onChange={(event) => onScopeChange(event.target.value as "selection" | "section")}
            className="h-9 rounded-lg border border-[var(--wjn-line)] bg-white px-2 text-sm"
          >
            <option value="selection">只改选中内容</option>
            <option value="section">改所在小节</option>
          </select>
        </div>
      ) : (
        <div className="mt-2 rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-2 text-xs leading-5 text-[var(--wjn-text-muted)]">
          修改会先进入审阅队列，不会直接覆盖正文。
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {hasSelectionContext ? (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={onSaveComment}
              disabled={!canCreate || busy}
            >
              添加批注
            </Button>
            <Button
              size="sm"
              onClick={onQuickRewrite}
              disabled={!canCreate || busy}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              改这段
            </Button>
          </>
        ) : null}
        <Button
          size="sm"
          variant="outline"
          onClick={onDeepAssist}
          disabled={busy || !canUseDocumentAssist || !canDeepAssist}
        >
          <Users className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          修改全文
        </Button>
      </div>
    </section>
  );
}
