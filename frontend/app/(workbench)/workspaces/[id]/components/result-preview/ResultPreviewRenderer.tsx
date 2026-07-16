"use client";

import { useState } from "react";
import type { Components } from "react-markdown";

import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import { WorkspaceActionLink } from "../WorkspaceActionLink";

interface ResultPreviewRendererProps {
  preview: WorkspaceResultPreview;
}

const previewMarkdownComponents: Components = {
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
  const [imageFailed, setImageFailed] = useState(false);
  if (preview.previewMode === "image") {
    const path = preview.previewPath?.trim();
    const imageUrl = safeImageUrl(preview.previewUrl);
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
            background: "var(--wjn-surface)",
            display: "grid",
            placeItems: "center",
            overflow: "hidden",
          }}
        >
          {imageUrl && !imageFailed ? (
            <img
              src={imageUrl}
              alt={`${preview.title} 图像预览`}
              loading="lazy"
              decoding="async"
              onError={() => setImageFailed(true)}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                background: "var(--wjn-surface)",
              }}
            />
          ) : (
            <FigurePlaceholder />
          )}
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
          ) : imageUrl ? (
            <span
              style={{
                fontSize: 12.5,
                color: "var(--wjn-text-muted)",
              }}
            >
              已加载图像预览。
            </span>
          ) : (
            <span
              style={{
                fontSize: 12.5,
                color: "var(--wjn-text-muted)",
              }}
            >
              结果路径将在保存后由工作区解析。
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
        data-testid="result-preview-unavailable"
        style={{
          display: "grid",
          gap: 6,
          padding: 14,
          borderRadius: "var(--wjn-radius-lg)",
          border: "1px solid var(--wjn-line)",
          background: "var(--wjn-surface-subtle)",
        }}
      >
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 650,
            color: "var(--wjn-text)",
          }}
        >
          暂时无法预览这项结果
        </div>
        <div
          style={{
            fontSize: 13,
            lineHeight: 1.6,
            color: "var(--wjn-text-muted)",
          }}
        >
          请先在复核区确认是否保存；保存后可在对应工作区房间继续查看。
        </div>
      </div>
    );
  }

  if (preview.previewMode === "document_diff") {
    return (
      <DocumentPreviewFrame
        testId="result-preview-document-diff"
        title="文档修改对比"
        subtitle="请确认修改是否符合你的材料和证据要求。"
      >
        <pre
          style={{
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 13,
            lineHeight: 1.72,
            color: "var(--wjn-text-secondary)",
            fontFamily: "var(--wjn-font-sans)",
          }}
        >
          {content}
        </pre>
      </DocumentPreviewFrame>
    );
  }

  if (preview.kind === "document") {
    return (
      <DocumentPreviewFrame
        testId="result-preview-document-excerpt"
        title="文档摘录"
      >
        <PreviewTextBody preview={preview} content={content} />
      </DocumentPreviewFrame>
    );
  }

  return <PreviewTextBody preview={preview} content={content} />;
}

function PreviewTextBody({
  preview,
  content,
}: {
  preview: WorkspaceResultPreview;
  content: string;
}) {
  if (preview.previewMode === "markdown" || preview.previewMode === "outline") {
    return (
      <div data-testid="result-preview-markdown" className="prose-chat">
        <MarkdownRenderer
          content={content}
          components={previewMarkdownComponents}
        />
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

function DocumentPreviewFrame({
  testId,
  title,
  subtitle,
  children,
}: {
  testId: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      style={{
        display: "grid",
        gap: 10,
        padding: 14,
        borderRadius: "var(--wjn-radius-lg)",
        border: "1px solid var(--wjn-line)",
        background: "var(--wjn-surface-subtle)",
      }}
    >
      <div style={{ display: "grid", gap: 3 }}>
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 650,
            color: "var(--wjn-text)",
          }}
        >
          {title}
        </div>
        {subtitle ? (
          <div
            style={{
              fontSize: 12.5,
              lineHeight: 1.55,
              color: "var(--wjn-text-muted)",
            }}
          >
            {subtitle}
          </div>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function FigurePlaceholder() {
  return (
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
            background: "var(--wjn-accent)",
          }}
        />
      ))}
    </div>
  );
}

function safeImageUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed || /[\u0000-\u001F\u007F]/.test(trimmed)) {
    return null;
  }
  if (trimmed.startsWith("https://")) {
    return trimmed;
  }
  if (trimmed.startsWith("/api/") || trimmed.startsWith("/workspaces/")) {
    return trimmed.startsWith("//") ? null : trimmed;
  }
  return null;
}
