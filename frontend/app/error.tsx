"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[PageError]", error);
  }, [error]);

  return (
    <div style={{ fontFamily: "monospace", padding: "2rem", background: "#0a1628", color: "#e2e8f0", minHeight: "100vh" }}>
      <h2 style={{ color: "#f87171", marginBottom: "1rem" }}>Page Error</h2>
      <pre
        style={{
          background: "#1e293b",
          padding: "1rem",
          borderRadius: "8px",
          overflow: "auto",
          fontSize: "0.85rem",
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
        }}
      >
        {error?.message}
        {"\n\n"}
        {error?.stack}
      </pre>
      {error?.digest && (
        <p style={{ marginTop: "1rem", color: "#94a3b8", fontSize: "0.8rem" }}>
          Digest: {error.digest}
        </p>
      )}
      <button
        onClick={reset}
        style={{
          marginTop: "1.5rem",
          padding: "0.5rem 1.5rem",
          background: "#3b82c4",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
        }}
      >
        Try again
      </button>
    </div>
  );
}
