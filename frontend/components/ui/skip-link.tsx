"use client";

import { cn } from "@/lib/utils";

interface SkipLinkProps {
  href: string;
  children: React.ReactNode;
  className?: string;
}

export function SkipLink({ href, children, className }: SkipLinkProps) {
  return (
    <a
      href={href}
      className={cn(
        "sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50",
        "focus:px-4 focus:py-2 focus:bg-academic-primary focus:text-white focus:rounded-lg",
        "focus:outline-none focus:ring-2 focus:ring-academic-primary focus:ring-offset-2",
        className
      )}
    >
      {children}
    </a>
  );
}
