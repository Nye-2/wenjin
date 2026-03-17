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
      <header className="fixed top-0 left-0 right-0 z-50 px-4 py-4 bg-[var(--bg-base)]/80 backdrop-blur-md border-b border-[var(--border-default)]/50">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[var(--accent-primary)] to-[#2563EB] flex items-center justify-center group-hover:shadow-lg transition-shadow">
              <span className="text-white font-bold text-lg">A</span>
            </div>
            <span className="text-xl font-bold text-[var(--text-primary)]">AcademiaGPT</span>
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
                  className="px-4 py-2 rounded-xl text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors font-medium"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {t("auth.login.button")}
                </motion.button>
                <motion.button
                  onClick={openRegister}
                  className="px-4 py-2 rounded-xl text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#2563EB] hover:shadow-lg transition-shadow font-medium"
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
