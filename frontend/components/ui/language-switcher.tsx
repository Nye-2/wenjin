"use client";

import { motion } from "framer-motion";
import { useLocaleStore, Locale } from "@/stores/locale";
import { cn } from "@/lib/utils";

const languages: { code: Locale; label: string }[] = [
  { code: "cn", label: "中文" },
  { code: "en", label: "EN" },
];

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useLocaleStore();

  return (
    <div
      className={cn(
        "flex items-center gap-1 p-1 rounded-lg bg-[var(--wjn-surface-subtle)] border border-[var(--wjn-line)]",
        className
      )}
    >
      {languages.map((lang) => (
        <motion.button
          key={lang.code}
          onClick={() => setLocale(lang.code)}
          className={cn(
            "px-3 py-1.5 rounded-md text-sm font-medium transition-all",
            locale === lang.code
              ? "bg-[var(--wjn-navy)] text-white shadow-sm"
              : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)] hover:bg-[var(--bg-muted)]"
          )}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          {lang.label}
        </motion.button>
      ))}
    </div>
  );
}
