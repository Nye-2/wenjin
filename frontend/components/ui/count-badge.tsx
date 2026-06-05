import { cn } from "@/lib/utils";

export function CountBadge({
  count,
  tone = "default",
  className,
  hiddenFromAssistive = true,
}: {
  count: number;
  tone?: "default" | "review" | "success";
  className?: string;
  hiddenFromAssistive?: boolean;
}) {
  if (count <= 0) {
    return null;
  }

  return (
    <span
      aria-hidden={hiddenFromAssistive}
      className={cn(
        "wjn-tabular inline-flex h-4 min-w-4 items-center justify-center rounded-[var(--wjn-radius-pill)] px-1 text-[10px] font-bold leading-none text-white",
        tone === "review"
          ? "bg-[var(--wjn-review)]"
          : tone === "success"
            ? "bg-[var(--wjn-success)]"
            : "bg-[var(--wjn-blue)]",
        className,
      )}
    >
      {Math.min(count, 99)}
    </span>
  );
}
