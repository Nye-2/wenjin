"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Eye,
  FileText,
  FlaskConical,
  Footprints,
  Landmark,
  ScrollText,
  ShieldCheck,
  Sigma,
  Stamp,
  Timer,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { AuthModal } from "@/components/auth/auth-modal";
import { UserDropdown } from "@/components/auth/user-dropdown";
import { useAuthStore } from "@/stores/auth";
import { WORKSPACE_TYPES, type WorkspaceType } from "@/lib/workspace-types";
import LandingTheater from "@/components/landing-theater";

type AuthMode = "login" | "register";

const serif = "var(--wjn-font-serif)";
const PAPER = "var(--wjn-bg-base)";
const PAPER_DEEP = "var(--wjn-bg-rail)";
const SURFACE = "var(--wjn-surface)";
const INK = "var(--wjn-text)";
const INK_SOFT = "var(--wjn-text-secondary)";
const INK_FAINT = "var(--wjn-text-muted)";
const LINE = "var(--wjn-line)";
const ACCENT = "var(--wjn-blue)";
const ACCENT_SOFT = "var(--wjn-accent-soft)";
const BRASS = "var(--wjn-review)";

const QUICK_START_ORDER: WorkspaceType[] = [...WORKSPACE_TYPES];

const QUICK_START_LABELS: Record<WorkspaceType, string> = {
  sci: "SCI",
  thesis: "学位论文",
  proposal: "项目书",
  software_copyright: "软著",
  math_modeling: "数学建模",
  patent: "专利",
};

function quickStartHref(type: WorkspaceType): string {
  return `/workspaces?create=${type}`;
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-px w-8" style={{ background: BRASS }} />
      <span className="text-[11px] font-semibold tracking-[0.32em]" style={{ color: BRASS }}>
        {children}
      </span>
    </div>
  );
}

function Seal() {
  return (
    <div
      className="flex h-8 w-8 items-center justify-center rounded-[6px] text-[15px] font-bold text-[#f5f1e8]"
      style={{ background: INK, fontFamily: serif }}
    >
      问
    </div>
  );
}

function QuickStartMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-haspopup="menu"
        onClick={() => setIsOpen((current) => !current)}
        className="inline-flex h-9 items-center justify-center gap-1 whitespace-nowrap rounded-full border px-4 text-[13px] font-medium transition-colors hover:bg-[rgba(28,36,32,0.04)]"
        style={{ borderColor: LINE, color: INK }}
      >
        快速开始
        <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" style={{ color: INK_FAINT }} />
      </button>

      {isOpen ? (
        <div
          role="menu"
          className="absolute right-0 top-12 z-50 w-52 rounded-[var(--wjn-radius-xl)] border p-2"
          style={{ borderColor: LINE, background: SURFACE, boxShadow: "var(--wjn-shadow-md)" }}
        >
          {QUICK_START_ORDER.map((type) => (
            <Link
              key={type}
              href={quickStartHref(type)}
              className="flex min-h-10 items-center rounded-[var(--wjn-radius)] px-3 text-[13px] font-medium transition-colors hover:bg-[var(--wjn-surface-subtle)]"
              style={{ color: INK }}
            >
              {QUICK_START_LABELS[type]}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LandingNav({ onAuth }: { onAuth: (mode: AuthMode) => void }) {
  const { isAuthenticated } = useAuthStore();

  return (
    <header className="relative z-10 mx-auto flex h-[68px] max-w-[1200px] items-center justify-between px-8">
      <div className="flex items-center gap-3">
        <Seal />
        <div className="leading-none">
          <div className="text-[15px] font-semibold tracking-[0.02em]" style={{ color: INK, fontFamily: serif }}>
            问津
          </div>
          <div className="mt-[3px] text-[9.5px] font-medium tracking-[0.28em]" style={{ color: INK_FAINT }}>
            WENJIN
          </div>
        </div>
      </div>
      <nav className="hidden items-center gap-8 text-[13px] md:flex" style={{ color: INK_SOFT }}>
        <Link href="/pricing" className="transition-colors hover:text-[var(--wjn-text)]">
          定价
        </Link>
        <Link href="/docs" className="transition-colors hover:text-[var(--wjn-text)]">
          文档
        </Link>
      </nav>
      <div className="flex items-center gap-3">
        <QuickStartMenu />
        {isAuthenticated ? (
          <>
            <Link
              href="/workspaces"
              className="flex h-9 items-center gap-1.5 rounded-full px-4 text-[13px] font-medium text-[#f5f1e8] transition-transform hover:-translate-y-px"
              style={{ background: INK }}
            >
              进入工作台
              <ArrowRight size={14} strokeWidth={2.2} />
            </Link>
            <UserDropdown />
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onAuth("login")}
              className="text-[13px]"
              style={{ color: INK_SOFT }}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => onAuth("register")}
              className="flex h-9 items-center gap-1.5 rounded-full px-4 text-[13px] font-medium text-[#f5f1e8] transition-transform hover:-translate-y-px"
              style={{ background: INK }}
            >
              创建账户
              <ArrowRight size={14} strokeWidth={2.2} />
            </button>
          </>
        )}
      </div>
    </header>
  );
}

function HeroCopy({ onStart }: { onStart: () => void }) {
  return (
    <div className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[92px]">
      <Eyebrow>有据可查的研究执行环境</Eyebrow>
      <h1
        className="mt-7 text-[76px] font-bold leading-[1.08] tracking-[0.01em]"
        style={{ color: INK, fontFamily: serif }}
      >
        向研究深处，
        <br />
        <span style={{ color: ACCENT }}>问津。</span>
      </h1>
      <p className="mt-4 text-[15px] italic tracking-[0.04em]" style={{ color: INK_FAINT, fontFamily: "Georgia, serif" }}>
        Ask where the river deepens — evidence visible, process traceable.
      </p>
      <p className="mt-8 max-w-[520px] text-[15.5px] leading-[1.9]" style={{ color: INK_SOFT }}>
        不是聊天框，也不是模板库。从一个研究想法开始，AI 研究团队在你的工作空间里持续跑链路：
        组织文献、设计实验、留下依据，把关键判断留给你确认。
      </p>
      <div className="mt-10 flex items-center gap-4">
        <button
          type="button"
          onClick={onStart}
          className="group flex h-12 items-center gap-2.5 rounded-full px-7 text-[14.5px] font-medium text-[#f5f1e8] transition-all hover:-translate-y-0.5"
          style={{ background: ACCENT, boxShadow: "0 10px 30px rgba(20, 84, 74, 0.28)" }}
        >
          开始一个研究任务
          <ArrowRight size={16} strokeWidth={2.2} className="transition-transform group-hover:translate-x-0.5" />
        </button>
        <a
          href="#demo"
          className="flex h-12 items-center gap-2 rounded-full border px-6 text-[14px] transition-colors hover:bg-[rgba(28,36,32,0.04)]"
          style={{ borderColor: LINE, color: INK }}
        >
          <Eye size={15} style={{ color: ACCENT }} />
          看看它怎么做研究
        </a>
      </div>
      <div className="mt-16 flex items-center gap-7 text-[12px]" style={{ color: INK_FAINT }}>
        {(
          [
            [ScrollText, "SCI 论文"],
            [Landmark, "项目申报书"],
            [Sigma, "数学建模"],
            [FileText, "专利申请"],
            [FlaskConical, "实验设计"],
          ] as Array<[LucideIcon, string]>
        ).map(([Icon, label]) => (
          <span key={label} className="flex items-center gap-1.5">
            <Icon size={13} strokeWidth={1.8} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

function PainBand() {
  const pains = ["引用看着像真的，查无此文", "过程黑箱，导师问起来答不上", "长任务跑到一半，上下文就丢了"];
  const gains = ["每条结论都有可查证的出处", "检索、计算、判断全程留痕", "关键写入必须经你确认才落稿"];
  return (
    <section className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[72px]">
      <div
        className="grid overflow-hidden rounded-[18px] border md:grid-cols-2"
        style={{ borderColor: LINE, background: SURFACE }}
      >
        <div className="border-b px-8 py-8 md:border-b-0 md:border-r" style={{ borderColor: LINE }}>
          <div className="text-[11px] font-semibold tracking-[0.24em]" style={{ color: INK_FAINT }}>
            普通 AI 聊天给你的
          </div>
          <div className="mt-5 space-y-3.5">
            {pains.map((p) => (
              <div key={p} className="flex items-center gap-3 text-[13.5px]" style={{ color: INK_FAINT }}>
                <XCircle size={15} style={{ color: "#c9bfa9" }} />
                <span className="line-through decoration-[rgba(28,36,32,0.25)]">{p}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="px-8 py-8" style={{ background: ACCENT_SOFT }}>
          <div className="text-[11px] font-semibold tracking-[0.24em]" style={{ color: ACCENT }}>
            问津给你的
          </div>
          <div className="mt-5 space-y-3.5">
            {gains.map((g) => (
              <div key={g} className="flex items-center gap-3 text-[13.5px] font-medium" style={{ color: INK }}>
                <CheckCircle2 size={15} style={{ color: ACCENT }} />
                {g}
              </div>
            ))}
          </div>
        </div>
      </div>
      <p className="mt-6 text-center text-[15px]" style={{ color: INK_SOFT, fontFamily: serif }}>
        别的 AI 给你答案，问津给你<span style={{ color: ACCENT, fontWeight: 700 }}>敢交上去的</span>答案。
      </p>
    </section>
  );
}

function Highlights() {
  const items = [
    {
      icon: ShieldCheck,
      title: "结论有据可查",
      body: "每条结论后面都挂着可查证的文献与数据回执。引用不编造——没有出处的话，它宁可说不知道。",
    },
    {
      icon: Footprints,
      title: "轨迹可追溯",
      body: "检索了什么、算了什么、为什么这么判断，全程留痕。答辩和组会上，每一步都有据可查。",
    },
    {
      icon: Stamp,
      title: "你掌方向",
      body: "研究团队跑链路，但关键产出必须经你确认才会写进论文。AI 不会背着你改动任何一个字。",
    },
    {
      icon: Timer,
      title: "长任务跑得完",
      body: "小时级的建模与综述任务在服务端持续执行，断线自动续跑、失败断点恢复，不是聊十轮就忘的玩具。",
    },
  ];
  return (
    <section className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[110px]">
      <Eyebrow>为什么是问津</Eyebrow>
      <h2 className="mt-5 text-[38px] font-bold leading-snug" style={{ color: INK, fontFamily: serif }}>
        为「敢不敢用」而生的四件事
      </h2>
      <div className="mt-10 grid gap-4 md:grid-cols-2">
        {items.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="group rounded-[16px] border p-7 transition-all hover:-translate-y-1 hover:shadow-[var(--wjn-shadow-md)]"
            style={{ borderColor: LINE, background: SURFACE }}
          >
            <div
              className="flex h-11 w-11 items-center justify-center rounded-[10px]"
              style={{ background: ACCENT_SOFT, color: ACCENT }}
            >
              <Icon size={20} strokeWidth={1.8} />
            </div>
            <h3 className="mt-5 text-[19px] font-bold" style={{ color: INK, fontFamily: serif }}>
              {title}
            </h3>
            <p className="mt-2.5 text-[13.5px] leading-[1.85]" style={{ color: INK_SOFT }}>
              {body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    ["提一个研究问题", "一句话描述你的题目或材料，剩下的拆解、规划交给研究团队。"],
    ["团队跑链路，依据随行", "文献、计算、草稿在工作空间里持续推进，每一步都有据可查。"],
    ["你确认，然后成稿", "关键产出送审到你手里，确认之后才写入论文，导出即交付。"],
  ];
  return (
    <section className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[110px]">
      <Eyebrow>它怎么工作</Eyebrow>
      <h2 className="mt-5 text-[38px] font-bold leading-snug" style={{ color: INK, fontFamily: serif }}>
        三步，从问题到交付
      </h2>
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {steps.map(([title, body], i) => (
          <div key={title} className="relative rounded-[16px] border p-7" style={{ borderColor: LINE, background: SURFACE }}>
            <div
              className="text-[34px] font-bold italic"
              style={{ color: "rgba(181,133,47,0.55)", fontFamily: "Georgia, serif" }}
            >
              {String(i + 1).padStart(2, "0")}
            </div>
            <h3 className="mt-4 text-[17px] font-bold" style={{ color: INK, fontFamily: serif }}>
              {title}
            </h3>
            <p className="mt-2 text-[13px] leading-[1.85]" style={{ color: INK_SOFT }}>
              {body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function UseCases() {
  const cases = [
    { icon: ScrollText, title: "SCI 论文", body: "从选题综述到成稿修订，引用全部可溯源。", href: quickStartHref("sci") },
    { icon: BookOpen, title: "毕业论文", body: "开题、综述、实验设计，按学校规范推进。", href: quickStartHref("thesis") },
    { icon: Sigma, title: "数学建模", body: "模型设计、求解验证、论文撰写一站完成。", href: quickStartHref("math_modeling") },
    { icon: Landmark, title: "项目申报", body: "立项依据与技术路线，经得起评审追问。", href: quickStartHref("proposal") },
  ];
  return (
    <section className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[110px]">
      <Eyebrow>为长流程研究与写作设计</Eyebrow>
      <div className="mt-10 grid gap-4 md:grid-cols-4">
        {cases.map(({ icon: Icon, title, body, href }) => (
          <Link
            key={title}
            href={href}
            className="rounded-[16px] border p-6 transition-all hover:-translate-y-1 hover:shadow-[var(--wjn-shadow-md)]"
            style={{ borderColor: LINE, background: SURFACE }}
          >
            <Icon size={18} strokeWidth={1.8} style={{ color: ACCENT }} />
            <h3 className="mt-4 text-[16px] font-bold" style={{ color: INK, fontFamily: serif }}>
              {title}
            </h3>
            <p className="mt-2 text-[12.5px] leading-[1.8]" style={{ color: INK_SOFT }}>
              {body}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}

function FinalCta({ onStart }: { onStart: () => void }) {
  return (
    <section className="relative z-10 mx-auto max-w-[1200px] px-8 py-[110px]">
      <div className="relative overflow-hidden rounded-[20px] px-10 py-16 text-center" style={{ background: INK }}>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: "linear-gradient(to right, rgba(245,241,232,0.05) 1px, transparent 1px)",
            backgroundSize: "120px 100%",
          }}
        />
        <div className="relative">
          <div className="text-[11px] font-semibold tracking-[0.32em] text-[#c8b585]">开始你的第一个研究任务</div>
          <h2 className="mt-5 text-[40px] font-bold leading-snug text-[#f5f1e8]" style={{ fontFamily: serif }}>
            把科研从临时问答，
            <br />
            推进到可持续交付。
          </h2>
          <p className="mx-auto mt-5 max-w-[440px] text-[14px] leading-[1.85] text-[rgba(245,241,232,0.62)]">
            从一个想法开始，进入工作空间，让研究团队组织上下文、推进任务，并在你的确认下完成最终复核。
          </p>
          <button
            type="button"
            onClick={onStart}
            className="group mx-auto mt-9 flex h-12 w-fit items-center gap-2.5 rounded-full px-8 text-[14.5px] font-medium text-[#1c2420] transition-transform hover:-translate-y-0.5"
            style={{ background: "#f5f1e8" }}
          >
            开始一个研究任务
            <ArrowRight size={16} strokeWidth={2.2} className="transition-transform group-hover:translate-x-0.5" />
          </button>
        </div>
      </div>
      <footer className="mt-14 flex items-center justify-between border-t pt-7 text-[12px]" style={{ borderColor: LINE, color: INK_FAINT }}>
        <div className="flex items-center gap-2.5">
          <Seal />
          <span>问津 WENJIN · 结论有依据，过程可回溯</span>
        </div>
        <span className="italic" style={{ fontFamily: "Georgia, serif" }}>
          Evidence visible. Process traceable.
        </span>
      </footer>
    </section>
  );
}

export default function HomePage() {
  const { isAuthenticated } = useAuthStore();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authOpen, setAuthOpen] = useState(false);

  const openAuth = useCallback((mode: AuthMode) => {
    setAuthMode(mode);
    setAuthOpen(true);
  }, []);

  const closeAuth = useCallback(() => setAuthOpen(false), []);

  const start = useCallback(() => {
    if (isAuthenticated) {
      window.location.href = "/workspaces";
    } else {
      openAuth("register");
    }
  }, [isAuthenticated, openAuth]);

  return (
    <main className="relative min-h-screen overflow-hidden" style={{ background: PAPER, color: INK }}>
      {/* faint column hairlines */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: "linear-gradient(to right, rgba(28,36,32,0.045) 1px, transparent 1px)",
          backgroundSize: "120px 100%",
          maskImage: "linear-gradient(to bottom, black 0%, transparent 78%)",
          WebkitMaskImage: "linear-gradient(to bottom, black 0%, transparent 78%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px]"
        style={{ background: "linear-gradient(180deg, rgba(20,84,74,0.06), transparent)" }}
      />
      <LandingNav onAuth={openAuth} />
      <HeroCopy onStart={start} />
      <PainBand />
      <section id="demo" className="relative z-10 mx-auto max-w-[1200px] px-8 pt-[72px]">
        <LandingTheater accent={ACCENT} soft={ACCENT_SOFT} panel={PAPER_DEEP} meta={BRASS} surface={SURFACE} />
      </section>
      <Highlights />
      <HowItWorks />
      <UseCases />
      <FinalCta onStart={start} />
      <AuthModal isOpen={authOpen} onClose={closeAuth} initialMode={authMode} />
    </main>
  );
}
