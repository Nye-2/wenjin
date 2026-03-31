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
    <div className="relative min-h-screen overflow-hidden bg-[var(--bg-base)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="route-grid absolute inset-x-6 bottom-8 top-8 rounded-[2rem] opacity-30" />
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-32 left-1/2 h-[26rem] w-[26rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(31,66,99,0.18),transparent_68%)] blur-3xl" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(46,111,109,0.14),transparent_70%)] blur-3xl" />
        <div className="absolute left-0 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(166,124,57,0.1),transparent_72%)] blur-3xl" />
      </div>

      <div className="relative mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.08fr_0.92fr]">
        <aside className="route-card hidden rounded-[2rem] p-10 lg:flex lg:flex-col">
          <div className="inline-flex w-fit items-center gap-3 rounded-full border border-[var(--border-default)] bg-white/80 px-4 py-2 text-sm font-semibold text-[var(--accent-primary)]">
            <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden rounded-2xl bg-[linear-gradient(145deg,var(--brand-navy),var(--brand-teal))] shadow-[0_10px_24px_rgba(31,66,99,0.2)]">
              <svg className="absolute inset-0 h-full w-full opacity-95" viewBox="0 0 44 44" fill="none" aria-hidden="true">
                <path
                  d="M8 31C14 24 20 22 26 19C31 17 34 14 36 10"
                  stroke="rgba(247,244,238,0.92)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle cx="8" cy="31" r="3" fill="rgba(247,244,238,0.92)" />
                <circle cx="26" cy="19" r="2.4" fill="rgba(247,244,238,0.72)" />
                <circle cx="36" cy="10" r="3.1" fill="var(--brand-brass)" />
              </svg>
            </div>
            <span className="font-serif">{t("brand.cn")}</span>
            <span className="text-xs uppercase tracking-[0.28em] text-[var(--text-muted)]">
              {t("brand.en")}
            </span>
          </div>

          <div className="mt-10 space-y-4">
            <h2 className="max-w-xl text-4xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("auth.shell.title")}
            </h2>
            <p className="max-w-lg text-base leading-8 text-[var(--text-secondary)]">
              {t("auth.shell.subtitle")}
            </p>
          </div>

          <div className="mt-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
              {t("auth.shell.supported")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {supportedTypes.map((type) => (
                <span
                  key={type}
                  className="rounded-full border border-[var(--border-default)] bg-white/80 px-3 py-1.5 text-sm text-[var(--text-secondary)]"
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
                className="rounded-[1.5rem] border border-[var(--border-default)] bg-white/76 px-5 py-4"
              >
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                  <item.icon className="h-4 w-4 text-[var(--accent-secondary)]" />
                  {t(item.titleKey)}
                </div>
                <p className="text-sm leading-7 text-[var(--text-secondary)]">
                  {t(item.descriptionKey)}
                </p>
              </div>
            ))}
          </div>
        </aside>

        <section className="rounded-[2rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.94)] shadow-[var(--glass-shadow-elevated)] backdrop-blur-sm">
          <header className="space-y-5 border-b border-[var(--border-subtle)] p-6 sm:p-8">
            <div className="inline-flex w-fit items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] p-1">
              <Link
                href="/login"
                className={cn(
                  "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "login"
                    ? "bg-white text-[var(--text-primary)] shadow-sm"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                )}
              >
                {t("auth.login.button")}
              </Link>
              <Link
                href="/register"
                className={cn(
                  "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "register"
                    ? "bg-white text-[var(--text-primary)] shadow-sm"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                )}
              >
                {t("auth.register.button")}
              </Link>
            </div>

            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
                {title}
              </h1>
              <p className="text-sm leading-7 text-[var(--text-secondary)]">{description}</p>
            </div>
          </header>

          <div className="space-y-6 p-6 sm:p-8">
            {children}
            <div className="border-t border-[var(--border-subtle)] pt-4 text-sm text-[var(--text-secondary)]">
              {footer}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
