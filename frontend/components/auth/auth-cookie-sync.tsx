"use client";

import { useEffect } from "react";

import { syncCurrentAuthCookie, useAuthStore } from "@/stores/auth";

export function AuthCookieSync() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  useEffect(() => {
    syncCurrentAuthCookie();
  }, [isAuthenticated]);

  return null;
}
