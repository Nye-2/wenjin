"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { LiquidGlassCard } from "@/components/glass/liquid-glass-card";
import { Header } from "@/components/layout/header";
import {
  BookOpen,
  PenTool,
  Lightbulb,
  FlaskConical,
  Send,
  Waves,
  Search,
  FileText,
} from "lucide-react";
import {
  fadeInUp,
  staggerContainer,
  defaultTransition,
  buttonTap,
} from "@/lib/animations";
import { useI18n } from "@/components/i18n-provider";
import { useAuthStore } from "@/stores/auth";

/* ── Hero Wave SVG ── */
function HeroWaves() {
  return (
    <div className="absolute bottom-0 left-0 right-0 overflow-hidden pointer-events-none">
      {/* Layer 1: deepest, slowest */}
      <svg
        className="relative block w-[200%] h-[120px] wave-line-slow opacity-[0.08]"
        viewBox="0 0 2400 120"
        preserveAspectRatio="none"
      >
        <path
          d="M0,60 C200,20 400,100 600,60 C800,20 1000,100 1200,60 C1400,20 1600,100 1800,60 C2000,20 2200,100 2400,60 L2400,120 L0,120 Z"
          fill="url(#wave-grad-1)"
        />
        <defs>
          <linearGradient id="wave-grad-1" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--guanlan-wave)" />
            <stop offset="50%" stopColor="var(--guanlan-crest)" />
            <stop offset="100%" stopColor="var(--guanlan-wave)" />
          </linearGradient>
        </defs>
      </svg>

      {/* Layer 2: mid, medium speed */}
      <svg
        className="absolute bottom-0 left-0 w-[200%] h-[90px] wave-line opacity-[0.06]"
        viewBox="0 0 2400 90"
        preserveAspectRatio="none"
      >
        <path
          d="M0,45 C150,70 350,20 600,45 C850,70 1050,20 1200,45 C1350,70 1550,20 1800,45 C2050,70 2250,20 2400,45 L2400,90 L0,90 Z"
          fill="var(--guanlan-crest)"
        />
      </svg>

      {/* Layer 3: surface, fastest */}
      <svg
        className="absolute bottom-0 left-0 w-[200%] h-[60px] wave-line opacity-[0.04]"
        style={{ animationDuration: "8s" }}
        viewBox="0 0 2400 60"
        preserveAspectRatio="none"
      >
        <path
          d="M0,30 C100,45 300,15 500,30 C700,45 900,15 1100,30 C1300,45 1500,15 1700,30 C1900,45 2100,15 2400,30 L2400,60 L0,60 Z"
          fill="var(--guanlan-foam)"
        />
      </svg>
    </div>
  );
}

/* ── Decorative Ink Circles ── */
function InkCircles() {
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none">
      {/* Large deep circle — top left */}
      <div className="absolute -top-32 -left-32 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(15,40,71,0.12),transparent_65%)]" />
      {/* Medium crest circle — right */}
      <div className="absolute top-1/3 -right-20 w-[400px] h-[400px] rounded-full bg-[radial-gradient(circle,rgba(59,130,196,0.1),transparent_60%)]" />
      {/* Gold accent — bottom left */}
      <div className="absolute bottom-20 left-1/4 w-[300px] h-[300px] rounded-full bg-[radial-gradient(circle,rgba(196,147,74,0.07),transparent_65%)]" />
      {/* Subtle mist wash — center */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-[radial-gradient(circle,rgba(123,184,224,0.06),transparent_55%)]" />
    </div>
  );
}

/* ── Get Started Button ── */
function GetStartedButton({ showIcon = false }: { showIcon?: boolean }) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { t } = useI18n();

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    router.push(isAuthenticated ? "/workspaces" : "/login");
  };

  return (
    <motion.a
      href="/workspaces"
      onClick={handleClick}
      className="inline-flex items-center gap-2 px-8 py-4 text-base font-semibold text-white rounded-xl bg-gradient-to-r from-[var(--guanlan-wave)] to-[var(--guanlan-crest)] hover:shadow-xl hover:shadow-[var(--guanlan-crest)]/15 transition-shadow cursor-pointer"
      whileHover={{ scale: 1.02 }}
      whileTap={showIcon ? { scale: 0.98 } : buttonTap}
    >
      {t("home.getStarted")}
      {showIcon && <Send className="w-4 h-4" />}
    </motion.a>
  );
}

