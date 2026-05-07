"use client";

import { useState } from "react";

interface WorkspaceAssetsProps {
  defaultOpen: boolean;
}

export function WorkspaceAssets({ defaultOpen }: WorkspaceAssetsProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div data-testid="workspace-assets">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-[12px] font-medium"
        style={{
          color: "var(--compute-text-primary)",
          borderBottom: open ? "1px solid var(--compute-border-subtle)" : undefined,
        }}
      >
        <span>📚 文献 · 📦 成果 · 🧠 上下文</span>
        <span style={{ color: "var(--compute-text-muted)" }}>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div
          className="px-3 py-4 text-[11px]"
          style={{ color: "var(--compute-text-muted)" }}
        >
          （在 Plan 3 中接入真实子组件）
        </div>
      )}
    </div>
  );
}
