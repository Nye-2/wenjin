"use client";

import { motion } from "framer-motion";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { cn } from "@/lib/utils";

interface StreamingTextProps {
  text: string;
  isStreaming: boolean;
  className?: string;
  cursorClassName?: string;
}

export function StreamingText({
  text,
  isStreaming,
  className,
  cursorClassName,
}: StreamingTextProps) {
  return (
    <div className="relative">
      <div className="inline">
        <MarkdownRenderer
          content={text}
          className={cn("text-sm", className)}
        />
      </div>
      {isStreaming && (
        <motion.span
          className={cn(
            "inline-block w-0.5 h-4 bg-[var(--accent-primary)] ml-0.5 align-middle rounded-full",
            cursorClassName
          )}
          animate={{ opacity: [1, 0.3] }}
          transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </div>
  );
}
