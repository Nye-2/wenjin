"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body style={{ fontFamily: "monospace", padding: "2rem", background: "var(--wjn-text)", color: "var(--wjn-line)" }}>
        <h2 style={{ color: "var(--wjn-error)", marginBottom: "1rem" }}>Application Error</h2>
        <pre
          style={{
            background: "var(--wjn-text)",
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
          <p style={{ marginTop: "1rem", color: "var(--wjn-text-muted)", fontSize: "0.8rem" }}>
            Digest: {error.digest}
          </p>
        )}
        <button
          onClick={reset}
          style={{
            marginTop: "1.5rem",
            padding: "0.5rem 1.5rem",
            background: "var(--wjn-blue)",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
