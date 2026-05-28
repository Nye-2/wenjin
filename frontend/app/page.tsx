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

function SmartRouteButton({
  label,
  path,
  variant = "primary",
  compact = false,
}: {
  label: string;
  path: string;
  variant?: "primary" | "secondary";
  compact?: boolean;
}) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    router.push(isAuthenticated ? path : "/login");
  };

  return (
    <motion.a
      href={path}
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-[var(--wjn-radius)] font-semibold transition-colors",
        compact ? "px-4 py-2.5 text-sm" : "px-7 py-4 text-base",
        variant === "primary"
          ? "bg-[var(--wjn-accent)] text-white shadow-[var(--wjn-shadow-sm)] hover:bg-[var(--wjn-accent-strong)]"
          : "border border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] text-[var(--wjn-text)] hover:border-[var(--wjn-accent-line)] hover:bg-white",
      )}
      whileHover={{ scale: 1.02 }}
      whileTap={buttonTap}
    >
      <span>{label}</span>
      <ArrowRight className="h-4 w-4 shrink-0" />
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
      <p className="text-xs font-semibold text-[var(--wjn-evidence)]">
        {eyebrow}
      </p>
      <h2 className="mt-4 text-3xl font-semibold text-[var(--wjn-text)] sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-relaxed text-[var(--wjn-text-secondary)] sm:text-lg">
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
    dot: "border-[var(--wjn-evidence)] bg-[var(--wjn-evidence)]",
    badge:
      "border-[var(--wjn-evidence)]/25 bg-[var(--wjn-evidence-soft)] text-[var(--wjn-evidence)]",
    panel: "bg-white/72",
  },
  active: {
    dot: "border-[var(--wjn-review)] bg-[var(--wjn-review)]",
    badge:
      "border-[var(--wjn-review)]/30 bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]",
    panel: "bg-[var(--wjn-review-soft)]",
  },
  queued: {
    dot: "border-[var(--wjn-line-strong)] bg-[var(--wjn-surface)]",
    badge:
      "border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-muted)]",
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
    t("workspace.types.thesis"),
    t("workspace.types.sci"),
    t("workspace.types.proposal"),
    t("workspace.types.patent"),
    t("workspace.types.software_copyright"),
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
      accent: "var(--wjn-accent)",
      accentBg: "var(--wjn-accent-soft)",
    },
    {
      key: "stages",
      icon: Layers,
      accent: "var(--wjn-evidence)",
      accentBg: "var(--wjn-evidence-soft)",
    },
    {
      key: "singleThread",
      icon: GitMerge,
      accent: "var(--wjn-review)",
      accentBg: "var(--wjn-review-soft)",
    },
    {
      key: "artifacts",
      icon: Archive,
      accent: "var(--wjn-text-secondary)",
      accentBg: "var(--wjn-surface-subtle)",
    },
  ] as const;

  /* ---- Section 3: Workspace types ---- */
  const workspaceTypes = [
    {
      key: "thesis",
      icon: BookOpen,
      accent: "var(--wjn-evidence)",
      accentBg: "var(--wjn-evidence-soft)",
      borderAccent: "var(--wjn-accent-line)",
    },
    {
      key: "sci",
      icon: FileText,
      accent: "var(--wjn-accent)",
      accentBg: "var(--wjn-accent-soft)",
      borderAccent: "var(--wjn-accent-line)",
    },
    {
      key: "proposal",
      icon: FlaskConical,
      accent: "var(--wjn-evidence)",
      accentBg: "var(--wjn-evidence-soft)",
      borderAccent: "var(--wjn-line-strong)",
    },
    {
      key: "software_copyright",
      icon: Code2,
      accent: "var(--wjn-text-secondary)",
      accentBg: "var(--wjn-surface-subtle)",
      borderAccent: "var(--wjn-line-strong)",
    },
    {
      key: "patent",
      icon: Lightbulb,
      accent: "var(--wjn-review)",
      accentBg: "var(--wjn-review-soft)",
      borderAccent: "var(--wjn-line-strong)",
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
    { key: "thesis", borderColor: "var(--wjn-evidence)" },
    { key: "sci", borderColor: "var(--wjn-accent)" },
    { key: "proposal", borderColor: "var(--wjn-review)" },
  ] as const;

  /* ---- Section 6: Stats ---- */
  const statKeys = ["skills", "types", "disciplines", "templates", "models"] as const;

  return (
    <main className="wjn-shell-bg min-h-screen text-[var(--wjn-text)]">
      <Header />

      {/* ============================================================ */}
      {/*  SECTION 1 — Hero                                            */}
      {/* ============================================================ */}
      <section className="relative overflow-hidden px-6 pb-20 pt-28 sm:pt-32 lg:pb-24">
        <div className="route-grid pointer-events-none absolute inset-x-8 bottom-6 top-24 rounded-[var(--wjn-radius-lg)] opacity-35" />

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
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] px-4 py-2 text-xs font-semibold text-[var(--wjn-evidence)]">
                <span className="h-2 w-2 rounded-full bg-[var(--wjn-review)]" />
                {t("home.heroBadge")}
              </div>

              <div className="mt-8">
                <h1 className="text-6xl font-semibold text-[var(--wjn-text)] sm:text-7xl lg:text-8xl">
                  <span>{t("brand.cn")}</span>
                </h1>
                <p className="mt-3 text-sm text-[var(--wjn-text-muted)] sm:text-base">
                  {t("brand.en")}
                </p>
              </div>

              <div className="mt-8 space-y-3">
                <p className="text-2xl font-semibold text-[var(--wjn-text)] sm:text-3xl">
                  {t("brand.motto")}
                </p>
                <p className="max-w-2xl text-lg font-medium leading-relaxed text-[var(--wjn-text)] sm:text-xl">
                  {t("brand.tagline")}
                </p>
                <p className="text-sm text-[var(--wjn-text-muted)] sm:text-base">
                  {t("brand.english")}
                </p>
              </div>

              <p className="mt-8 max-w-2xl text-base leading-8 text-[var(--wjn-text-secondary)] sm:text-lg">
                {t("home.subtitle")}
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                {supportedTypes.map((type) => (
                  <span
                    key={type}
                    className="rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] px-4 py-2 text-sm text-[var(--wjn-text-secondary)]"
                  >
                    {type}
                  </span>
                ))}
              </div>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <SmartRouteButton label={t("home.getStarted")} path="/workspaces" />
                <SmartRouteButton label={t("home.openPrism")} path="/workspaces" variant="secondary" />
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
                className="wjn-hairline-panel relative overflow-hidden rounded-[var(--wjn-radius-lg)] p-6 sm:p-8"
              >
                <div className="absolute inset-y-8 left-10 w-px bg-[var(--wjn-line)]" />

                <div className="relative">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold text-[var(--wjn-evidence)]">
                        {t("home.pathCard.eyebrow")}
                      </p>
                      <h2 className="mt-3 text-2xl font-semibold text-[var(--wjn-text)]">
                        {t("home.pathCard.title")}
                      </h2>
                    </div>
                    <div className="rounded-full border border-[var(--wjn-line)] bg-white px-3 py-1 text-xs text-[var(--wjn-text-secondary)]">
                      {t("home.pathCard.workspaceLabel")}
                    </div>
                  </div>

                  <p className="mt-3 text-sm text-[var(--wjn-text-secondary)]">
                    {t("home.pathCard.workspaceValue")}
                  </p>

                  <div className="relative mt-8">
                    <div className="absolute bottom-3 left-[0.6rem] top-3 w-px bg-[var(--wjn-line)]" />
                    <div className="space-y-4">
                      {pathStages.map((stage) => {
                        const tone = stageToneStyles[stage.tone];
                        return (
                          <div
                            key={stage.key}
                            className={cn(
                              "relative rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] px-4 py-4 pl-10 shadow-[var(--wjn-shadow-sm)]",
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
                                <div className="h-2.5 w-2.5 rounded-full bg-white" />
                              )}
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-[var(--wjn-text)]">
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
                            <p className="mt-2 text-sm text-[var(--wjn-text-secondary)]">
                              {t(`home.stages.${stage.key}.artifact`)}
                            </p>
                            <p className="mt-1 text-xs text-[var(--wjn-text-muted)]">
                              {t(`home.stages.${stage.key}.update`)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Next-action panel (no CTA button) */}
                  <div className="mt-6 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white p-4">
                    <p className="text-xs font-semibold text-[var(--wjn-text-muted)]">
                      {t("home.pathCard.nextLabel")}
                    </p>
                    <div className="mt-2">
                      <p className="text-sm font-medium text-[var(--wjn-text)]">
                        {t("home.pathCard.nextAction")}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[var(--wjn-text-secondary)]">
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
                  className="group h-full rounded-[var(--wjn-radius)] border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] p-7 transition-shadow duration-300 hover:shadow-[var(--wjn-shadow-md)]"
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-[var(--wjn-radius)] transition-transform duration-300 group-hover:scale-105"
                    style={{ background: card.accentBg }}
                  >
                    <card.icon
                      className="h-5 w-5"
                      style={{ color: card.accent }}
                    />
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-[var(--wjn-text)]">
                    {t(`home.philosophy.cards.${card.key}.title`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                    {t(`home.philosophy.cards.${card.key}.description`)}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  SECTION 2.5 — Workspace / Prism                             */}
      {/* ============================================================ */}
      <section className="px-6 py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("home.modes.eyebrow")}
            title={t("home.modes.title")}
            subtitle=""
          />

          <div className="mt-14 space-y-5">
            {/* ── Workspace ── */}
            <motion.div
              variants={fadeInUp}
              initial="initial"
              whileInView="animate"
              viewport={{ once: true }}
              transition={defaultTransition}
            >
              <div className="wjn-hairline-panel overflow-hidden rounded-[var(--wjn-radius-lg)] px-6 py-8 sm:px-10 sm:py-10">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                  <div className="max-w-2xl">
                    <div className="flex items-center gap-3">
                      <span className="rounded-full border border-[var(--wjn-evidence)]/25 bg-[var(--wjn-evidence-soft)] px-3 py-1 text-xs font-semibold text-[var(--wjn-evidence)]">
                        {t("home.modes.writing.badge")}
                      </span>
                      <span className="text-sm font-medium text-[var(--wjn-text-muted)]">
                        {t("home.modes.writing.product")}
                      </span>
                    </div>
                    <h3 className="mt-5 text-2xl font-semibold text-[var(--wjn-text)] sm:text-3xl">
                      {t("home.modes.writing.tagline")}
                    </h3>
                    <p className="mt-4 text-base leading-8 text-[var(--wjn-text-secondary)]">
                      {t("home.modes.writing.description")}
                    </p>
                    <p className="mt-5 text-sm font-medium text-[var(--wjn-text-muted)]">
                      {t("home.modes.writing.keywords")}
                    </p>
                  </div>
                  <div className="shrink-0">
                    <SmartRouteButton label={t("home.getStarted")} path="/workspaces" />
                  </div>
                </div>
              </div>
            </motion.div>

            {/* ── Prism ── */}
            <motion.div
              variants={fadeInUp}
              initial="initial"
              whileInView="animate"
              viewport={{ once: true }}
              transition={defaultTransition}
            >
              <div className="wjn-hairline-panel overflow-hidden rounded-[var(--wjn-radius-lg)] px-6 py-8 sm:px-10 sm:py-10">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                  <div className="max-w-2xl">
                    <div className="flex items-center gap-3">
                      <span className="rounded-full border border-[var(--wjn-review)]/30 bg-[var(--wjn-review-soft)] px-3 py-1 text-xs font-semibold text-[var(--wjn-review)]">
                        {t("home.modes.rewriting.badge")}
                      </span>
                      <span className="text-sm font-medium text-[var(--wjn-text-muted)]">
                        {t("home.modes.rewriting.product")}
                      </span>
                    </div>
                    <h3 className="mt-5 text-2xl font-semibold text-[var(--wjn-text)] sm:text-3xl">
                      {t("home.modes.rewriting.tagline")}
                    </h3>
                    <p className="mt-4 text-base leading-8 text-[var(--wjn-text-secondary)]">
                      {t("home.modes.rewriting.description")}
                    </p>
                    <p className="mt-5 text-sm font-medium text-[var(--wjn-text-muted)]">
                      {t("home.modes.rewriting.keywords")}
                    </p>
                  </div>
                  <div className="shrink-0">
                    <SmartRouteButton label={t("home.openPrism")} path="/workspaces" variant="secondary" />
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
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
                  className="group h-full rounded-[var(--wjn-radius)] bg-[var(--wjn-surface-raised)] p-6"
                  style={{ borderColor: ws.borderAccent }}
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-[var(--wjn-radius)] transition-transform duration-300 group-hover:scale-105"
                    style={{ background: ws.accentBg }}
                  >
                    <ws.icon
                      className="h-5 w-5"
                      style={{ color: ws.accent }}
                    />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-[var(--wjn-text)]">
                    {t(`workspace.types.${ws.key}`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                    {t(`home.workspaceTypes.${ws.key}.description`)}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-[var(--wjn-text-muted)]">
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
                  className="group h-full rounded-[var(--wjn-radius)] bg-[var(--wjn-surface-raised)] p-6"
                  style={{ borderColor: ws.borderAccent }}
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-[var(--wjn-radius)] transition-transform duration-300 group-hover:scale-105"
                    style={{ background: ws.accentBg }}
                  >
                    <ws.icon
                      className="h-5 w-5"
                      style={{ color: ws.accent }}
                    />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-[var(--wjn-text)]">
                    {t(`workspace.types.${ws.key}`)}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                    {t(`home.workspaceTypes.${ws.key}.description`)}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-[var(--wjn-text-muted)]">
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
            <div className="absolute left-6 right-6 top-8 hidden h-px bg-[var(--wjn-line)] lg:block" />
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
                    className="h-full rounded-[var(--wjn-radius)] border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] p-6"
                  >
                    <div className="flex h-12 w-12 items-center justify-center rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white text-sm font-semibold text-[var(--wjn-accent)]">
                      {step.index}
                    </div>
                    <h3 className="mt-5 text-lg font-semibold text-[var(--wjn-text)]">
                      {t(`home.workflow.${step.stepKey}.title`)}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-[var(--wjn-text-secondary)]">
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
                  className="h-full rounded-[var(--wjn-radius)] bg-[var(--wjn-surface-raised)] p-0"
                >
                  <div className="flex h-full">
                    <div
                      className="w-1 shrink-0 rounded-l-[var(--wjn-radius)]"
                      style={{ background: uc.borderColor }}
                    />
                    <div className="p-6">
                      <h3 className="text-lg font-semibold text-[var(--wjn-text)]">
                        {t(`home.useCases.cases.${uc.key}.title`)}
                      </h3>
                      <p className="mt-3 text-sm leading-7 text-[var(--wjn-text-secondary)]">
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
                className="rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] px-5 py-2.5 text-sm text-[var(--wjn-text-secondary)]"
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
            className="wjn-hairline-panel overflow-hidden rounded-[var(--wjn-radius-lg)] px-6 py-8 sm:px-10 sm:py-10"
          >
            <div className="grid gap-8 lg:grid-cols-[1.4fr_auto] lg:items-center">
              <div>
                <p className="text-xs font-semibold text-[var(--wjn-evidence)]">
                  {t("brand.cn")} / {t("brand.en")}
                </p>
                <h2 className="mt-4 max-w-3xl text-3xl font-semibold text-[var(--wjn-text)] sm:text-4xl">
                  {t("home.cta.title")}
                </h2>
                <p className="mt-4 max-w-2xl text-base leading-8 text-[var(--wjn-text-secondary)]">
                  {t("home.cta.subtitle")}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <SmartRouteButton label={t("home.cta.button")} path="/workspaces" />
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-[var(--wjn-line)] px-6 py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-base font-semibold text-[var(--wjn-text)]">
              {t("brand.cn")}{" "}
              <span className="ml-1 text-xs text-[var(--wjn-text-muted)]">
                {t("brand.en")}
              </span>
            </p>
            <p className="mt-1 text-sm text-[var(--wjn-text-secondary)]">{t("brand.tagline")}</p>
          </div>
          <p className="text-sm text-[var(--wjn-text-muted)]">{t("brand.summary")}</p>
        </div>
      </footer>
    </main>
  );
}
