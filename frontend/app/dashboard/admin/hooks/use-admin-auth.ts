"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth";

export function useAdminAuth() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuthStore();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    if (user?.role !== "admin") {
      router.push("/dashboard/me");
    }
  }, [isLoading, isAuthenticated, user?.role, router]);

  return {
    user,
    isAuthenticated,
    isLoading,
    isAdmin: user?.role === "admin",
  };
}
