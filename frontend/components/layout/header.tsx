"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
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
      <header className="fixed top-0 left-0 right-0 z-50 px-4 py-3 bg-[var(--bg-base)]/80 backdrop-blur-lg border-b border-[var(--border-default)]/40">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            {/* Wave mark */}
            <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-[var(--guanlan-deep)] via-[var(--guanlan-wave)] to-[var(--guanlan-crest)] flex items-center justify-center group-hover:shadow-lg group-hover:shadow-[var(--guanlan-crest)]/20 transition-shadow overflow-hidden">
              {/* Subtle wave line inside the mark */}
              <svg className="absolute inset-0 w-full h-full opacity-20" viewBox="0 0 40 40" fill="none">
                <path d="M0 28 Q10 22 20 28 T40 28" stroke="white" strokeWidth="1.5" fill="none" />
                <path d="M0 32 Q10 26 20 32 T40 32" stroke="white" strokeWidth="1" fill="none" opacity="0.5" />
              </svg>
              <span className="relative font-serif text-white font-bold text-base tracking-tight">澜</span>
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-serif text-lg font-semibold text-[var(--text-primary)] tracking-wide">观澜</span>
              <span className="text-[10px] font-sans text-[var(--text-muted)] tracking-[0.15em] uppercase">Guanlan</span>
            </div>
          </Link>

          {/* Right Side */}
          <div className="flex items-center gap-3">
            {showLanguageSwitcher && <LanguageSwitcher />}

            {isAuthenticated ? (
              <UserDropdown />
            ) : (
              <div className="flex items-center gap-2">
                <motion.button
                  onClick={openLogin}
                  className="px-4 py-2 rounded-xl text-[var(--text-primary)] hover:bg-[var(--bg-surface)] transition-colors font-medium text-sm"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {t("auth.login.button")}
                </motion.button>
                <motion.button
                  onClick={openRegister}
                  className="px-4 py-2 rounded-xl text-white bg-gradient-to-r from-[var(--guanlan-wave)] to-[var(--guanlan-crest)] hover:shadow-lg hover:shadow-[var(--guanlan-crest)]/20 transition-shadow font-medium text-sm"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {t("auth.register.button")}
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
