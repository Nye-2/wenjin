"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

interface WorkspaceActionLinkProps {
  href: string;
  style?: CSSProperties;
  children: ReactNode;
}

export function WorkspaceActionLink({
  href,
  style,
  children,
}: WorkspaceActionLinkProps) {
  if (isInternalHref(href)) {
    return (
      <Link href={href} style={style}>
        {children}
      </Link>
    );
  }

  return (
    <a href={href} style={style} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

function isInternalHref(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//");
}
