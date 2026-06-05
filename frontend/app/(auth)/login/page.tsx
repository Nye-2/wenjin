'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AuthShell } from '@/components/auth/auth-shell';
import { useI18n } from '@/components/i18n-provider';
import { resolvePostAuthRedirect } from '@/lib/auth-redirect';
import { Eye, EyeOff, Loader2, LogIn } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useI18n();
  const { login, isLoading, error, clearError, isAuthenticated } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const redirectTo = resolvePostAuthRedirect(searchParams?.get('redirect'));

  useEffect(() => {
    if (isAuthenticated) {
      router.push(redirectTo);
    }
  }, [isAuthenticated, redirectTo, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    await login(email, password);
    // Redirect is handled by the useEffect watching isAuthenticated
  };

  return (
    <AuthShell
      mode="login"
      title={t("auth.login.title")}
      description={t("auth.login.subtitle")}
      footer={(
        <p className="text-center">
          {t("auth.login.noAccount")}{" "}
          <Link
            href="/register"
            className="font-semibold text-[var(--wjn-navy)] hover:text-[var(--wjn-blue)]"
          >
            {t("auth.login.createOne")}
          </Link>
        </p>
      )}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-2">
            <Label htmlFor="email">
              {t("auth.login.email")} <span className="text-[var(--semantic-error)]">*</span>
            </Label>
            <Input
              id="email"
              type="email"
              placeholder={t("auth.login.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">
              {t("auth.login.password")} <span className="text-[var(--semantic-error)]">*</span>
            </Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder={t("auth.login.passwordPlaceholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="pr-12"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-[var(--wjn-text-muted)] transition-colors hover:text-[var(--wjn-text)]"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>

        <Button type="submit" className="h-11 w-full text-sm font-semibold" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t("auth.login.signingIn")}
            </>
          ) : (
            <>
              <LogIn className="mr-2 h-4 w-4" />
              {t("auth.login.button")}
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}
