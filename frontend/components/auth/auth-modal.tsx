"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, Eye, EyeOff } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { useAuthStore } from "@/stores/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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

  const resetForm = useCallback(() => {
    setFormData({ email: "", password: "", confirmPassword: "", name: "", verificationCode: "" });
    setShowPassword(false);
    setPasswordError("");
    setVerificationError("");
    setCountdown(0);
    clearError();
  }, [clearError]);

  useEffect(() => {
    if (isAuthenticated && isOpen) {
      onClose();
      resetForm();
    }
  }, [isAuthenticated, isOpen, onClose, resetForm]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      setMode(initialMode);
      setShowPassword(false);
      setPasswordError("");
      setVerificationError("");
      clearError();
    }
  }, [isOpen, initialMode, clearError]);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown((prev) => prev - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleSendCode = useCallback(async () => {
    if (!formData.email || countdown > 0) return;

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      setVerificationError(t("auth.register.invalidEmail"));
      return;
    }

    setIsSendingCode(true);
    setVerificationError("");

    const result = await sendVerificationCode(formData.email, "register");

    if (result.success) {
      setCountdown(60);
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
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setPasswordError(t("auth.register.passwordMismatch"));
      return;
    }

    if (formData.password.length < 8) {
      setPasswordError(t("auth.register.passwordTooShort"));
      return;
    }

    if (!/^\d{6}$/.test(formData.verificationCode)) {
      setVerificationError("请输入6位数字验证码");
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
  };

  const changeMode = (nextMode: "login" | "register") => {
    setMode(nextMode);
    setShowPassword(false);
    setPasswordError("");
    setVerificationError("");
    clearError();
  };

  const switchMode = () => {
    changeMode(mode === "login" ? "register" : "login");
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.section
            initial={{ y: 12, opacity: 0, scale: 0.985 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 12, opacity: 0, scale: 0.985 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-modal-title"
            className="w-full max-w-lg overflow-hidden rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-[var(--wjn-shadow-md)]"
          >
            <header className="space-y-4 border-b border-[var(--wjn-line)] px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h2 id="auth-modal-title" className="text-2xl font-semibold tracking-tight text-[var(--wjn-text)]">
                    {mode === "login" ? t("auth.login.button") : t("auth.register.button")}
                  </h2>
                  <p className="text-sm text-[var(--wjn-text-secondary)]">
                    {mode === "login" ? t("auth.login.subtitle") : t("auth.register.subtitle")}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="rounded-lg p-2 text-[var(--wjn-text-muted)] transition-colors hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="inline-flex w-fit items-center rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-1">
                <button
                  type="button"
                  onClick={() => changeMode("login")}
                  className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    mode === "login"
                      ? "bg-white text-[var(--wjn-text)] shadow-sm"
                      : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                  }`}
                >
                  {t("auth.login.button")}
                </button>
                <button
                  type="button"
                  onClick={() => changeMode("register")}
                  className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    mode === "register"
                      ? "bg-white text-[var(--wjn-text)] shadow-sm"
                      : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                  }`}
                >
                  {t("auth.register.button")}
                </button>
              </div>
            </header>

            <form onSubmit={handleSubmit} className="space-y-4 px-6 py-5">
              {(error || passwordError || verificationError) && (
                <Alert variant="destructive">
                  <AlertDescription>{passwordError || verificationError || error}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label htmlFor="auth-modal-email">
                  {t("auth.login.email")} <span className="text-[var(--semantic-error)]">*</span>
                </Label>
                <Input
                  id="auth-modal-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={formData.email}
                  onChange={(e) => setFormData((prev) => ({ ...prev, email: e.target.value }))}
                  placeholder={t("auth.login.emailPlaceholder")}
                />
              </div>

              {mode === "register" && (
                <div className="space-y-2">
                  <Label htmlFor="auth-modal-name">{t("auth.register.name")}</Label>
                  <Input
                    id="auth-modal-name"
                    type="text"
                    autoComplete="name"
                    value={formData.name}
                    onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder={t("auth.register.namePlaceholder")}
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="auth-modal-password">
                  {t("auth.login.password")} <span className="text-[var(--semantic-error)]">*</span>
                </Label>
                <div className="relative">
                  <Input
                    id="auth-modal-password"
                    type={showPassword ? "text" : "password"}
                    required
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    value={formData.password}
                    onChange={(e) => setFormData((prev) => ({ ...prev, password: e.target.value }))}
                    placeholder={t("auth.login.passwordPlaceholder")}
                    className="pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-[var(--wjn-text-muted)] transition-colors hover:text-[var(--wjn-text)]"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {mode === "register" && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="auth-modal-confirm-password">
                      {t("auth.register.confirmPassword")} <span className="text-[var(--semantic-error)]">*</span>
                    </Label>
                    <Input
                      id="auth-modal-confirm-password"
                      type="password"
                      required
                      autoComplete="new-password"
                      value={formData.confirmPassword}
                      onChange={(e) => setFormData((prev) => ({ ...prev, confirmPassword: e.target.value }))}
                      placeholder={t("auth.login.passwordPlaceholder")}
                    />
                    <p className="text-xs text-[var(--wjn-text-muted)]">{t("auth.register.passwordTooShort")}</p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="auth-modal-code">
                      {t("auth.register.verificationCode")} <span className="text-[var(--semantic-error)]">*</span>
                    </Label>
                    <div className="flex gap-2">
                      <Input
                        id="auth-modal-code"
                        type="text"
                        required
                        inputMode="numeric"
                        pattern="\d{6}"
                        maxLength={6}
                        value={formData.verificationCode}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            verificationCode: e.target.value.replace(/\D/g, "").slice(0, 6),
                          }))
                        }
                        placeholder="请输入6位数字验证码"
                        className="flex-1 font-mono tracking-wider"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        disabled={countdown > 0 || isSendingCode || !formData.email}
                        onClick={handleSendCode}
                        className="h-11 shrink-0 px-4"
                      >
                        {isSendingCode ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : countdown > 0 ? (
                          `${countdown}s`
                        ) : (
                          t("auth.register.sendCode")
                        )}
                      </Button>
                    </div>
                  </div>
                </>
              )}

              <Button type="submit" disabled={isLoading} className="mt-2 h-11 w-full text-sm font-semibold">
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {mode === "login" ? t("auth.login.signingIn") : t("auth.register.creating")}
                  </>
                ) : mode === "login" ? (
                  t("auth.login.button")
                ) : (
                  t("auth.register.button")
                )}
              </Button>

              <p className="border-t border-[var(--wjn-line)] pt-4 text-center text-sm text-[var(--wjn-text-secondary)]">
                {mode === "login" ? t("auth.login.noAccount") : t("auth.register.hasAccount")}{" "}
                <button
                  type="button"
                  onClick={switchMode}
                  className="font-semibold text-[var(--wjn-navy)] transition-colors hover:text-[var(--wjn-blue)]"
                >
                  {mode === "login" ? t("auth.login.createOne") : t("auth.register.signIn")}
                </button>
              </p>
            </form>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
