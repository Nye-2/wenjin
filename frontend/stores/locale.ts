import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Locale = "en" | "cn";

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useLocaleStore = create<LocaleState>()(
  persist(
    (set) => ({
      locale: "en",
      setLocale: (locale) => set({ locale }),
    }),
    {
      name: "academiagpt-locale",
    }
  )
);
