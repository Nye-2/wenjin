import type { Locale } from "@/stores/locale";

import enMessages from "@/locales/en.json";
import cnMessages from "@/locales/cn.json";

export type Messages = typeof enMessages;

const messages: Record<Locale, Messages> = {
  en: enMessages,
  cn: cnMessages,
};

export function getMessages(locale: Locale): Promise<Messages> {
  return Promise.resolve(messages[locale]);
}

export function getBrowserLocale(): Locale {
  if (typeof window === "undefined") return "en";

  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith("zh") || browserLang.startsWith("cn")) {
    return "cn";
  }
  return "en";
}

export function detectInitialLocale(savedLocale: Locale | null): Locale {
  if (savedLocale) return savedLocale;
  return getBrowserLocale();
}
