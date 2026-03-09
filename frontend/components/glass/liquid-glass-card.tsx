"use client";

import { forwardRef } from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";
import { scaleIn, defaultTransition } from "@/lib/animations";

interface LiquidGlassCardProps extends HTMLMotionProps<"div"> {
  variant?: "default" | "elevated" | "floating";
  glow?: boolean;
}

export const LiquidGlassCard = forwardRef<HTMLDivElement, LiquidGlassCardProps>(
  ({ className, variant = "default", glow = false, children, ...props }, ref) => {
    return (
      <motion.div
        ref={ref}
        className={cn(
          "relative overflow-hidden rounded-2xl",
          "bg-[var(--glass-bg)]",
          "backdrop-blur-[var(--glass-blur)]",
          "border border-[var(--glass-border)]",
          "shadow-[var(--glass-shadow)]",
          variant === "elevated" && "shadow-xl",
          variant === "floating" && "hover:shadow-2xl hover:-translate-y-1 transition-transform",
          glow && "before:absolute before:inset-0 before:rounded-2xl before:p-[1px] before:bg-gradient-to-br before:from-white/40 before:to-transparent",
          className
        )}
        variants={scaleIn}
        initial="initial"
        animate="animate"
        transition={{ ...defaultTransition, duration: 0.4 }}
        {...props}
      >
        {children}
      </motion.div>
    );
  }
);

LiquidGlassCard.displayName = "LiquidGlassCard";
