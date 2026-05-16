"use client";

import { Loader2 } from "lucide-react";

import { Header } from "@/components/layout/header";
import { AdminSidebar } from "./components/AdminSidebar";
import { useAdminAuth } from "./hooks/use-admin-auth";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, isAdmin } = useAdminAuth();

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
      </main>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="flex pt-16">
        <AdminSidebar />
        <main className="flex-1 min-w-0 px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
