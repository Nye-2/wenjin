"use client";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { Components } from "react-markdown";

const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-4 text-lg font-semibold text-[var(--wjn-text)] first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-3 text-base font-semibold text-[var(--wjn-text)] first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-3 text-sm font-semibold text-[var(--wjn-text)] first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="mb-2 text-sm leading-7 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-2 ml-4 list-disc space-y-1 text-sm leading-7 last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 ml-4 list-decimal space-y-1 text-sm leading-7 last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-[var(--wjn-evidence)] pl-3 text-sm italic text-[var(--wjn-text-secondary)] last:mb-0">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <pre className="mb-2 overflow-x-auto rounded-xl bg-[var(--wjn-surface-subtle)] p-3 text-xs leading-6 last:mb-0">
          <code className={className}>{children}</code>
        </pre>
      );
    }
    return (
      <code className="rounded-md bg-[var(--wjn-surface-subtle)] px-1.5 py-0.5 text-xs font-medium">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <>{children}</>,
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="w-full text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="border-b border-[var(--wjn-line)] text-left text-xs font-semibold text-[var(--wjn-text-secondary)]">
      {children}
    </thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-[var(--wjn-line)]">{children}</tr>
  ),
  th: ({ children }) => <th className="px-2 py-1.5">{children}</th>,
  td: ({ children }) => (
    <td className="px-2 py-1.5 text-[var(--wjn-text)]">{children}</td>
  ),
  hr: () => <hr className="ink-divider my-3" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[var(--wjn-blue)] underline decoration-[var(--wjn-blue)]/30 underline-offset-2 hover:decoration-[var(--wjn-blue)]"
    >
      {children}
    </a>
  ),
};

interface MarkdownRendererProps {
  content: string;
  className?: string;
  components?: Components;
}

const protectedCodePattern = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g;

export function normalizeLatexDelimiters(content: string): string {
  return content
    .split(protectedCodePattern)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;
      return segment
        .replace(/\\\[([\s\S]*?)\\\]/g, (_match, expression: string) =>
          `\n\n$$\n${expression.trim()}\n$$\n\n`,
        )
        .replace(/\\\(([\s\S]*?)\\\)/g, (_match, expression: string) =>
          `$${expression.trim()}$`,
        );
    })
    .join("");
}

export function MarkdownRenderer({
  content,
  className,
  components,
}: MarkdownRendererProps) {
  return (
    <div className={`wjn-markdown ${className ?? ""}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ ...markdownComponents, ...components }}
      >
        {normalizeLatexDelimiters(content)}
      </ReactMarkdown>
    </div>
  );
}
