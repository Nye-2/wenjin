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
        color: "var(--v2-text-primary)",
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
        color: "var(--v2-text-primary)",
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
        color: "var(--v2-text-secondary)",
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
        color: "var(--v2-text-secondary)",
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
        color: "var(--v2-text-secondary)",
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
        fontFamily: "var(--v2-font-mono)",
        fontSize: 12,
        padding: "2px 5px",
        borderRadius: 6,
        background: "rgba(20, 20, 30, 0.06)",
        color: "var(--v2-text-primary)",
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
        color: "var(--v2-accent-blue-700)",
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
  const content = preview.previewText?.trim();
  if (!content) {
    return (
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.6,
          color: "var(--v2-text-tertiary)",
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

  if (preview.previewMode === "plain_text" || preview.previewMode === "json_fallback") {
    return (
      <pre
        data-testid="result-preview-plain-text"
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontSize: 13,
          lineHeight: 1.7,
          color: "var(--v2-text-secondary)",
          fontFamily:
            preview.previewMode === "json_fallback"
              ? "var(--v2-font-mono)"
              : "var(--v2-font-sans)",
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
        color: "var(--v2-text-secondary)",
      }}
    >
      {content}
    </div>
  );
}
