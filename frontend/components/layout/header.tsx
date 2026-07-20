"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { AuthModal } from "@/components/auth/auth-modal";
import { UserDropdown } from "@/components/auth/user-dropdown";

export function Header() {
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
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[7px] text-[17px] font-bold text-[#f5f1e8] shadow-[var(--wjn-shadow-sm)] transition-transform duration-150 ease-[var(--wjn-ease-standard)] group-hover:-translate-y-px"
              style={{ background: "var(--wjn-text)", fontFamily: "var(--wjn-font-serif)" }}
            >
              问
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 leading-none">
                <span className="text-lg font-semibold tracking-[-0.01em] text-[var(--wjn-text)]">
                  问津
                </span>
                <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--wjn-text-muted)]">
                  Wenjin
                </span>
              </div>
              <p className="hidden truncate text-xs text-[var(--wjn-text-secondary)] sm:block">
                结论有依据，过程可回溯
              </p>
            </div>
          </Link>

          <div className="hidden rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-2 text-xs font-medium text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] lg:block">
            Evidence visible. Process traceable.
          </div>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <UserDropdown />
            ) : (
              <div className="flex items-center gap-2">
                <motion.button
                  onClick={openLogin}
                  className="rounded-[var(--wjn-radius-md)] px-4 py-2 text-sm font-medium text-[var(--wjn-text)] transition-colors hover:bg-[rgba(28,36,32,0.05)]"
                  whileHover={{ y: -1 }}
                  whileTap={{ y: 0 }}
                >
                  登录
                </motion.button>
                <motion.button
                  onClick={openRegister}
                  className="inline-flex items-center gap-2 rounded-[var(--wjn-radius-md)] bg-[var(--wjn-navy)] px-4 py-2 text-sm font-medium text-white shadow-[0_8px_20px_rgba(28,36,32,0.16)] transition-colors hover:bg-[var(--wjn-blue-strong)]"
                  whileHover={{ y: -1 }}
                  whileTap={{ y: 0 }}
                >
                  <span>创建账户</span>
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
