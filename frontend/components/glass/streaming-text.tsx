"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

interface StreamingTextProps {
  text: string;
  isStreaming: boolean;
}

export function StreamingText({ text, isStreaming }: StreamingTextProps) {
  const [displayedText, setDisplayedText] = useState(text);

  useEffect(() => {
    setDisplayedText(text);
  }, [text, isStreaming]);

  return (
    <div className="relative">
      <div className="inline">
        <MarkdownRenderer content={displayedText} className="text-sm" />
      </div>
      {isStreaming && (
        <motion.span
          className="inline-block w-0.5 h-4 bg-[var(--accent-primary)] ml-0.5 align-middle rounded-full"
          animate={{ opacity: [1, 0.3] }}
          transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </div>
  );
}
