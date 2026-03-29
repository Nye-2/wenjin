"use client";

import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { useLocaleStore, Locale } from "@/stores/locale";
import { getMessages, Messages, getBrowserLocale } from "@/lib/i18n";

interface I18nContextType {
  messages: Messages | null;
  locale: Locale;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextType | null>(null);

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}

interface I18nProviderProps {
  children: ReactNode;
}

export function I18nProvider({ children }: I18nProviderProps) {
  const { locale, setLocale } = useLocaleStore();
  const [messages, setMessages] = useState<Messages | null>(null);
  const initializedRef = useRef(false);

  // Initialize locale from localStorage or browser
  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      const savedLocale = localStorage.getItem("guanlan-locale") || localStorage.getItem("academiagpt-locale");
      if (savedLocale) {
        try {
          const parsed = JSON.parse(savedLocale);
          if (parsed.state?.locale) {
            setLocale(parsed.state.locale as Locale);
          }
        } catch {
          // If parsing fails, detect from browser
          setLocale(getBrowserLocale());
        }
      } else {
        // No saved preference, use browser language
        setLocale(getBrowserLocale());
      }
    }
  }, [setLocale]);

  // Load messages when locale changes
  useEffect(() => {
    getMessages(locale).then(setMessages);
  }, [locale]);

  // Translation function
  const t = (key: string, params?: Record<string, string | number>): string => {
    if (!messages) return key;

    const keys = key.split(".");
    let value: unknown = messages;

    for (const k of keys) {
      if (typeof value === "object" && value !== null && k in value) {
        value = (value as Record<string, unknown>)[k];
      } else {
        return key;
      }
    }

    if (typeof value !== "string") return key;

    // Replace parameters like {name} with actual values
    if (params) {
      return value.replace(/\{(\w+)\}/g, (_, paramKey) => {
        return String(params[paramKey] ?? `{${paramKey}}`);
      });
    }

    return value;
  };

  if (!messages) {
    return (
      <div className="min-h-screen bg-[var(--bg-base)] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <I18nContext.Provider value={{ messages, locale, t }}>
      {children}
    </I18nContext.Provider>
  );
}
