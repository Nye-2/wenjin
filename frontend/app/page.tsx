"use client";

import { motion } from "framer-motion";
import { LiquidGlassCard } from "@/components/glass/liquid-glass-card";
import { GradientText } from "@/components/glass/gradient-text";
import { LanguageSwitcher } from "@/components/ui/language-switcher";
import { FileText, BookOpen, Lightbulb, PenTool, FlaskConical, Send } from "lucide-react";
import { fadeInUp, staggerContainer, defaultTransition, buttonTap } from "@/lib/animations";
import { useI18n } from "@/components/i18n-provider";

export default function HomePage() {
  const { t } = useI18n();

  const features = [
    {
      icon: BookOpen,
      title: t("features.deepResearch.title"),
      description: t("features.deepResearch.description"),
    },
    {
      icon: PenTool,
      title: t("features.paperWriting.title"),
      description: t("features.paperWriting.description"),
    },
    {
      icon: Lightbulb,
      title: t("features.ideaGeneration.title"),
      description: t("features.ideaGeneration.description"),
    },
    {
      icon: FlaskConical,
      title: t("features.experimentDesign.title"),
      description: t("features.experimentDesign.description"),
    },
  ];

  return (
    <main className="min-h-screen bg-[var(--bg-base)]">
      {/* Language Switcher */}
      <div className="fixed top-4 right-4 z-50">
        <LanguageSwitcher />
      </div>

      {/* Hero Section */}
      <section className="relative overflow-hidden px-6 py-24 lg:py-32">
        <div className="mx-auto max-w-6xl text-center">
          <motion.div
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            transition={{ ...defaultTransition, duration: 0.6 }}
          >
            <h1 className="text-5xl font-bold tracking-tight sm:text-6xl lg:text-7xl">
              <GradientText>{t("home.title")}</GradientText>
            </h1>
            <p className="mt-6 text-lg leading-8 text-[var(--text-secondary)] max-w-2xl mx-auto">
              {t("home.subtitle")}
            </p>
            <div className="mt-10 flex items-center justify-center gap-4">
              <motion.a
                href="/workspaces"
                className="px-8 py-4 text-base font-semibold text-white rounded-xl bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] hover:shadow-xl transition-shadow cursor-pointer"
                whileHover={{ scale: 1.02 }}
                whileTap={buttonTap}
              >
                {t("home.getStarted")}
              </motion.a>
              <motion.a
                href="#features"
                className="px-8 py-4 text-base font-semibold text-[var(--accent-primary)] border-2 border-[var(--accent-primary)] rounded-xl hover:bg-[var(--accent-primary)] hover:text-white transition-all cursor-pointer"
                whileHover={{ scale: 1.02 }}
                whileTap={buttonTap}
              >
                {t("home.learnMore")}
              </motion.a>
            </div>
          </motion.div>
        </div>

        {/* Decorative gradient */}
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[var(--accent-primary)]/10 rounded-full blur-3xl" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[var(--accent-secondary)]/10 rounded-full blur-3xl" />
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold tracking-tight">
              <GradientText variant="subtle">{t("home.features.title")}</GradientText>
            </h2>
            <p className="mt-4 text-[var(--text-secondary)]">
              {t("home.features.subtitle")}
            </p>
          </div>

          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
            variants={staggerContainer}
            initial="initial"
            animate="animate"
          >
            {features.map((feature) => (
              <motion.div
                key={feature.title}
                variants={fadeInUp}
                transition={defaultTransition}
              >
                <LiquidGlassCard className="p-6 h-full">
                  <feature.icon className="w-8 h-8 text-[var(--accent-primary)] mb-4" />
                  <h3 className="font-semibold text-lg mb-2">{feature.title}</h3>
                  <p className="text-sm text-[var(--text-secondary)]">{feature.description}</p>
                </LiquidGlassCard>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-4xl">
          <LiquidGlassCard variant="elevated" className="p-12 text-center">
            <FileText className="w-16 h-16 text-[var(--accent-primary)] mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-4">{t("home.cta.title")}</h2>
            <p className="text-[var(--text-secondary)] mb-8 max-w-md mx-auto">
              {t("home.cta.subtitle")}
            </p>
            <motion.a
              href="/workspaces"
              className="inline-flex items-center gap-2 px-8 py-4 text-base font-semibold text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] rounded-xl cursor-pointer hover:shadow-lg transition-shadow"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {t("home.cta.button")}
              <Send className="w-4 h-4" />
            </motion.a>
          </LiquidGlassCard>
        </div>
      </section>
    </main>
  );
}