/* ── Page ── */
export default function HomePage() {
  const { t } = useI18n();

  const features = [
    {
      icon: BookOpen,
      title: t("features.deepResearch.title"),
      description: t("features.deepResearch.description"),
      accent: "var(--guanlan-wave)",
    },
    {
      icon: PenTool,
      title: t("features.paperWriting.title"),
      description: t("features.paperWriting.description"),
      accent: "var(--guanlan-crest)",
    },
    {
      icon: Lightbulb,
      title: t("features.ideaGeneration.title"),
      description: t("features.ideaGeneration.description"),
      accent: "var(--guanlan-gold)",
    },
    {
      icon: FlaskConical,
      title: t("features.experimentDesign.title"),
      description: t("features.experimentDesign.description"),
      accent: "var(--guanlan-foam)",
    },
  ];

  return (
    <main className="min-h-screen bg-[var(--bg-base)]">
      <Header />

      {/* ━━━ Hero Section ━━━ */}
      <section className="relative overflow-hidden px-6 pt-32 pb-40 lg:pt-40 lg:pb-52">
        {/* Background gradient: deep at top → misty at bottom */}
        <div className="absolute inset-0 -z-20 bg-gradient-to-b from-[var(--guanlan-ink)]/[0.03] via-transparent to-[var(--bg-base)]" />

        <InkCircles />

        <div className="mx-auto max-w-5xl text-center relative z-10">
          <motion.div
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            transition={{ ...defaultTransition, duration: 0.7 }}
          >
            {/* Chinese calligraphic title */}
            <h1 className="font-serif text-6xl sm:text-7xl lg:text-8xl font-bold tracking-tight leading-none">
              <span className="bg-gradient-to-br from-[var(--guanlan-deep)] via-[var(--guanlan-wave)] to-[var(--guanlan-crest)] bg-clip-text text-transparent">
                观澜
              </span>
            </h1>

            {/* English subtitle */}
            <motion.p
              className="mt-3 font-display text-lg sm:text-xl text-[var(--guanlan-crest)]/70 italic tracking-wide"
              variants={fadeInUp}
              transition={{ ...defaultTransition, delay: 0.15 }}
            >
              Guanlan
            </motion.p>

            {/* Motto — the soul of the product */}
            <motion.div
              className="mt-8 space-y-2"
              variants={fadeInUp}
              transition={{ ...defaultTransition, delay: 0.3 }}
            >
              <p className="font-serif text-xl sm:text-2xl text-[var(--text-primary)]/80 tracking-[0.08em]">
                观水必观其澜
              </p>
              <p className="text-sm sm:text-base text-[var(--text-secondary)] tracking-wide max-w-lg mx-auto leading-relaxed">
                立潮头处，与智同行
              </p>
              <p className="text-xs text-[var(--text-muted)] italic font-display mt-1">
                To understand the waters, observe where the waves rise highest
              </p>
            </motion.div>

            {/* Decorative divider — wave line */}
            <motion.div
              className="mt-8 flex justify-center"
              variants={fadeInUp}
              transition={{ ...defaultTransition, delay: 0.4 }}
            >
              <svg width="120" height="16" viewBox="0 0 120 16" className="text-[var(--guanlan-crest)]/30">
                <path
                  d="M0,8 C15,2 30,14 45,8 C60,2 75,14 90,8 C105,2 120,14 120,8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  fill="none"
                  strokeLinecap="round"
                />
              </svg>
            </motion.div>

            {/* Description */}
            <motion.p
              className="mt-6 text-base sm:text-lg leading-relaxed text-[var(--text-secondary)] max-w-2xl mx-auto"
              variants={fadeInUp}
              transition={{ ...defaultTransition, delay: 0.5 }}
            >
              {t("home.subtitle")}
            </motion.p>

            {/* CTA Buttons */}
            <motion.div
              className="mt-10 flex items-center justify-center gap-4"
              variants={fadeInUp}
              transition={{ ...defaultTransition, delay: 0.6 }}
            >
              <GetStartedButton />
              <motion.a
                href="#features"
                className="px-8 py-4 text-base font-semibold text-[var(--guanlan-wave)] border-2 border-[var(--guanlan-wave)]/30 rounded-xl hover:bg-[var(--guanlan-wave)]/5 hover:border-[var(--guanlan-wave)]/50 transition-all cursor-pointer"
                whileHover={{ scale: 1.02 }}
                whileTap={buttonTap}
              >
                {t("home.learnMore")}
              </motion.a>
            </motion.div>
          </motion.div>
        </div>

        {/* Animated waves at bottom of hero */}
        <HeroWaves />
      </section>

      {/* ━━━ Features Section ━━━ */}
      <section id="features" className="px-6 py-24 relative">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={defaultTransition}
            >
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--guanlan-crest)]/20 bg-[var(--guanlan-crest)]/5 text-[var(--guanlan-wave)] text-sm font-medium mb-4">
                <Waves className="w-3.5 h-3.5" />
                {t("home.features.title")}
              </div>
              <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
                <span className="gradient-text-subtle">
                  {t("home.features.subtitle")}
                </span>
              </h2>
            </motion.div>
          </div>

          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
            variants={staggerContainer}
            initial="initial"
            whileInView="animate"
            viewport={{ once: true }}
          >
            {features.map((feature) => (
              <motion.div
                key={feature.title}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard className="p-6 h-full group">
                  <div
                    className="w-11 h-11 rounded-xl flex items-center justify-center mb-4 transition-transform group-hover:scale-110"
                    style={{ background: `color-mix(in srgb, ${feature.accent} 12%, transparent)` }}
                  >
                    <feature.icon
                      className="w-5 h-5"
                      style={{ color: feature.accent }}
                    />
                  </div>
                  <h3 className="font-semibold text-lg mb-2 text-[var(--text-primary)]">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                    {feature.description}
                  </p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ━━━ Philosophy Section ━━━ */}
      <section className="px-6 py-24 relative overflow-hidden">
        {/* Subtle background texture */}
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-transparent via-[var(--guanlan-wave)]/[0.02] to-transparent" />

        <div className="mx-auto max-w-4xl">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ ...defaultTransition, duration: 0.6 }}
          >
            <LiquidGlassCard variant="elevated" className="p-10 sm:p-14 text-center relative overflow-hidden">
              {/* Decorative wave lines inside the card */}
              <div className="absolute inset-0 pointer-events-none opacity-[0.03]">
                <svg className="w-full h-full" viewBox="0 0 800 400" preserveAspectRatio="none">
                  <path d="M0,200 C100,160 200,240 300,200 C400,160 500,240 600,200 C700,160 800,240 800,200" stroke="var(--guanlan-wave)" strokeWidth="2" fill="none" />
                  <path d="M0,220 C100,180 200,260 300,220 C400,180 500,260 600,220 C700,180 800,260 800,220" stroke="var(--guanlan-crest)" strokeWidth="1.5" fill="none" />
                  <path d="M0,240 C100,200 200,280 300,240 C400,200 500,280 600,240 C700,200 800,280 800,240" stroke="var(--guanlan-foam)" strokeWidth="1" fill="none" />
                </svg>
              </div>

              <div className="relative">
                {/* Source attribution */}
                <p className="text-xs text-[var(--text-muted)] tracking-widest uppercase font-display mb-6">
                  《孟子 · 尽心上》
                </p>

                {/* The quote */}
                <blockquote className="font-serif text-2xl sm:text-3xl text-[var(--text-primary)] leading-relaxed tracking-[0.06em]">
                  观水有术，必观其澜
                </blockquote>

                {/* Wave divider */}
                <div className="flex justify-center my-6">
                  <div className="w-16 h-px bg-gradient-to-r from-transparent via-[var(--guanlan-gold)] to-transparent" />
                </div>

                {/* Interpretation */}
                <p className="text-base text-[var(--text-secondary)] max-w-lg mx-auto leading-relaxed mb-8">
                  在 AI 浪潮之巅，以传统智慧观照未来。观澜，让学术研究站在智能的潮头。
                </p>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <GetStartedButton showIcon />
                </div>
              </div>
            </LiquidGlassCard>
          </motion.div>
        </div>
      </section>

      {/* ━━━ Footer ━━━ */}
      <footer className="px-6 py-8 border-t border-[var(--border-default)]/50">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-serif text-sm text-[var(--text-secondary)]">观澜</span>
            <span className="text-[var(--text-muted)] text-xs">Guanlan</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            观水必观其澜。立潮头处，与智同行。
          </p>
        </div>
      </footer>
    </main>
  );
}
