"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import { WorkspaceActionLink } from "../WorkspaceActionLink";

interface ResultPreviewRendererProps {
  preview: WorkspaceResultPreview;
}

const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1
      style={{
        margin: "0 0 10px",
        fontSize: 18,
        lineHeight: 1.35,
        fontWeight: 700,
        color: "var(--wjn-text)",
      }}
    >
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2
      style={{
        margin: "14px 0 8px",
        fontSize: 15,
        lineHeight: 1.4,
        fontWeight: 650,
        color: "var(--wjn-text)",
      }}
    >
      {children}
    </h2>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p
      style={{
        margin: "0 0 10px",
        fontSize: 13.5,
        lineHeight: 1.7,
        color: "var(--wjn-text-secondary)",
      }}
    >
      {children}
    </p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul
      style={{
        margin: "0 0 10px 20px",
        padding: 0,
        color: "var(--wjn-text-secondary)",
      }}
    >
      {children}
    </ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol
      style={{
        margin: "0 0 10px 20px",
        padding: 0,
        color: "var(--wjn-text-secondary)",
      }}
    >
      {children}
    </ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li
      style={{
        marginBottom: 6,
        fontSize: 13.5,
        lineHeight: 1.7,
      }}
    >
      {children}
    </li>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code
      style={{
        fontFamily: "var(--wjn-font-mono)",
        fontSize: 12,
        padding: "2px 5px",
        borderRadius: 6,
        background: "rgba(20, 20, 30, 0.06)",
        color: "var(--wjn-text)",
      }}
    >
      {children}
    </code>
  ),
  a: ({
    href,
    children,
  }: {
    href?: string;
    children?: React.ReactNode;
  }) =>
    href ? (
    <WorkspaceActionLink
      href={href}
      style={{
        color: "var(--wjn-blue)",
        textDecoration: "underline",
        textUnderlineOffset: 2,
      }}
    >
      {children}
    </WorkspaceActionLink>
    ) : (
      <span>{children}</span>
    ),
};

export function ResultPreviewRenderer({
  preview,
}: ResultPreviewRendererProps) {
  if (preview.previewMode === "image") {
    const path = preview.previewPath?.trim();
    return (
      <div
        data-testid="result-preview-image"
        style={{
          display: "grid",
          gap: 10,
          padding: 14,
          borderRadius: "var(--wjn-radius-lg)",
          border: "1px solid var(--wjn-line)",
          background: "var(--wjn-surface-subtle)",
          color: "var(--wjn-text-secondary)",
        }}
      >
        <div
          style={{
            height: 136,
            borderRadius: "var(--wjn-radius-md)",
            border: "1px dashed rgba(20, 20, 30, 0.18)",
            background:
              "linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0.42))",
            display: "grid",
            placeItems: "center",
            overflow: "hidden",
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: 92,
              height: 58,
              display: "flex",
              alignItems: "end",
              justifyContent: "center",
              gap: 8,
              borderBottom: "1px solid rgba(20,20,30,0.2)",
              borderLeft: "1px solid rgba(20,20,30,0.2)",
              padding: "0 10px 6px",
            }}
          >
            {[28, 44, 36, 52].map((height) => (
              <span
                key={height}
                style={{
                  width: 9,
                  height,
                  borderRadius: "3px 3px 0 0",
                  background: "rgba(124, 58, 237, 0.52)",
                }}
              />
            ))}
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gap: 4,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 650,
              color: "var(--wjn-text)",
            }}
          >
            图表预览
          </div>
          {path ? (
            <code
              style={{
                fontFamily: "var(--wjn-font-mono)",
                fontSize: 12,
                color: "var(--wjn-text-muted)",
                wordBreak: "break-all",
              }}
            >
              {path}
            </code>
          ) : (
            <span
              style={{
                fontSize: 12.5,
                color: "var(--wjn-text-muted)",
              }}
            >
              产物路径将在保存后由工作区解析。
            </span>
          )}
        </div>
      </div>
    );
  }

  const content = preview.previewText?.trim();
  if (!content) {
    return (
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.6,
          color: "var(--wjn-text-muted)",
        }}
      >
        No preview available yet.
      </div>
    );
  }

  if (preview.previewMode === "markdown" || preview.previewMode === "outline") {
    return (
      <div data-testid="result-preview-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={markdownComponents}
        >
          {content}
        </ReactMarkdown>
      </div>
    );
  }

  if (preview.previewMode === "plain_text" || preview.previewMode === "structured_json") {
    return (
      <pre
        data-testid="result-preview-plain-text"
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontSize: 13,
          lineHeight: 1.7,
          color: "var(--wjn-text-secondary)",
          fontFamily:
            preview.previewMode === "structured_json"
              ? "var(--wjn-font-mono)"
              : "var(--wjn-font-sans)",
        }}
      >
        {content}
      </pre>
    );
  }

  return (
    <div
      data-testid="result-preview-citation"
      style={{
        fontSize: 13.5,
        lineHeight: 1.7,
        color: "var(--wjn-text-secondary)",
      }}
    >
      {content}
    </div>
  );
}
