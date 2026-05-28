"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { useAuthStore } from "@/stores/auth";
import { LanguageSwitcher } from "@/components/ui/language-switcher";
import { AuthModal } from "@/components/auth/auth-modal";
import { UserDropdown } from "@/components/auth/user-dropdown";

interface HeaderProps {
  showLanguageSwitcher?: boolean;
}

export function Header({ showLanguageSwitcher = true }: HeaderProps) {
  const { t } = useI18n();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const { isAuthenticated } = useAuthStore();

  const openLogin = useCallback(() => {
    setAuthMode("login");
    setShowAuthModal(true);
  }, []);

  const openRegister = useCallback(() => {
    setAuthMode("register");
    setShowAuthModal(true);
  }, []);

  const closeModal = useCallback(() => {
    setShowAuthModal(false);
  }, []);

  return (
    <>
      <header className="fixed left-0 right-0 top-0 z-50 border-b border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] px-4 py-3 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <Link href="/" className="group flex min-w-0 items-center gap-3">
            <div className="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[var(--wjn-radius)] border border-[var(--wjn-accent-line)] bg-[var(--wjn-accent)] shadow-[var(--wjn-shadow-sm)] transition-transform duration-200 group-hover:-translate-y-0.5">
              <svg className="absolute inset-0 h-full w-full opacity-90" viewBox="0 0 44 44" fill="none" aria-hidden="true">
                <path
                  d="M8 31C14 24 20 22 26 19C31 17 34 14 36 10"
                  stroke="rgba(255,255,255,0.92)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle cx="8" cy="31" r="3" fill="rgba(255,255,255,0.92)" />
                <circle cx="26" cy="19" r="2.4" fill="rgba(255,255,255,0.72)" />
                <circle cx="36" cy="10" r="3.1" fill="var(--wjn-review)" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 leading-none">
                <span className="text-lg font-semibold text-[var(--wjn-text)]">
                  {t("brand.cn")}
                </span>
                <span className="text-[10px] text-[var(--wjn-text-muted)]">
                  {t("brand.en")}
                </span>
              </div>
              <p className="hidden truncate text-xs text-[var(--wjn-text-secondary)] sm:block">
                {t("nav.productTagline")}
              </p>
            </div>
          </Link>

          <div className="hidden rounded-full border border-[var(--wjn-line)] bg-white px-4 py-2 text-xs text-[var(--wjn-text-secondary)] lg:block">
            {t("brand.english")}
          </div>

          <div className="flex items-center gap-3">
            {showLanguageSwitcher && <LanguageSwitcher />}

            {isAuthenticated ? (
              <UserDropdown />
            ) : (
              <div className="flex items-center gap-2">
                <motion.button
                  onClick={openLogin}
                  className="rounded-[var(--wjn-radius)] px-4 py-2 text-sm font-medium text-[var(--wjn-text)] transition-colors hover:bg-white"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {t("auth.login.button")}
                </motion.button>
                <motion.button
                  onClick={openRegister}
                  className="inline-flex items-center gap-2 rounded-[var(--wjn-radius)] bg-[var(--wjn-accent)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--wjn-accent-strong)]"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <span>{t("auth.register.button")}</span>
                  <ArrowRight className="h-4 w-4" />
                </motion.button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Auth Modal */}
      <AuthModal
        isOpen={showAuthModal}
        onClose={closeModal}
        initialMode={authMode}
      />
    </>
  );
}
