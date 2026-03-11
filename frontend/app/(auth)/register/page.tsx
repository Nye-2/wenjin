'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, UserPlus } from 'lucide-react';

export default function RegisterPage() {
  const router = useRouter();
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

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/workspaces');
    }
  }, [isAuthenticated, router]);

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
      setCodeError('Please enter a valid email address');
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
      setValidationError('Password must be at least 8 characters long');
      return;
    }

    if (password !== confirmPassword) {
      setValidationError('Passwords do not match');
      return;
    }

    if (!verificationCode || verificationCode.length < 4) {
      setValidationError('Please enter the verification code');
      return;
    }

    const success = await register(email, password, name || email.split('@')[0], verificationCode);
    if (success) {
      router.push('/workspaces');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-base)] px-4 py-8">
      <Card className="w-full max-w-md bg-[var(--bg-elevated)]/50 border-[var(--border-default)] backdrop-blur-sm">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold text-[var(--text-primary)]">
            Create Account
          </CardTitle>
          <CardDescription className="text-[var(--text-secondary)]">
            Start your academic research journey
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {(error || validationError) && (
              <Alert variant="destructive" className="bg-red-900/50 border-red-800">
                <AlertDescription>{error || validationError}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="name" className="text-slate-200">
                Name (optional)
              </Label>
              <Input
                id="name"
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="bg-slate-900/50 border-slate-600 text-white placeholder:text-slate-500"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email" className="text-slate-200">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="bg-slate-900/50 border-slate-600 text-white placeholder:text-slate-500"
              />
            </div>

            {/* Verification Code */}
            <div className="space-y-2">
              <Label htmlFor="verificationCode" className="text-slate-200">
                Verification Code
              </Label>
              <div className="flex gap-2">
                <Input
                  id="verificationCode"
                  type="text"
                  placeholder="Enter code"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.toUpperCase())}
                  required
                  maxLength={10}
                  className="flex-1 bg-slate-900/50 border-slate-600 text-white placeholder:text-slate-500 font-mono tracking-wider"
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={countdown > 0 || isSendingCode || !email}
                  onClick={handleSendCode}
                  className="shrink-0 border-slate-600 text-slate-200 hover:bg-slate-700"
                >
                  {isSendingCode ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : countdown > 0 ? (
                    `${countdown}s`
                  ) : (
                    'Send Code'
                  )}
                </Button>
              </div>
              {codeError && (
                <p className="text-xs text-red-400">{codeError}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-200">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="bg-slate-900/50 border-slate-600 text-white placeholder:text-slate-500"
              />
              <p className="text-xs text-slate-500">
                Must be at least 8 characters
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword" className="text-slate-200">
                Confirm Password
              </Label>
              <Input
                id="confirmPassword"
                type="password"
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="bg-slate-900/50 border-slate-600 text-white placeholder:text-slate-500"
              />
            </div>
          </CardContent>

          <CardFooter className="flex flex-col space-y-4">
            <Button
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                <>
                  <UserPlus className="mr-2 h-4 w-4" />
                  Create Account
                </>
              )}
            </Button>

            <p className="text-sm text-slate-400 text-center">
              Already have an account?{' '}
              <Link
                href="/login"
                className="text-blue-400 hover:text-blue-300 underline underline-offset-4"
              >
                Sign in
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
