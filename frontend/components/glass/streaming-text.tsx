"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

interface StreamingTextProps {
  text: string;
  isStreaming: boolean;
  speed?: number;
}

export function StreamingText({ text, isStreaming, speed = 30 }: StreamingTextProps) {
  const [displayedText, setDisplayedText] = useState("");

  useEffect(() => {
    if (!isStreaming) {
      setDisplayedText(text);
      return;
    }

    let index = 0;
    const interval = setInterval(() => {
      if (index < text.length) {
        setDisplayedText(text.slice(0, index + 1));
        index++;
      } else {
        clearInterval(interval);
      }
    }, speed);

    return () => clearInterval(interval);
  }, [text, isStreaming, speed]);

  return (
    <span className="relative">
      {displayedText}
      {isStreaming && (
        <motion.span
          className="inline-block w-0.5 h-[1.1em] bg-current ml-0.5 align-middle"
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity }}
        />
      )}
    </span>
  );
}
