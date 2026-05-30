"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings,
  LogOut,
  FolderOpen,
  ChevronDown,
  LayoutDashboard,
  Shield,
  Coins,
} from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { useAuthStore } from "@/stores/auth";
import { useRouter } from "next/navigation";

export function UserDropdown() {
  const { t } = useI18n();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { user, logout } = useAuthStore();

  // Get display name - prefer name, fallback to email username part
  const displayName = user?.name || user?.email?.split("@")[0] || "User";
  const userInitial = displayName.charAt(0).toUpperCase();
  const credits = typeof user?.credits === "number" ? user.credits : 0;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, []);

  const handleLogout = () => {
    logout();
    setIsOpen(false);
    router.push("/");
  };

  const menuItems = [
    {
      icon: LayoutDashboard,
      label: t("nav.userDashboard"),
      onClick: () => {
        router.push("/dashboard/me");
        setIsOpen(false);
      },
    },
    {
      icon: FolderOpen,
      label: t("nav.workspaces"),
      onClick: () => {
        router.push("/workspaces");
        setIsOpen(false);
      },
    },
    ...(user?.role === "admin"
      ? [
          {
            icon: Shield,
            label: t("nav.adminDashboard"),
            onClick: () => {
              router.push("/dashboard/admin");
              setIsOpen(false);
            },
          },
        ]
      : []),
    {
      icon: Settings,
      label: t("nav.settings"),
      onClick: () => {
        setIsOpen(false);
      },
    },
  ];

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] hover:bg-[var(--bg-surface)] transition-colors"
      >
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--accent-primary)] to-[#2563EB] flex items-center justify-center text-white font-medium text-sm">
          {userInitial}
        </div>
        <span className="text-sm font-medium text-[var(--text-primary)] max-w-[120px] truncate">
          {displayName}
        </span>
        <ChevronDown className={`w-4 h-4 text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-56 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-default)] shadow-xl overflow-hidden z-50"
          >
            {/* User Info */}
            <div className="px-4 py-3 border-b border-[var(--border-default)]">
              <p className="font-medium text-[var(--text-primary)] truncate">{displayName}</p>
              <p className="text-sm text-[var(--text-muted)] truncate">{user?.email}</p>
            </div>

            <div className="border-b border-[var(--border-default)] bg-[var(--bg-surface)]/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--wjn-accent-soft)] text-[var(--accent-primary)]">
                    <Coins className="h-4 w-4" />
                  </span>
                  <span className="text-sm font-medium text-[var(--text-secondary)]">
                    {t("nav.creditBalance")}
                  </span>
                </div>
                <span className="text-lg font-semibold tabular-nums text-[var(--text-primary)]">
                  {credits.toLocaleString()}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  router.push("/dashboard/me");
                  setIsOpen(false);
                }}
                className="mt-3 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-left text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-surface)]"
              >
                {t("nav.creditDashboard")}
              </button>
            </div>

            {/* Menu Items */}
            <div className="py-2">
              {menuItems.map((item, index) => (
                <button
                  key={index}
                  onClick={item.onClick}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[var(--bg-surface)] transition-colors"
                >
                  <item.icon className="w-4 h-4 text-[var(--text-muted)]" />
                  <span className="text-sm text-[var(--text-primary)]">{item.label}</span>
                </button>
              ))}
            </div>

            {/* Logout */}
            <div className="border-t border-[var(--border-default)] py-2">
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-red-500/10 transition-colors"
              >
                <LogOut className="w-4 h-4 text-red-500" />
                <span className="text-sm text-red-500">{t("nav.logout")}</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
