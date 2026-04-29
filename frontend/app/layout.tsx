import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { I18nProvider } from "@/components/i18n-provider";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "问津 Wenjin | 研究工作流 AI 工作台",
  description:
    "面向论文、申报、专利与项目写作的 AI 工作台。从选题调研到成稿交付，把来源、推理、写作、修订与成果沉淀放进同一工作空间。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body
        className="font-sans antialiased"
        style={
          {
            "--font-sans":
              '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
            "--font-serif":
              '"Noto Serif SC", "Songti SC", "STSong", "SimSun", serif',
            "--font-display":
              '"Noto Serif SC", "Songti SC", "STSong", "SimSun", serif',
          } as React.CSSProperties
        }
      >
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
