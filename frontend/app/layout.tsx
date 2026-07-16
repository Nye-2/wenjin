import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import { I18nProvider } from "@/components/i18n-provider";
import { WenjinThemeProvider } from "@/components/wenjin-theme-provider";
import { DEFAULT_WENJIN_THEME, WENJIN_THEME_INIT_SCRIPT } from "@/lib/wenjin-theme";

export const metadata: Metadata = {
  title: "问津 Wenjin | 证据驱动的研究导航系统",
  description:
    "面向论文、申报、软著与专利材料的 AI 研究导航系统。从选题调研到成稿交付，把来源、运行轨迹、写作、修订与成果确认放进同一工作空间。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="zh-CN"
      data-scroll-behavior="smooth"
      data-wjn-theme={DEFAULT_WENJIN_THEME}
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: WENJIN_THEME_INIT_SCRIPT,
          }}
        />
      </head>
      <body
        className="font-sans antialiased"
        style={
          {
            "--font-sans":
              '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
            "--font-mono":
              '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
            "--font-serif":
              '"Noto Serif SC", "Songti SC", "STSong", "SimSun", serif',
            "--font-display":
              '"Noto Serif SC", "Songti SC", "STSong", "SimSun", serif',
          } as React.CSSProperties
        }
      >
        <WenjinThemeProvider>
          <I18nProvider>
            {children}
          </I18nProvider>
        </WenjinThemeProvider>
      </body>
    </html>
  );
}
