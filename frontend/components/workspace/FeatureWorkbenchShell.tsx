"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface FeatureWorkbenchShellProps {
  workspaceId: string;
  title: string;
  description: string;
  icon: LucideIcon;
  iconBgClass: string;
  iconClass: string;
  sidebarTitle?: string;
  sidebar?: ReactNode;
  headerActions?: ReactNode;
  sidebarWidthClassName?: string;
  sidebarClassName?: string;
  mainPaneClassName?: string;
  contentClassName?: string;
  contentAnimated?: boolean;
  children: ReactNode;
}

export function FeatureWorkbenchShell({
  workspaceId,
  title,
  description,
  icon: Icon,
  iconBgClass,
  iconClass,
  sidebarTitle,
  sidebar,
  headerActions,
  sidebarWidthClassName,
  sidebarClassName,
  mainPaneClassName,
  contentClassName,
  contentAnimated = true,
  children,
}: FeatureWorkbenchShellProps) {
  const router = useRouter();
  const content = contentAnimated ? (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("space-y-4 sm:space-y-6", contentClassName)}
    >
      {children}
    </motion.div>
  ) : (
    <div className={contentClassName}>{children}</div>
  );

  return (
    <>
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.9)] px-4 py-3 backdrop-blur-xl">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => router.push(`/workspaces/${workspaceId}`)}
            className={cn(
              "rounded-2xl p-2.5",
              "bg-white/80",
              "hover:bg-[var(--bg-muted)]",
              "text-[var(--text-secondary)]",
              "transition-colors"
            )}
          >
            <ArrowLeft className="w-5 h-5" />
          </motion.button>

          <div className="flex min-w-0 items-center gap-3">
            <div className={cn("rounded-2xl p-2.5", iconBgClass)}>
              <Icon className={cn("w-5 h-5", iconClass)} />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                工作模块
              </p>
              <h1 className="truncate text-base font-semibold text-[var(--text-primary)] sm:text-lg">
                {title}
              </h1>
              <p className="truncate text-xs text-[var(--text-secondary)]">
                {description}
              </p>
            </div>
          </div>
        </div>
        {headerActions && (
          <div className="flex w-full justify-start sm:w-auto sm:justify-end">
            {headerActions}
          </div>
        )}
      </header>

      <main className="flex flex-1 flex-col overflow-hidden lg:flex-row">
        {sidebar ? (
          <aside
            className={cn(
              "w-full max-h-[40vh] overflow-auto border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.88)] p-4 lg:max-h-none lg:shrink-0 lg:border-b-0 lg:border-r",
              sidebarWidthClassName ?? "lg:w-80",
              sidebarClassName
            )}
          >
            {sidebarTitle ? (
              <h2 className="mb-4 text-sm font-medium text-[var(--text-primary)]">
                {sidebarTitle}
              </h2>
            ) : null}
            {sidebar}
          </aside>
        ) : null}

        <div
          className={cn(
            "route-topography flex-1 overflow-auto p-4 sm:p-6",
            mainPaneClassName
          )}
        >
          {content}
        </div>
      </main>
    </>
  );
}
