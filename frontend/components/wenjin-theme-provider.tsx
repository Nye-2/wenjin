"use client";

import { useEffect, type ReactNode } from "react";

import { useWenjinThemeStore } from "@/stores/wenjin-theme-store";

export function WenjinThemeProvider({ children }: { children: ReactNode }) {
  const theme = useWenjinThemeStore((state) => state.theme);

  useEffect(() => {
    document.documentElement.setAttribute("data-wjn-theme", theme);
  }, [theme]);

  return <>{children}</>;
}
