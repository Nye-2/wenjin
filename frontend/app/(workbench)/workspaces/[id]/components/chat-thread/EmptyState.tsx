"use client";

/**
 * EmptyState · Plan 2 T13
 *
 * Shown when a chat thread has no messages yet. Renders the feature
 * description and 3 starter prompts derived from the feature's
 * guidance_prompt header.
 */
interface FeatureMeta {
  id: string;
  name: string;
  description: string;
}

interface EmptyStateProps {
  feature: FeatureMeta | null;
  starterPrompts: string[];
  onPick?: (text: string) => void;
}

export function EmptyState({
  feature,
  starterPrompts,
  onPick,
}: EmptyStateProps) {
  if (!feature) {
    return (
      <div
        className="px-6 py-12 text-center text-[12.5px]"
        style={{ color: "var(--text-muted)" }}
      >
        输入开始对话。
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 px-6 py-10">
      <div>
        <div
          className="text-[18px] font-semibold"
          style={{
            fontFamily: "var(--font-serif)",
            color: "var(--text-primary)",
          }}
        >
          {feature.name}
        </div>
        <div
          className="mt-1.5 text-[13px] leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          {feature.description}
        </div>
      </div>

      {starterPrompts.length > 0 && (
        <div>
          <div
            className="mb-2 text-[10.5px] uppercase tracking-wider"
            style={{ color: "var(--text-muted)" }}
          >
            想这样开始？
          </div>
          <div className="flex flex-col gap-1.5">
            {starterPrompts.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => onPick?.(p)}
                className="rounded-md px-3.5 py-2.5 text-left text-[13px] leading-relaxed transition-colors hover:opacity-80"
                style={{
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
