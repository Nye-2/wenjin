import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "问津 Wenjin｜结论有依据，过程可回溯",
  description:
    "面向论文、申报、软著与专利材料的 AI 研究导航系统。从选题调研到成稿交付，把来源、运行轨迹、写作、修订与成果确认放进同一工作空间。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body
        className="font-sans antialiased"
        style={
          {
            "--font-sans":
              '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
            "--font-serif":
              '"Songti SC", "STSong", "Noto Serif SC", "SimSun", Georgia, serif',
            "--font-mono":
              '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
          } as React.CSSProperties
        }
      >
        {children}
      </body>
    </html>
  );
}
