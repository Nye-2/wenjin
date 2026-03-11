"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, Eye, EyeOff, Mail } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { useAuthStore } from "@/stores/auth";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: "login" | "register";
}

export function AuthModal({ isOpen, onClose, initialMode = "login" }: AuthModalProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [showPassword, setShowPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [verificationError, setVerificationError] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    name: "",
    verificationCode: "",
  });

  const { login, register, sendVerificationCode, isLoading, error, clearError, isAuthenticated } = useAuthStore();

  // Close modal when authenticated
  useEffect(() => {
    if (isAuthenticated && isOpen) {
      onClose();
      resetForm();
    }
  }, [isAuthenticated, isOpen, onClose]);

  // Close on ESC key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  // Reset mode when modal opens
  useEffect(() => {
    if (isOpen) {
      setMode(initialMode);
    }
  }, [isOpen, initialMode]);

  // Countdown timer
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleSendCode = useCallback(async () => {
    if (!formData.email || countdown > 0) return;

    // Simple email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      setVerificationError(t("auth.register.invalidEmail"));
      return;
    }

    setIsSendingCode(true);
    setVerificationError("");

    const result = await sendVerificationCode(formData.email, "register");

    if (result.success) {
      setCountdown(60); // 60 seconds countdown
    } else {
      setVerificationError(result.message);
    }

    setIsSendingCode(false);
  }, [formData.email, countdown, sendVerificationCode, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setVerificationError("");

    if (mode === "login") {
      const success = await login(formData.email, formData.password);
      if (success) {
        onClose();
        resetForm();
      }
    } else {
      // Validate password match
      if (formData.password !== formData.confirmPassword) {
        setPasswordError(t("auth.register.passwordMismatch"));
        return;
      }
      if (formData.password.length < 8) {
        setPasswordError(t("auth.register.passwordTooShort"));
        return;
      }
      // Validate verification code
      if (!formData.verificationCode || formData.verificationCode.length < 4) {
        setVerificationError(t("auth.register.verificationCodeRequired"));
        return;
      }
      const success = await register(
        formData.email,
        formData.password,
        formData.name || formData.email.split("@")[0],
        formData.verificationCode
      );
      if (success) {
        onClose();
        resetForm();
      }
    }
  };

  const resetForm = useCallback(() => {
    setFormData({ email: "", password: "", confirmPassword: "", name: "", verificationCode: "" });
    setPasswordError("");
    setVerificationError("");
    setCountdown(0);
    clearError();
  }, [clearError]);

  const switchMode = () => {
    setMode(mode === "login" ? "register" : "login");
    setPasswordError("");
    clearError();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[60] p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md"
          >
            <div className="bg-[var(--bg-elevated)] rounded-2xl border border-[var(--border-default)] shadow-2xl overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-[var(--border-default)]">
                <div>
                  <h2 className="text-xl font-bold text-[var(--text-primary)]">
                    {mode === "login" ? t("auth.login.button") : t("auth.register.button")}
                  </h2>
                  <p className="text-sm text-[var(--text-secondary)] mt-1">
                    {mode === "login" ? t("auth.login.subtitle") : t("auth.register.subtitle")}
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg hover:bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="p-6 space-y-4">
                {/* Error Banner */}
                {(error || passwordError) && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-600 text-sm"
                  >
                    {passwordError || error}
                  </motion.div>
                )}

                {/* Email */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                    {t("auth.login.email")}
                  </label>
                  <input
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder={t("auth.login.emailPlaceholder")}
                    className="w-full px-4 py-3 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
                  />
                </div>

                {/* Name field (register only) */}
                {mode === "register" && (
                  <div>
                    <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                      {t("auth.register.name")}
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder={t("auth.register.namePlaceholder")}
                      className="w-full px-4 py-3 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
                    />
                  </div>
                )}

                {/* Password */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                    {t("auth.login.password")}
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      placeholder={t("auth.login.passwordPlaceholder")}
                      className="w-full px-4 py-3 pr-12 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                {/* Confirm Password (register only) */}
                {mode === "register" && (
                  <div>
                    <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                      {t("auth.register.confirmPassword")}
                    </label>
                    <input
                      type="password"
                      required
                      value={formData.confirmPassword}
                      onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                      placeholder={t("auth.login.passwordPlaceholder")}
                      className="w-full px-4 py-3 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
                    />
                  </div>
                )}

                {/* Verification Code (register only) */}
                {mode === "register" && (
                  <div>
                    <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                      {t("auth.register.verificationCode")}
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        required
                        value={formData.verificationCode}
                        onChange={(e) => setFormData({ ...formData, verificationCode: e.target.value.toUpperCase() })}
                        placeholder={t("auth.register.verificationCodePlaceholder")}
                        maxLength={10}
                        className="flex-1 px-4 py-3 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all font-mono tracking-wider"
                      />
                      <button
                        type="button"
                        disabled={countdown > 0 || isSendingCode || !formData.email}
                        onClick={handleSendCode}
                        className="shrink-0 px-4 py-3 rounded-xl bg-[var(--accent-primary)] text-white font-medium whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--accent-primary)]/90 transition-all"
                      >
                        {isSendingCode ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : countdown > 0 ? (
                          `${countdown}s`
                        ) : (
                          t("auth.register.sendCode")
                        )}
                      </button>
                    </div>
                    {verificationError && (
                      <p className="text-xs text-red-500 mt-1">{verificationError}</p>
                    )}
                  </div>
                )}

                {/* Submit Button */}
                <motion.button
                  type="submit"
                  disabled={isLoading}
                  className="w-full px-6 py-3.5 rounded-xl text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#2563EB] hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all font-medium mt-6"
                  whileHover={{ scale: isLoading ? 1 : 1.02 }}
                  whileTap={{ scale: isLoading ? 1 : 0.98 }}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      {mode === "login" ? t("auth.login.signingIn") : t("auth.register.creating")}
                    </>
                  ) : (
                    mode === "login" ? t("auth.login.button") : t("auth.register.button")
                  )}
                </motion.button>

                {/* Switch Mode */}
                <p className="text-center text-sm text-[var(--text-secondary)] mt-4">
                  {mode === "login" ? t("auth.login.noAccount") : t("auth.register.hasAccount")}{" "}
                  <button
                    type="button"
                    onClick={switchMode}
                    className="text-[var(--accent-primary)] hover:underline font-medium"
                  >
                    {mode === "login" ? t("auth.login.createOne") : t("auth.register.signIn")}
                  </button>
                </p>
              </form>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
