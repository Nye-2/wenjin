import { LocateFixed, Trash2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { LatexFeedbackItem } from "@/lib/api";

export function PrismAnnotationList({
  annotations,
  activeFeedbackId,
  busyFeedbackId,
  onFocus,
  onQuickRewrite,
  onDeepAssist,
  onRemove,
}: {
  annotations: LatexFeedbackItem[];
  activeFeedbackId: string | null;
  busyFeedbackId: string | null;
  onFocus: (item: LatexFeedbackItem) => void;
  onQuickRewrite: (item: LatexFeedbackItem) => void;
  onDeepAssist: (item: LatexFeedbackItem) => void;
  onRemove: (feedbackId: string) => void;
}) {
  return (
    <section className="rounded-lg border border-[var(--wjn-line)] bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-[var(--wjn-text)]">当前文件批注</p>
        <span className="text-xs text-[var(--wjn-text-muted)]">{annotations.length} 条</span>
      </div>
      {annotations.length === 0 ? (
        <p className="mt-3 rounded-lg border border-dashed border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-5 text-center text-xs text-[var(--wjn-text-muted)]">
          选中文本后可以添加批注或生成修改。
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {annotations.map((item, index) => {
            const busy = busyFeedbackId === item.id;
            const active = activeFeedbackId === item.id;
            return (
              <article
                key={item.id}
                className={[
                  "rounded-lg border p-3",
                  active
                    ? "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)]"
                    : "border-[var(--wjn-line)] bg-white",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--wjn-text-secondary)]">
                      批注 #{index + 1}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs text-[var(--wjn-text-muted)]">
                      {item.selected_text}
                    </p>
                  </div>
                  {item.last_status === "pending" ? (
                    <span className="rounded-full border border-[var(--wjn-review)]/25 bg-[rgba(180,83,9,0.08)] px-2 py-0.5 text-[10px] text-[var(--wjn-review)]">
                      待应用
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-sm leading-5 text-[var(--wjn-text)]">
                  {item.comment}
                </p>
                {item.last_error ? (
                  <p className="mt-2 text-xs leading-5 text-red-600">{item.last_error}</p>
                ) : null}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => onFocus(item)}>
                    <LocateFixed className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    定位
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => onQuickRewrite(item)}
                    disabled={busy}
                  >
                    {busy ? "生成中..." : "改这段"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onDeepAssist(item)}
                    disabled={busy}
                  >
                    <Users className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    生成建议
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onRemove(item.id)}
                    disabled={busy}
                  >
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    删除
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
