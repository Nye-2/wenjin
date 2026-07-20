'use client';

import { Suspense, useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AuthShell } from '@/components/auth/auth-shell';
import { resolvePostAuthRedirect } from '@/lib/auth-redirect';
import { Loader2, UserPlus } from 'lucide-react';

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { register, sendVerificationCode, isLoading, error, clearError, isAuthenticated } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [validationError, setValidationError] = useState('');
  const [codeError, setCodeError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const redirectTo = resolvePostAuthRedirect(searchParams?.get('redirect'));

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      router.push(redirectTo);
    }
  }, [isAuthenticated, redirectTo, router]);

  // Countdown timer
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleSendCode = useCallback(async () => {
    if (!email || countdown > 0) return;

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setCodeError("请输入有效的邮箱地址");
      return;
    }

    setIsSendingCode(true);
    setCodeError('');

    const result = await sendVerificationCode(email, 'register');

    if (result.success) {
      setCountdown(60);
    } else {
      setCodeError(result.message);
    }

    setIsSendingCode(false);
  }, [email, countdown, sendVerificationCode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setValidationError('');

    // Client-side validation
    if (password.length < 8) {
      setValidationError("密码长度至少为8位");
      return;
    }

    if (password !== confirmPassword) {
      setValidationError("两次输入的密码不一致");
      return;
    }

    if (!/^\d{6}$/.test(verificationCode)) {
      setValidationError("请输入验证码");
      return;
    }

    await register(email, password, name || email.split('@')[0], verificationCode);
    // Redirect handled by useEffect watching isAuthenticated
  };

  return (
    <AuthShell
      mode="register"
      title="创建你的问津账户"
      description="从第一份来源开始，建立一条可持续推进的工作路径。"
      footer={(
        <p className="text-center">
          已有账户？{" "}
          <Link
            href="/login"
            className="font-semibold text-[var(--wjn-navy)] hover:text-[var(--wjn-blue)]"
          >
            登录
          </Link>
        </p>
      )}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-4">
          {(error || validationError) && (
            <Alert variant="destructive">
              <AlertDescription>{error || validationError}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-2">
            <Label htmlFor="name">
              姓名 (可选)
            </Label>
            <Input
              id="name"
              type="text"
              placeholder="输入您的姓名"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">
              邮箱 <span className="text-[var(--wjn-error)]">*</span>
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="your@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="verificationCode">
              验证码 <span className="text-[var(--wjn-error)]">*</span>
            </Label>
            <div className="flex gap-2">
              <Input
                id="verificationCode"
                type="text"
                placeholder="请输入验证码"
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                required
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                className="flex-1 font-mono tracking-wider"
              />
              <Button
                type="button"
                variant="outline"
                disabled={countdown > 0 || isSendingCode || !email}
                onClick={handleSendCode}
                className="h-11 shrink-0 px-4"
              >
                {isSendingCode ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : countdown > 0 ? (
                  `${countdown}s`
                ) : (
                  "发送验证码"
                )}
              </Button>
            </div>
            {codeError && (
              <p className="text-xs text-[var(--wjn-error)]">{codeError}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">
              密码 <span className="text-[var(--wjn-error)]">*</span>
            </Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
            />
            <p className="text-xs text-[var(--wjn-text-muted)]">密码长度至少为8位</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">
              确认密码 <span className="text-[var(--wjn-error)]">*</span>
            </Label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
        </div>

        <Button type="submit" className="h-11 w-full text-sm font-semibold" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              创建中...
            </>
          ) : (
            <>
              <UserPlus className="mr-2 h-4 w-4" />
              创建账户
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}
