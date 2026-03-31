"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import {
  ArrowRight,
  BookOpen,
  FlaskConical,
  Lightbulb,
  PenTool,
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
      {withIcon && <Send className={cn("shrink-0", compact ? "h-4 w-4" : "h-4 w-4")} />}
    </motion.a>
  );
}

function LearnMoreButton({ label }: { label: string }) {
  return (
    <motion.a
      href="#capabilities"
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

export default function HomePage() {
  const { t } = useI18n();

  const taskTypes = [
    {
      icon: BookOpen,
      title: t("features.deepResearch.title"),
      description: t("features.deepResearch.description"),
      badge: t("workspace.types.sci"),
      accent: "var(--brand-navy)",
    },
    {
      icon: FlaskConical,
      title: t("features.paperWriting.title"),
      description: t("features.paperWriting.description"),
      badge: t("workspace.types.proposal"),
      accent: "var(--brand-teal)",
    },
    {
      icon: PenTool,
      title: t("features.ideaGeneration.title"),
      description: t("features.ideaGeneration.description"),
      badge: t("workspace.types.patent"),
      accent: "var(--brand-brass)",
    },
    {
      icon: Lightbulb,
      title: t("features.experimentDesign.title"),
      description: t("features.experimentDesign.description"),
      badge: t("workspace.types.thesis"),
      accent: "var(--brand-cyan)",
    },
  ];

  const pathStages: Array<{
    key: string;
    tone: StageTone;
  }> = [
    { key: "stage1", tone: "done" },
    { key: "stage2", tone: "active" },
    { key: "stage3", tone: "queued" },
    { key: "stage4", tone: "queued" },
    { key: "stage5", tone: "queued" },
  ];

  const workflowSteps = [
    {
      index: "01",
      title: t("home.workflow.step1.title"),
      description: t("home.workflow.step1.description"),
    },
    {
      index: "02",
      title: t("home.workflow.step2.title"),
      description: t("home.workflow.step2.description"),
    },
    {
      index: "03",
      title: t("home.workflow.step3.title"),
      description: t("home.workflow.step3.description"),
    },
    {
      index: "04",
      title: t("home.workflow.step4.title"),
      description: t("home.workflow.step4.description"),
    },
    {
      index: "05",
      title: t("home.workflow.step5.title"),
      description: t("home.workflow.step5.description"),
    },
  ];

  const supportedTypes = [
    t("workspace.types.sci"),
    t("workspace.types.proposal"),
    t("workspace.types.patent"),
    t("workspace.types.thesis"),
  ];

  return (
    <main className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <Header />

      <section className="route-topography relative overflow-hidden px-6 pb-20 pt-28 sm:pt-32 lg:pb-24">
        <div className="route-grid absolute inset-x-8 bottom-6 top-24 rounded-[2rem] opacity-40" />
        <div className="absolute -left-16 top-24 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(31,66,99,0.18),transparent_70%)] blur-3xl" />
        <div className="absolute right-0 top-8 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(46,111,109,0.18),transparent_72%)] blur-3xl" />

        <div className="relative mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)] lg:items-center">
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

                  <div className="mt-6 rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
                      {t("home.pathCard.nextLabel")}
                    </p>
                    <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {t("home.pathCard.nextAction")}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                          {t("home.pathCard.note")}
                        </p>
                      </div>
                      <EnterWorkspaceButton
                        label={t("home.getStarted")}
                        compact
                        withIcon={false}
                      />
                    </div>
                  </div>
                </div>
              </LiquidGlassCard>
            </motion.div>
          </div>
        </div>
      </section>

      <section id="capabilities" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow={t("nav.productTagline")}
            title={t("home.features.title")}
            subtitle={t("home.features.subtitle")}
          />

          <motion.div
            className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {taskTypes.map((task) => (
              <motion.div
                key={task.title}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard
                  variant="floating"
                  className="h-full rounded-[1.75rem] border-[rgba(31,66,99,0.1)] bg-[rgba(251,248,242,0.82)] p-6"
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-2xl"
                    style={{
                      background: `color-mix(in srgb, ${task.accent} 14%, white)`,
                    }}
                  >
                    <task.icon className="h-5 w-5" style={{ color: task.accent }} />
                  </div>
                  <div className="mt-5 flex items-center gap-2">
                    <span className="rounded-full border border-[var(--border-default)] bg-white/78 px-2.5 py-1 text-[11px] text-[var(--text-muted)]">
                      {task.badge}
                    </span>
                  </div>
                  <h3 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">
                    {task.title}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {task.description}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="px-6 pb-24">
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
                      {step.title}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {step.description}
                    </p>
                  </LiquidGlassCard>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </section>

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
