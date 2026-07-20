import { cn } from "@/lib/utils";

/**
 * 状态 pill —— 两级命名规范的状态级。
 * 语义：回答「到哪一步了」，与 TypeChip（回答「这是什么」）互不混用。
 * - verified：已查证（主色绿）
 * - pending：待你确认 / 待你补充（黄铜，仅"等待你"类信号）
 * - done：已完成/已保存（墨色中性）
 * - failed：失败（错误红）
 */
const PILL_CLASS = {
  verified:
    "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]",
  pending:
    "bg-[rgba(181,133,47,0.12)] text-[var(--wjn-review)]",
  done:
    "bg-[rgba(28,36,32,0.06)] text-[var(--wjn-text-secondary)]",
  failed:
    "bg-[var(--wjn-error-soft)] text-[var(--wjn-error)]",
} as const;

export type StatusPillTone = keyof typeof PILL_CLASS;

export function StatusPill({
  label,
  tone = "done",
  dot = true,
  className,
}: {
  label: string;
  tone?: StatusPillTone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-[3px] text-[11px] font-medium leading-none",
        PILL_CLASS[tone],
        className,
      )}
    >
      {dot ? <span className="h-[5px] w-[5px] rounded-full bg-current" /> : null}
      <span className="truncate">{label}</span>
    </span>
  );
}
