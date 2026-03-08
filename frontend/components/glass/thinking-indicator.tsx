"use client";

import { motion } from "framer-motion";

export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-2 h-2 rounded-full bg-current"
            animate={{
              y: [0, -4, 0],
              opacity: [0.5, 1, 0.5]
            }}
            transition={{
              duration: 0.6,
              repeat: Infinity,
              delay: i * 0.15
            }}
          />
        ))}
      </div>
      <span className="text-sm">正在思考</span>
    </div>
  );
}
