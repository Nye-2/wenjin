"use client";

import { motion } from "framer-motion";
import { LiquidGlassCard } from "@/components/glass/liquid-glass-card";
import { GradientText } from "@/components/glass/gradient-text";
import { FileText, BookOpen, Lightbulb, PenTool, FlaskConical, Send } from "lucide-react";
import { fadeInUp, staggerContainer, defaultTransition, buttonTap } from "@/lib/animations";

export default function HomePage() {
  const features = [
    {
      icon: BookOpen,
      title: "Deep Research",
      description: "Comprehensive literature analysis and research gap identification",
    },
    {
      icon: PenTool,
      title: "Paper Writing",
      description: "End-to-end academic paper generation with proper citations",
    },
    {
      icon: Lightbulb,
      title: "Idea Generation",
      description: "Generate novel research ideas based on existing literature",
    },
    {
      icon: FlaskConical,
      title: "Experiment Design",
      description: "Design rigorous experiments with proper methodology",
    },
  ];

  return (
    <main className="min-h-screen bg-[var(--bg-base)]">
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
              <GradientText>AcademiaGPT</GradientText>
            </h1>
            <p className="mt-6 text-lg leading-8 text-[var(--text-secondary)] max-w-2xl mx-auto">
              Your AI-powered academic research and writing assistant. From literature review to
              paper submission, we help you every step of the way.
            </p>
            <div className="mt-10 flex items-center justify-center gap-4">
              <motion.a
                href="/workspaces"
                className="glass-card px-6 py-3 text-base font-semibold text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] hover:shadow-lg transition-shadow cursor-pointer"
                whileHover={{ scale: 1.02 }}
                whileTap={buttonTap}
              >
                Get Started
              </motion.a>
              <motion.a
                href="#features"
                className="glass-card px-6 py-3 text-base font-semibold text-[var(--text-primary)] hover:bg-[var(--bg-surface)] cursor-pointer"
                whileHover={{ scale: 1.02 }}
                whileTap={buttonTap}
              >
                Learn More
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
              <GradientText variant="subtle">Powerful Features</GradientText>
            </h2>
            <p className="mt-4 text-[var(--text-secondary)]">
              Everything you need for academic research and writing
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
                  <feature.icon className="w-8 h-8 text-academic-primary mb-4" />
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
            <h2 className="text-2xl font-bold mb-4">Ready to write your next paper?</h2>
            <p className="text-[var(--text-secondary)] mb-8 max-w-md mx-auto">
              Create a workspace and start your research journey with AI assistance.
            </p>
            <motion.a
              href="/workspaces"
              className="inline-flex items-center gap-2 px-8 py-4 text-base font-semibold text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] rounded-xl cursor-pointer hover:shadow-lg transition-shadow"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Create Workspace
              <Send className="w-4 h-4" />
            </motion.a>
          </LiquidGlassCard>
        </div>
      </section>
    </main>
  );
}
