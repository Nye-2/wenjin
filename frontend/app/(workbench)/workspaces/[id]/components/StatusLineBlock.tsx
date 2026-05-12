"use client";

interface StatusLineBlockProps {
  content: string;
}

export function StatusLineBlock({ content }: StatusLineBlockProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        borderLeft: "2px solid var(--v2-accent-blue-700)",
        margin: "4px 0 4px 4px",
        fontSize: 12,
        color: "var(--v2-text-secondary)",
      }}
    >
      <span style={{ color: "var(--v2-accent-blue-700)" }}>→</span>
      {content}
    </div>
  );
}
