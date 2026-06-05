"use client";

import Link from "next/link";
import { FileText, SearchCheck, Sparkles } from "lucide-react";
import { ReactNode } from "react";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";

type AuthMode = "login" | "register";

interface AuthShellProps {
  mode: AuthMode;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}

const highlights = [
  {
    icon: SearchCheck,
    titleKey: "auth.shell.highlights.sources.title",
    descriptionKey: "auth.shell.highlights.sources.description",
  },
  {
    icon: FileText,
    titleKey: "auth.shell.highlights.drafts.title",
    descriptionKey: "auth.shell.highlights.drafts.description",
  },
  {
    icon: Sparkles,
    titleKey: "auth.shell.highlights.delivery.title",
    descriptionKey: "auth.shell.highlights.delivery.description",
  },
];

export function AuthShell({
  mode,
  title,
  description,
  children,
  footer,
}: AuthShellProps) {
  const { t } = useI18n();
  const supportedTypes = [
    t("workspace.types.sci"),
    t("workspace.types.proposal"),
    t("workspace.types.patent"),
  ];

  return (
    <div className="wjn-shell-bg relative min-h-screen overflow-hidden px-4 py-8 sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--wjn-navy),var(--wjn-blue)_72%,var(--wjn-gold)_72%,var(--wjn-gold)_74%,var(--wjn-blue)_74%,var(--wjn-navy))]" />

      <div className="relative mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.08fr_0.92fr]">
        <aside className="hidden rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[rgba(255,255,255,0.82)] p-10 shadow-[var(--wjn-shadow-md)] backdrop-blur-md lg:flex lg:flex-col">
          <div className="inline-flex w-fit items-center gap-3 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white px-4 py-2 text-sm font-semibold text-[var(--wjn-navy)] shadow-[var(--wjn-shadow-sm)]">
            <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden rounded-[12px] bg-[linear-gradient(145deg,var(--wjn-navy),var(--wjn-blue)_72%,#4d78b9)] shadow-[0_10px_24px_rgba(44,93,160,0.20)]">
              <svg className="absolute inset-0 h-full w-full opacity-95" viewBox="0 0 44 44" fill="none" aria-hidden="true">
                <path
                  d="M8 31C14 24 20 22 26 19C31 17 34 14 36 10"
                  stroke="rgba(255,255,255,0.92)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle cx="8" cy="31" r="3" fill="rgba(255,255,255,0.92)" />
                <circle cx="26" cy="19" r="2.4" fill="rgba(255,255,255,0.72)" />
                <circle cx="36" cy="10" r="3.1" fill="var(--wjn-gold)" />
              </svg>
            </div>
            <span>{t("brand.cn")}</span>
            <span className="text-xs uppercase tracking-[0.24em] text-[var(--wjn-text-muted)]">
              {t("brand.en")}
            </span>
          </div>

          <div className="mt-10 space-y-4">
            <h2 className="max-w-xl text-4xl font-semibold tracking-[-0.03em] text-[var(--wjn-text)]">
              {t("auth.shell.title")}
            </h2>
            <p className="max-w-lg text-base leading-8 text-[var(--wjn-text-secondary)]">
              {t("auth.shell.subtitle")}
            </p>
          </div>

          <div className="mt-8">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wjn-text-muted)]">
              {t("auth.shell.supported")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {supportedTypes.map((type) => (
                <span
                  key={type}
                  className="rounded-full border border-[var(--wjn-line)] bg-white px-3 py-1.5 text-sm text-[var(--wjn-text-secondary)]"
                >
                  {type}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-10 space-y-4">
            {highlights.map((item) => (
              <div
                key={item.titleKey}
                className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white px-5 py-4 shadow-[var(--wjn-shadow-sm)]"
              >
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--wjn-text)]">
                  <item.icon className="h-4 w-4 text-[var(--wjn-blue)]" />
                  {t(item.titleKey)}
                </div>
                <p className="text-sm leading-7 text-[var(--wjn-text-secondary)]">
                  {t(item.descriptionKey)}
                </p>
              </div>
            ))}
          </div>
        </aside>

        <section className="rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-[var(--wjn-shadow-lg)]">
          <header className="space-y-5 border-b border-[var(--wjn-line)] p-6 sm:p-8">
            <div className="inline-flex w-fit items-center rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-1">
              <Link
                href="/login"
                className={cn(
                  "rounded-[var(--wjn-radius)] px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "login"
                    ? "bg-white text-[var(--wjn-text)] shadow-sm"
                    : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                )}
              >
                {t("auth.login.button")}
              </Link>
              <Link
                href="/register"
                className={cn(
                  "rounded-[var(--wjn-radius)] px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "register"
                    ? "bg-white text-[var(--wjn-text)] shadow-sm"
                    : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                )}
              >
                {t("auth.register.button")}
              </Link>
            </div>

            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-[-0.025em] text-[var(--wjn-text)]">
                {title}
              </h1>
              <p className="text-sm leading-7 text-[var(--wjn-text-secondary)]">{description}</p>
            </div>
          </header>

          <div className="space-y-6 p-6 sm:p-8">
            {children}
            <div className="border-t border-[var(--wjn-line)] pt-4 text-sm text-[var(--wjn-text-secondary)]">
              {footer}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
