import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

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
          const response = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });

          if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Login failed');
          }

          const data = await response.json();

          // Fetch user info with the new token
          const meResponse = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          let user = {
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
            error: error instanceof Error ? error.message : 'Login failed',
            isLoading: false,
          });
          return false;
        }
      },

      register: async (email: string, password: string, name: string, verificationCode: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch(`${API_BASE}/api/auth/register`, {
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
            const data = await response.json();
            throw new Error(data.detail || 'Registration failed');
          }

          const data = await response.json();

          // Fetch user info with the new token
          const meResponse = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          let user = {
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
            error: error instanceof Error ? error.message : 'Registration failed',
            isLoading: false,
          });
          return false;
        }
      },

      sendVerificationCode: async (email: string, purpose: 'register' | 'reset_password') => {
        try {
          const response = await fetch(`${API_BASE}/api/auth/send-verification-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, purpose }),
          });

          const data = await response.json();

          if (!response.ok) {
            return { success: false, message: data.detail || 'Failed to send code' };
          }

          return {
            success: true,
            message: data.message,
            expireSeconds: data.expire_seconds,
          };
        } catch (error) {
          return {
            success: false,
            message: error instanceof Error ? error.message : 'Failed to send code',
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
          const response = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!response.ok) {
            set({ isAuthenticated: false });
            return false;
          }

          const data = await response.json();
          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
          });

          // Fetch user info
          const meResponse = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
              Authorization: `Bearer ${data.access_token}`,
            },
          });

          if (meResponse.ok) {
            const userData = await meResponse.json();
            set({ user: userData, isAuthenticated: true });
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
      name: 'auth-storage',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
