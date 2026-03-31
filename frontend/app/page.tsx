"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import {
  ArrowRight,
  BookOpen,
  FileText,
  FlaskConical,
  Code2,
  Lightbulb,
  MessageSquare,
  Layers,
  GitMerge,
  Archive,
  Send,
} from "lucide-react";
import { LiquidGlassCard } from "@/components/glass/liquid-glass-card";
import { Header } from "@/components/layout/header";
import {
  buttonTap,
  defaultTransition,
  fadeInUp,
  staggerContainer,
} from "@/lib/animations";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

type StageTone = "done" | "active" | "queued";

/* ------------------------------------------------------------------ */
/*  Helper components                                                  */
/* ------------------------------------------------------------------ */

function EnterWorkspaceButton({
  label,
  compact = false,
  withIcon = true,
}: {
  label: string;
  compact?: boolean;
  withIcon?: boolean;
}) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    router.push(isAuthenticated ? "/workspaces" : "/login");
  };

  return (
    <motion.a
      href="/workspaces"
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-[var(--brand-navy)] to-[var(--brand-teal)] font-semibold text-white transition-shadow hover:shadow-xl hover:shadow-[var(--brand-navy)]/20",
        compact ? "px-4 py-2.5 text-sm" : "px-7 py-4 text-base"
      )}
      whileHover={{ scale: 1.02 }}
      whileTap={buttonTap}
    >
      <span>{label}</span>
      {withIcon && <Send className="h-4 w-4 shrink-0" />}
    </motion.a>
  );
}

function LearnMoreButton({ label }: { label: string }) {
  return (
    <motion.a
      href="#philosophy"
      className="inline-flex items-center gap-2 rounded-2xl border border-[var(--brand-line)] bg-white/72 px-7 py-4 text-base font-semibold text-[var(--brand-navy)] transition-colors hover:border-[var(--brand-teal)]/40 hover:bg-white"
      whileHover={{ scale: 1.02 }}
      whileTap={buttonTap}
    >
      <span>{label}</span>
      <ArrowRight className="h-4 w-4" />
    </motion.a>
  );
}

function SectionHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent-secondary)]">
        {eyebrow}
      </p>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-relaxed text-[var(--text-secondary)] sm:text-lg">
        {subtitle}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Stage preview card data                                            */
/* ------------------------------------------------------------------ */

const stageToneStyles: Record<
  StageTone,
  { dot: string; badge: string; panel: string }
