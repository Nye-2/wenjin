"use client";

/**
 * RunContainer · Plan 2 T12
 *
 * Groups all messages of a single run inside a foldable wrapper.
 * Current run renders inline (no fold); completed runs collapse to a
 * single-line header (轮 N · title ✓) that the user can click to expand.
 */
import { useState } from "react";

interface RunContainerProps {
  index: number;
  title: string;
  isCurrent: boolean;
  children: React.ReactNode;
}

export function RunContainer({
  index,
  title,
  isCurrent,
  children,
}: RunContainerProps) {
  const [open, setOpen] = useState(isCurrent);

  // Current run: render inline, no header chrome.
  if (isCurrent) {
    return <div className="flex flex-col gap-3">{children}</div>;
  }

  return (
    <div
      className="rounded-lg"
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-[12px] transition-opacity hover:opacity-80"
        style={{ color: "var(--text-secondary)" }}
      >
        <span>
          轮 {index} · {title} ✓
        </span>
        <span style={{ color: "var(--text-muted)" }}>{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="flex flex-col gap-3 px-3 pb-3 pt-1">{children}</div>
      )}
    </div>
  );
}
