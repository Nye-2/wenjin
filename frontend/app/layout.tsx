import type { Metadata } from "next";
import "./globals.css";
import { I18nProvider } from "@/components/i18n-provider";

export const metadata: Metadata = {
  title: "AcademiaGPT - Academic AI Assistant",
  description: "AI-powered academic research and writing assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
