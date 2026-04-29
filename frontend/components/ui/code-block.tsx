"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Copy, Check } from "lucide-react";

interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
  showLineNumbers?: boolean;
  copyable?: boolean;
  maxHeight?: string;
}

export function CodeBlock({
  code,
  language,
  className,
  showLineNumbers = false,
  copyable = true,
  maxHeight,
}: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);
  const lines = code.split("\n");

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "compute-card relative overflow-hidden font-mono text-sm",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-compute-border px-3 py-2">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-compute-red/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-compute-gold/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-compute-green/60" />
          </div>
          {language && (
            <span className="ml-2 text-xs text-compute-text-muted uppercase tracking-wider">
              {language}
            </span>
          )}
        </div>
        {copyable && (
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-compute-text-muted transition-colors hover:bg-compute-surface hover:text-compute-text-secondary"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" />
                已复制
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                复制
              </>
            )}
          </button>
        )}
      </div>

      {/* Code Content */}
      <div
        className="compute-scroll overflow-auto bg-compute-base p-3"
        style={{ maxHeight }}
      >
        <pre className="m-0">
          <code>
            {lines.map((line, i) => (
              <div key={i} className="flex">
                {showLineNumbers && (
                  <span className="mr-4 inline-block w-8 select-none text-right text-compute-text-muted text-xs">
                    {i + 1}
                  </span>
                )}
                <span className="text-compute-text-primary whitespace-pre">
                  {line || " "}
                </span>
              </div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}

interface InlineCodeProps {
  children: React.ReactNode;
  className?: string;
}

export function InlineCode({ children, className }: InlineCodeProps) {
  return (
    <code
      className={cn(
        "inline rounded-md bg-compute-surface px-1.5 py-0.5 font-mono text-xs text-compute-cyan",
        className
      )}
    >
      {children}
    </code>
  );
}
