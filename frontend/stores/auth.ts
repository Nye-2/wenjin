import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { API_BASE_URL } from '@/lib/api-base';

export const AUTH_STORAGE_KEY = 'auth-storage';

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  credits?: number;
  total_credits_earned?: number;
  total_credits_spent?: number;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string, name: string, verificationCode: string) => Promise<boolean>;
  sendVerificationCode: (email: string, purpose: 'register' | 'reset_password') => Promise<{ success: boolean; message: string; expireSeconds?: number }>;
  logout: () => void;
  refreshTokens: () => Promise<boolean>;
  setUser: (user: User) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  clearError: () => void;
}

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }
    if (typeof data?.message === 'string' && data.message.trim()) {
      return data.message;
    }
    if (typeof data?.error?.message === 'string' && data.error.message.trim()) {
      return data.error.message;
    }
  } catch {
    // Ignore JSON parse errors and fall back to generic message.
  }
  return fallback;
}

function normalizeRequestError(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    if (error.message === 'Failed to fetch') {
      return 'Network error: unable to reach API server';
    }
    return error.message;
  }
  return fallback;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });

          if (!response.ok) {
            throw new Error(await parseErrorMessage(response, 'Login failed'));
          }

          const data = await response.json();

          // Fetch user info with the new token
          const meResponse = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          let user: User = {
            id: 'unknown',
            email: email,
            name: email.split('@')[0],
            role: 'user',
          };

          if (meResponse.ok) {
            const userData = await meResponse.json();
            user = {
              id: userData.id,
              email: userData.email,
              name: userData.name || email.split('@')[0],
              role: userData.role,
              credits: userData.credits,
              total_credits_earned: userData.total_credits_earned,
              total_credits_spent: userData.total_credits_spent,
            };
          }

          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            user: user,
            isAuthenticated: true,
            isLoading: false,
          });

          return true;
        } catch (error) {
          set({
            error: normalizeRequestError(error, 'Login failed'),
            isLoading: false,
          });
          return false;
        }
      },

      register: async (email: string, password: string, name: string, verificationCode: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch(`${API_BASE_URL}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email,
              password,
              name: name || undefined,
              verification_code: verificationCode,
            }),
          });

          if (!response.ok) {
            throw new Error(await parseErrorMessage(response, 'Registration failed'));
          }

          const data = await response.json();

          // Fetch user info with the new token
          const meResponse = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          let user: User = {
            id: 'unknown',
            email: email,
            name: name || email.split('@')[0],
            role: 'user',
          };

          if (meResponse.ok) {
            const userData = await meResponse.json();
            user = {
              id: userData.id,
              email: userData.email,
              name: userData.name || name || email.split('@')[0],
              role: userData.role,
              credits: userData.credits,
              total_credits_earned: userData.total_credits_earned,
              total_credits_spent: userData.total_credits_spent,
            };
          }

          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            user: user,
            isAuthenticated: true,
            isLoading: false,
          });

          return true;
        } catch (error) {
          set({
            error: normalizeRequestError(error, 'Registration failed'),
            isLoading: false,
          });
          return false;
        }
      },

      sendVerificationCode: async (email: string, purpose: 'register' | 'reset_password') => {
        try {
          const response = await fetch(`${API_BASE_URL}/auth/send-verification-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, purpose }),
          });

          if (!response.ok) {
            return {
              success: false,
              message: await parseErrorMessage(response, 'Failed to send code'),
            };
          }

          const data = await response.json();

          return {
            success: true,
            message: data.message,
            expireSeconds: data.expire_seconds,
          };
        } catch (error) {
          return {
            success: false,
            message: normalizeRequestError(error, 'Failed to send code'),
          };
        }
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        });
      },

      refreshTokens: async () => {
        const { refreshToken } = get();
        if (!refreshToken) return false;

        try {
          const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!response.ok) {
            set({ isAuthenticated: false });
            return false;
          }

          const data = await response.json();

          // Fetch user info before committing new tokens
          const meResponse = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          if (meResponse.ok) {
            const userData = await meResponse.json();
            set({
              accessToken: data.access_token,
              refreshToken: data.refresh_token,
              user: {
                id: userData.id,
                email: userData.email,
                name: userData.name || userData.email?.split('@')[0] || '',
                role: userData.role,
                credits: userData.credits,
                total_credits_earned: userData.total_credits_earned,
                total_credits_spent: userData.total_credits_spent,
              },
              isAuthenticated: true,
            });
          } else {
            // /auth/me failed but tokens are valid — keep existing user, mark authenticated
            set({
              accessToken: data.access_token,
              refreshToken: data.refresh_token,
              isAuthenticated: true,
            });
          }
          return true;
        } catch {
          set({ isAuthenticated: false });
          return false;
        }
      },

      setUser: (user: User) => set({ user }),
      setTokens: (accessToken: string, refreshToken: string) =>
        set({ accessToken, refreshToken }),
      clearError: () => set({ error: null }),
    }),
    {
      name: AUTH_STORAGE_KEY,
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
