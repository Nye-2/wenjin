"use client";

import { ReactNode } from "react";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default async function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  return (
    <div className="h-screen flex flex-col bg-gradient-to-b from-slate-50 to-indigo-50/30 dark:from-slate-950 dark:to-indigo-950/30">
      {children}
    </div>
  );
}
