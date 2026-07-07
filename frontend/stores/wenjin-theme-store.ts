import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import {
  DEFAULT_WENJIN_THEME,
  type WenjinTheme,
  isWenjinTheme,
  WENJIN_THEME_STORAGE_KEY,
} from "@/lib/wenjin-theme";

interface WenjinThemeState {
  theme: WenjinTheme;
  setTheme: (theme: WenjinTheme) => void;
  toggleTheme: () => void;
}

export const useWenjinThemeStore = create<WenjinThemeState>()(
  persist(
    (set) => ({
      theme: DEFAULT_WENJIN_THEME,
      setTheme(theme) {
        set({ theme });
      },
      toggleTheme() {
        set((state) => ({
          theme: state.theme === "graphite" ? "mineral" : "graphite",
        }));
      },
    }),
    {
      name: WENJIN_THEME_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ theme: state.theme }),
      merge: (persisted, current) => {
        const persistedState =
          persisted && typeof persisted === "object"
            ? (persisted as Partial<WenjinThemeState>)
            : {};
        return {
          ...current,
          theme: isWenjinTheme(persistedState.theme)
            ? persistedState.theme
            : current.theme,
        };
      },
    },
  ),
);
