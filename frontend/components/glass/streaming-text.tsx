"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

interface StreamingTextProps {
  text: string;
  isStreaming: boolean;
  speed?: number;
}

export function StreamingText({ text, isStreaming, speed = 12 }: StreamingTextProps) {
  const [displayedText, setDisplayedText] = useState(text);
  const prevLengthRef = useRef(0);

  useEffect(() => {
    if (!isStreaming) {
      setDisplayedText(text);
      prevLengthRef.current = text.length;
      return;
    }

    // When new text arrives during streaming, show it immediately
    // (the backend already streams chunk by chunk, no need for char-by-char simulation)
    setDisplayedText(text);
    prevLengthRef.current = text.length;
  }, [text, isStreaming]);

  return (
    <div className="relative">
      <MarkdownRenderer content={displayedText} className="text-sm" />
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