> = {
  done: {
    dot: "border-[var(--brand-teal)] bg-[var(--brand-teal)]",
    badge:
      "border-[var(--brand-teal)]/25 bg-[var(--brand-teal)]/10 text-[var(--brand-teal)]",
    panel: "bg-white/72",
  },
  active: {
    dot: "border-[var(--brand-brass)] bg-[var(--brand-brass)]",
    badge:
      "border-[var(--brand-brass)]/30 bg-[var(--brand-brass)]/12 text-[var(--brand-brass)]",
    panel: "bg-[rgba(166,124,57,0.08)]",
  },
  queued: {
    dot: "border-[var(--brand-line)] bg-[var(--bg-elevated)]",
    badge:
      "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-muted)]",
    panel: "bg-[rgba(255,255,255,0.52)]",
  },
};

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function HomePage() {
  const { t } = useI18n();

  /* ---- Hero type badges ---- */
  const supportedTypes = [
    t("workspace.types.sci"),
    t("workspace.types.proposal"),
    t("workspace.types.patent"),
    t("workspace.types.thesis"),
  ];

  /* ---- Stage preview ---- */
  const pathStages: Array<{ key: string; tone: StageTone }> = [
    { key: "stage1", tone: "done" },
    { key: "stage2", tone: "active" },
    { key: "stage3", tone: "queued" },
    { key: "stage4", tone: "queued" },
    { key: "stage5", tone: "queued" },
  ];

  /* ---- Section 2: Philosophy cards ---- */
  const philosophyCards = [
    {
      key: "conversation",
      icon: MessageSquare,
      accent: "var(--brand-navy)",
      accentBg: "rgba(31, 66, 99, 0.12)",
    },
    {
      key: "stages",
      icon: Layers,
      accent: "var(--brand-teal)",
      accentBg: "rgba(46, 111, 109, 0.12)",
    },
    {
      key: "singleThread",
      icon: GitMerge,
      accent: "var(--brand-brass)",
      accentBg: "rgba(166, 124, 57, 0.12)",
    },
    {
      key: "artifacts",
      icon: Archive,
      accent: "var(--brand-cyan)",
      accentBg: "rgba(92, 151, 165, 0.14)",
    },
  ] as const;

  /* ---- Section 3: Workspace types ---- */
  const workspaceTypes = [
    {
      key: "thesis",
      icon: BookOpen,
      accent: "var(--brand-cyan)",
      accentBg: "rgba(92, 151, 165, 0.16)",
      borderAccent: "rgba(92, 151, 165, 0.35)",
    },
    {
      key: "sci",
      icon: FileText,
      accent: "var(--brand-navy)",
      accentBg: "rgba(31, 66, 99, 0.14)",
      borderAccent: "rgba(31, 66, 99, 0.30)",
    },
    {
      key: "proposal",
      icon: FlaskConical,
      accent: "var(--brand-teal)",
      accentBg: "rgba(46, 111, 109, 0.14)",
      borderAccent: "rgba(46, 111, 109, 0.30)",
    },
    {
      key: "software_copyright",
      icon: Code2,
      accent: "var(--text-secondary)",
      accentBg: "rgba(120, 135, 139, 0.14)",
      borderAccent: "rgba(120, 135, 139, 0.30)",
    },
    {
      key: "patent",
      icon: Lightbulb,
      accent: "var(--brand-brass)",
      accentBg: "rgba(166, 124, 57, 0.14)",
      borderAccent: "rgba(166, 124, 57, 0.30)",
    },
  ] as const;

  /* ---- Section 4: Workflow steps ---- */
  const workflowSteps = [
    { index: "01", stepKey: "step1" },
    { index: "02", stepKey: "step2" },
    { index: "03", stepKey: "step3" },
    { index: "04", stepKey: "step4" },
    { index: "05", stepKey: "step5" },
  ];

  /* ---- Section 5: Use cases ---- */
  const useCases = [
    { key: "thesis", borderColor: "var(--brand-cyan)" },
    { key: "sci", borderColor: "var(--brand-navy)" },
    { key: "proposal", borderColor: "var(--brand-teal)" },
  ] as const;

  /* ---- Section 6: Stats ---- */
  const statKeys = ["skills", "types", "disciplines", "templates", "models"] as const;

  return (
    <main className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <Header />

      {/* ============================================================ */}
      {/*  SECTION 1 — Hero                                            */}
      {/* ============================================================ */}
      <section className="route-topography relative overflow-hidden px-6 pb-20 pt-28 sm:pt-32 lg:pb-24">
        <div className="route-grid absolute inset-x-8 bottom-6 top-24 rounded-[2rem] opacity-40" />
        <div className="absolute -left-16 top-24 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(31,66,99,0.18),transparent_70%)] blur-3xl" />
        <div className="absolute right-0 top-8 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(46,111,109,0.18),transparent_72%)] blur-3xl" />

        <div className="relative mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)] lg:items-center">
            {/* Left — copy */}
            <motion.div
              variants={fadeInUp}
              initial="initial"
              animate="animate"
              transition={{ ...defaultTransition, duration: 0.6 }}
              className="max-w-3xl"
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white/72 px-4 py-2 text-xs font-semibold uppercase tracking-[0.26em] text-[var(--accent-secondary)]">
                <span className="h-2 w-2 rounded-full bg-[var(--brand-brass)]" />
                {t("nav.productTagline")}
              </div>

              <div className="mt-8">
                <h1 className="font-serif text-6xl font-semibold tracking-tight text-[var(--brand-ink)] sm:text-7xl lg:text-8xl">
                  <span className="gradient-text-shimmer">{t("brand.cn")}</span>
                </h1>
                <p className="mt-3 text-sm uppercase tracking-[0.44em] text-[var(--text-muted)] sm:text-base">
                  {t("brand.en")}
                </p>
              </div>

              <div className="mt-8 space-y-3">
                <p className="font-serif text-2xl text-[var(--text-primary)] sm:text-3xl">
                  {t("brand.motto")}
                </p>
                <p className="max-w-2xl text-lg font-medium leading-relaxed text-[var(--text-primary)] sm:text-xl">
                  {t("brand.tagline")}
                </p>
                <p className="text-sm uppercase tracking-[0.24em] text-[var(--text-muted)] sm:text-base">
                  {t("brand.english")}
                </p>
              </div>

              <p className="mt-8 max-w-2xl text-base leading-8 text-[var(--text-secondary)] sm:text-lg">
                {t("home.subtitle")}
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                {supportedTypes.map((type) => (
                  <span
                    key={type}
                    className="rounded-full border border-[var(--border-default)] bg-white/78 px-4 py-2 text-sm text-[var(--text-secondary)]"
                  >
                    {type}
                  </span>
                ))}
              </div>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <EnterWorkspaceButton label={t("home.getStarted")} />
                <LearnMoreButton label={t("home.learnMore")} />
              </div>
            </motion.div>

            {/* Right — stage preview card */}
            <motion.div
              variants={fadeInUp}
              initial="initial"
              animate="animate"
              transition={{ ...defaultTransition, delay: 0.15, duration: 0.6 }}
            >
              <LiquidGlassCard
                variant="elevated"
                className="route-card relative overflow-hidden rounded-[2rem] p-6 sm:p-8"
              >
                <div className="absolute inset-0 opacity-[0.18]">
                  <div className="absolute inset-y-8 left-10 w-px bg-[linear-gradient(180deg,var(--brand-line),transparent)]" />
                  <div className="absolute right-6 top-6 h-40 w-40 rounded-full bg-[radial-gradient(circle,rgba(46,111,109,0.2),transparent_70%)]" />
                </div>

                <div className="relative">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--accent-secondary)]">
                        {t("home.pathCard.eyebrow")}
                      </p>
                      <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
                        {t("home.pathCard.title")}
                      </h2>
                    </div>
                    <div className="rounded-full border border-[var(--border-default)] bg-white/80 px-3 py-1 text-xs text-[var(--text-secondary)]">
                      {t("home.pathCard.workspaceLabel")}
                    </div>
                  </div>

                  <p className="mt-3 text-sm text-[var(--text-secondary)]">
                    {t("home.pathCard.workspaceValue")}
                  </p>

                  <div className="relative mt-8">
                    <div className="absolute bottom-3 left-[0.6rem] top-3 w-px bg-[linear-gradient(180deg,var(--brand-line),rgba(46,111,109,0.3),var(--brand-line))]" />
                    <div className="space-y-4">
                      {pathStages.map((stage) => {
                        const tone = stageToneStyles[stage.tone];
                        return (
                          <div
                            key={stage.key}
                            className={cn(
                              "relative rounded-2xl border border-white/50 px-4 py-4 pl-10 shadow-[0_8px_24px_rgba(19,34,53,0.05)]",
                              tone.panel
                            )}
                          >
                            <div
                              className={cn(
                                "absolute left-0 top-6 flex h-5 w-5 items-center justify-center rounded-full border-2",
                                tone.dot
                              )}
                            >
                              {stage.tone === "active" && (
                                <div className="h-2.5 w-2.5 rounded-full bg-[var(--brand-paper)]" />
                              )}
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-[var(--text-primary)]">
                                {t(`home.stages.${stage.key}.title`)}
                              </p>
                              <span
                                className={cn(
                                  "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                                  tone.badge
                                )}
                              >
                                {t(`home.status.${stage.tone}`)}
                              </span>
                            </div>
                            <p className="mt-2 text-sm text-[var(--text-secondary)]">
                              {t(`home.stages.${stage.key}.artifact`)}
                            </p>
                            <p className="mt-1 text-xs text-[var(--text-muted)]">
                              {t(`home.stages.${stage.key}.update`)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Next-action panel (no CTA button) */}
                  <div className="mt-6 rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
                      {t("home.pathCard.nextLabel")}
                    </p>
                    <div className="mt-2">
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        {t("home.pathCard.nextAction")}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                        {t("home.pathCard.note")}
                      </p>
                    </div>
                  </div>
                </div>
              </LiquidGlassCard>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 2 — Design Philosophy                               */}
      {/* ============================================================ */}
      <section id="philosophy" className="px-6 py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("home.philosophy.eyebrow")}
            title={t("home.philosophy.title")}
            subtitle={t("home.philosophy.subtitle")}
          />

          <motion.div
            className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-2"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {philosophyCards.map((card) => (
              <motion.div
                key={card.key}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard
                  variant="elevated"
                  className="group h-full rounded-[1.75rem] border-[rgba(31,66,99,0.08)] bg-[rgba(251,248,242,0.84)] p-7 transition-shadow duration-300 hover:shadow-lg hover:shadow-[rgba(31,66,99,0.06)]"
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-2xl transition-transform duration-300 group-hover:scale-105"
                    style={{ background: card.accentBg }}
                  >
                    <card.icon
                      className="h-5 w-5"
                      style={{ color: card.accent }}
                    />
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-[var(--text-primary)]">
                    {t(`home.philosophy.cards.${card.key}.title`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {t(`home.philosophy.cards.${card.key}.description`)}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 3 — Five Workspace Types                            */}
      {/* ============================================================ */}
      <section className="px-6 py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("home.workspaceTypes.eyebrow")}
            title={t("home.workspaceTypes.title")}
            subtitle={t("home.workspaceTypes.subtitle")}
          />

          {/* First row: 3 cards */}
          <motion.div
            className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {workspaceTypes.slice(0, 3).map((ws) => (
              <motion.div
                key={ws.key}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard
                  variant="floating"
                  className="group h-full rounded-[1.75rem] bg-[rgba(251,248,242,0.82)] p-6"
                  style={{ borderColor: ws.borderAccent }}
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-2xl transition-transform duration-300 group-hover:scale-105"
                    style={{ background: ws.accentBg }}
                  >
                    <ws.icon
                      className="h-5 w-5"
                      style={{ color: ws.accent }}
                    />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-[var(--text-primary)]">
                    {t(`workspace.types.${ws.key}`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {t(`home.workspaceTypes.${ws.key}.description`)}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-[var(--text-muted)]">
                    {t(`home.workspaceTypes.${ws.key}.modules`)}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>

          {/* Second row: 2 cards, centered */}
          <motion.div
            className="mt-5 flex flex-col items-stretch justify-center gap-5 md:flex-row md:items-stretch lg:mx-auto lg:max-w-[calc(66.666%+0.625rem)]"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {workspaceTypes.slice(3).map((ws) => (
              <motion.div
                key={ws.key}
                variants={fadeInUp}
                transition={defaultTransition}
                className="flex-1"
              >
                <LiquidGlassCard
                  variant="floating"
                  className="group h-full rounded-[1.75rem] bg-[rgba(251,248,242,0.82)] p-6"
                  style={{ borderColor: ws.borderAccent }}
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-2xl transition-transform duration-300 group-hover:scale-105"
                    style={{ background: ws.accentBg }}
                  >
                    <ws.icon
                      className="h-5 w-5"
                      style={{ color: ws.accent }}
                    />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-[var(--text-primary)]">
                    {t(`workspace.types.${ws.key}`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {t(`home.workspaceTypes.${ws.key}.description`)}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-[var(--text-muted)]">
                    {t(`home.workspaceTypes.${ws.key}.modules`)}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 4 — How It Works (kept as-is)                       */}
      {/* ============================================================ */}
      <section className="px-6 pb-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("brand.en")}
            title={t("home.workflow.title")}
            subtitle={t("home.workflow.subtitle")}
          />

          <div className="relative mt-12">
            <div className="absolute left-6 right-6 top-8 hidden h-px bg-[linear-gradient(90deg,transparent,var(--brand-line),transparent)] lg:block" />
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
              {workflowSteps.map((step) => (
                <motion.div
                  key={step.index}
                  variants={fadeInUp}
                  initial="initial"
                  whileInView="animate"
                  viewport={{ once: true }}
                  transition={defaultTransition}
                >
                  <LiquidGlassCard
                    variant="elevated"
                    className="h-full rounded-[1.75rem] border-[rgba(31,66,99,0.08)] bg-[rgba(251,248,242,0.84)] p-6"
                  >
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--brand-line)] bg-white/88 text-sm font-semibold text-[var(--brand-navy)]">
                      {step.index}
                    </div>
                    <h3 className="mt-5 text-lg font-semibold text-[var(--text-primary)]">
                      {t(`home.workflow.${step.stepKey}.title`)}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {t(`home.workflow.${step.stepKey}.description`)}
                    </p>
                  </LiquidGlassCard>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 5 — Use Cases                                       */}
      {/* ============================================================ */}
      <section className="px-6 py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("home.useCases.eyebrow")}
            title={t("home.useCases.title")}
            subtitle={t("home.useCases.subtitle")}
          />

          <motion.div
            className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-3"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {useCases.map((uc) => (
              <motion.div
                key={uc.key}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard
                  variant="floating"
                  className="h-full rounded-[1.75rem] bg-[rgba(251,248,242,0.82)] p-0"
                >
                  <div className="flex h-full">
                    {/* Colored left border accent */}
                    <div
                      className="w-1 shrink-0 rounded-l-[1.75rem]"
                      style={{ background: uc.borderColor }}
                    />
                    <div className="p-6">
                      <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                        {t(`home.useCases.cases.${uc.key}.title`)}
                      </h3>
                      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                        {t(`home.useCases.cases.${uc.key}.description`)}
                      </p>
                    </div>
                  </div>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 6 — Technical Stats                                 */}
      {/* ============================================================ */}
      <section className="px-6 py-16">
        <div className="mx-auto max-w-7xl">
          <motion.div
            className="flex flex-wrap justify-center gap-4"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {statKeys.map((key) => (
              <motion.span
                key={key}
                variants={fadeInUp}
                transition={defaultTransition}
                className="rounded-full border border-[var(--border-default)] bg-white/78 px-5 py-2.5 text-sm text-[var(--text-secondary)]"
              >
                {t(`home.stats.${key}`)}
              </motion.span>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 7 — CTA + Footer (kept as-is)                      */}
      {/* ============================================================ */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-7xl">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={defaultTransition}
            className="route-card overflow-hidden rounded-[2rem] px-6 py-8 sm:px-10 sm:py-10"
          >
            <div className="grid gap-8 lg:grid-cols-[1.4fr_auto] lg:items-center">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--accent-secondary)]">
                  {t("brand.cn")} / {t("brand.en")}
                </p>
                <h2 className="mt-4 max-w-3xl text-3xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-4xl">
                  {t("home.cta.title")}
                </h2>
                <p className="mt-4 max-w-2xl text-base leading-8 text-[var(--text-secondary)]">
                  {t("home.cta.subtitle")}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <EnterWorkspaceButton label={t("home.cta.button")} />
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-[var(--border-default)]/70 px-6 py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-serif text-base text-[var(--text-primary)]">
              {t("brand.cn")}{" "}
              <span className="ml-1 font-sans text-xs uppercase tracking-[0.24em] text-[var(--text-muted)]">
                {t("brand.en")}
              </span>
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("brand.tagline")}</p>
          </div>
          <p className="text-sm text-[var(--text-muted)]">{t("brand.summary")}</p>
        </div>
      </footer>
    </main>
  );
}
