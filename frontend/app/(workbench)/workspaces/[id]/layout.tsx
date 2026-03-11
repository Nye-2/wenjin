"use client";

import { ReactNode } from "react";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {children}
    </div>
  );
}
