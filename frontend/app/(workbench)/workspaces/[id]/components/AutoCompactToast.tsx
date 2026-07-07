"use client";

import { useState } from "react";
import { authorizedFetch } from "@/lib/api/client";

// ── Types ────────────────────────────────────────────────────────────────────

interface AutoCompactToastProps {
  workspaceId: string;
  visible: boolean;
  onDismiss: () => void;
}

// ── Component ────────────────────────────────────────────────────────────────

export function AutoCompactToast({
  workspaceId,
  visible,
  onDismiss,
}: AutoCompactToastProps) {
  const [compacting, setCompacting] = useState(false);
  const [done, setDone] = useState(false);

  if (!visible) return null;

  const handleCompact = async () => {
    setCompacting(true);
    try {
      const res = await authorizedFetch(`/api/workspaces/${workspaceId}/chat/compact`, {
        method: "POST",
      });
      if (res.ok) {
        setDone(true);
        setTimeout(onDismiss, 2000);
      }
    } finally {
      setCompacting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        padding: "12px 20px",
        borderRadius: "var(--wjn-radius-lg)",
        background: "var(--wjn-surface)",
        boxShadow: "var(--wjn-shadow-md)",
        border: "1px solid var(--wjn-line)",
        display: "flex",
        alignItems: "center",
        gap: 12,
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 13.5,
        color: "var(--wjn-text)",
        animation: "wjn-panel-in 200ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      {done ? (
        <>
          <span style={{ fontSize: 16 }}>&#10003;</span>
          <span>上下文已压缩</span>
        </>
      ) : (
        <>
          <span>上下文接近上限</span>
          <button
            onClick={handleCompact}
            disabled={compacting}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--wjn-radius)",
              border: "none",
              background: "var(--wjn-blue)",
              color: "white",
              fontSize: 13,
              fontWeight: 500,
              cursor: compacting ? "wait" : "pointer",
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            {compacting ? "压缩中..." : "压缩"}
          </button>
          <button
            onClick={onDismiss}
            style={{
              padding: "6px 10px",
              borderRadius: "var(--wjn-radius)",
              border: "1px solid var(--wjn-line)",
              background: "transparent",
              color: "var(--wjn-text-secondary)",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            稍后
          </button>
        </>
      )}
    </div>
  );
}
