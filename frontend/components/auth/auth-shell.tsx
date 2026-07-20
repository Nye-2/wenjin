"use client";

import Link from "next/link";
import { FileText, SearchCheck, Sparkles } from "lucide-react";
import { ReactNode } from "react";
import { cn } from "@/lib/utils";

type AuthMode = "login" | "register";

interface AuthShellProps {
  mode: AuthMode;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}

const highlights = [
  {
    icon: SearchCheck,
    title: "来源入库",
    description: "把文献、参考与任务背景从一开始就放进同一条线。",
  },
  {
    icon: FileText,
    title: "结构成稿",
    description: "让大纲、章节草稿与修订动作在连续上下文里推进。",
  },
  {
    icon: Sparkles,
    title: "评审交付",
    description: "把审阅记录、交付物与成果沉淀统一收束。",
  },
];

const supportedTypes = ["SCI论文", "项目申报书", "专利申请"];

export function AuthShell({
  mode,
  title,
  description,
  children,
  footer,
}: AuthShellProps) {

  return (
    <div className="wjn-shell-bg relative min-h-screen overflow-hidden px-4 py-8 sm:px-6 lg:px-8">

      <div className="relative mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.08fr_0.92fr]">
        <aside className="hidden rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-raised)] p-10 shadow-[var(--wjn-shadow-md)] backdrop-blur-md lg:flex lg:flex-col">
          <div className="inline-flex w-fit items-center gap-3 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-2 text-sm font-semibold text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)]">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-[7px] text-[17px] font-bold text-[#f5f1e8]"
              style={{ background: "var(--wjn-text)", fontFamily: "var(--wjn-font-serif)" }}
            >
              问
            </div>
            <span>问津</span>
            <span className="text-xs uppercase tracking-[0.24em] text-[var(--wjn-text-muted)]">
              Wenjin
            </span>
          </div>

          <div className="mt-10 space-y-4">
            <h2 className="max-w-xl text-4xl font-bold leading-[1.2] tracking-[0.01em] text-[var(--wjn-text)]" style={{ fontFamily: "var(--wjn-font-serif)" }}>
              向研究深处问津
            </h2>
            <p className="max-w-lg text-base leading-8 text-[var(--wjn-text-secondary)]">
              一个工作空间，连接来源、判断、草稿与成果。
            </p>
          </div>

          <div className="mt-8">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wjn-text-muted)]">
              支持的任务类型
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {supportedTypes.map((type) => (
                <span
                  key={type}
                  className="rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-3 py-1.5 text-sm text-[var(--wjn-text-secondary)]"
                >
                  {type}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-10 space-y-4">
            {highlights.map((item) => (
              <div
                key={item.title}
                className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-5 py-4 shadow-[var(--wjn-shadow-sm)]"
              >
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--wjn-text)]">
                  <item.icon className="h-4 w-4 text-[var(--wjn-blue)]" />
                  {item.title}
                </div>
                <p className="text-sm leading-7 text-[var(--wjn-text-secondary)]">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </aside>

        <section className="rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-[var(--wjn-shadow-lg)]">
          <header className="space-y-5 border-b border-[var(--wjn-line)] p-6 sm:p-8">
            <div className="inline-flex w-fit items-center rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-1">
              <Link
                href="/login"
                className={cn(
                  "rounded-[var(--wjn-radius)] px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "login"
                    ? "bg-[var(--wjn-surface)] text-[var(--wjn-text)] shadow-sm"
                    : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                )}
              >
                登录
              </Link>
              <Link
                href="/register"
                className={cn(
                  "rounded-[var(--wjn-radius)] px-4 py-1.5 text-sm font-medium transition-colors",
                  mode === "register"
                    ? "bg-[var(--wjn-surface)] text-[var(--wjn-text)] shadow-sm"
                    : "text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                )}
              >
                创建账户
              </Link>
            </div>

            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-[-0.025em] text-[var(--wjn-text)]">
                {title}
              </h1>
              <p className="text-sm leading-7 text-[var(--wjn-text-secondary)]">{description}</p>
            </div>
          </header>

          <div className="space-y-6 p-6 sm:p-8">
            {children}
            <div className="border-t border-[var(--wjn-line)] pt-4 text-sm text-[var(--wjn-text-secondary)]">
              {footer}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
