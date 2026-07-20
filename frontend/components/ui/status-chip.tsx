import { cn } from "@/lib/utils";

const STATUS_CLASS = {
  neutral:
    "border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-secondary)]",
  running:
    "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue-strong)]",
  review:
    "border-[rgba(181,133,47,0.24)] bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]",
  success:
    "border-[rgba(46,125,82,0.22)] bg-[var(--wjn-success-soft)] text-[var(--wjn-success)]",
  error:
    "border-[rgba(179,52,62,0.22)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)]",
} as const;

export function StatusChip({
  label,
  tone = "neutral",
  className,
}: {
  label: string;
  tone?: keyof typeof STATUS_CLASS;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 max-w-full items-center rounded-[var(--wjn-radius-pill)] border px-2 text-[11px] font-semibold leading-none",
        STATUS_CLASS[tone],
        className,
      )}
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
