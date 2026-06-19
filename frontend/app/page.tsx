"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  Database,
  FileCheck2,
  FileText,
  Library,
  type LucideIcon,
} from "lucide-react";
import { AuthModal } from "@/components/auth/auth-modal";
import { UserDropdown } from "@/components/auth/user-dropdown";
import { useAuthStore } from "@/stores/auth";
import { useLocaleStore, type Locale } from "@/stores/locale";

type AuthMode = "login" | "register";
type WorkspaceType =
  | "sci"
  | "thesis"
  | "proposal"
  | "patent"
  | "software_copyright";

interface LandingCopy {
  nav: {
    product: string;
    docs: string;
    login: string;
    register: string;
    enter: string;
    quickStart: string;
    pricing: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    subtitle: string;
    caption: string;
    previewAlt: string;
    signals: string[];
  };
  positioning: {
    eyebrow: string;
    title: string;
    body: string;
    ordinaryLabel: string;
    ordinaryTitle: string;
    ordinaryBody: string;
    wenjinLabel: string;
    wenjinTitle: string;
    wenjinBody: string;
  };
  loop: {
    eyebrow: string;
    title: string;
    body: string;
    steps: Array<{ index: string; title: string; body: string }>;
  };
  scenes: {
    eyebrow: string;
    title: string;
  };
  final: {
    eyebrow: string;
    title: string;
    body: string;
  };
  quickStartItems: Record<WorkspaceType, string>;
}

const COPY: Record<Locale, LandingCopy> = {
  cn: {
    nav: {
      product: "产品",
      docs: "文档",
      login: "登录",
      register: "注册",
      enter: "进入工作台",
      quickStart: "快速开始",
      pricing: "定价",
    },
    hero: {
      eyebrow: "Research OS / Prism-native",
      title: "问津 Wenjin",
      subtitle:
        "从一个研究想法开始，学术 Harness 召集定制化专家 Agent，组织文献、证据、实验与稿件；你在 Prism 里确认引用、修改和最终成稿。",
      caption: "学术 Harness、专家团队、Library、Memory、Run History 与 Prism 在同一个 workspace 里协作。",
      previewAlt: "Wenjin Prism 研究工作台产品预览",
      signals: ["学术 Harness", "专家 Agent", "证据链", "Prism"],
    },
    positioning: {
      eyebrow: "Positioning",
      title: "不是聊天框，也不是模板库。它是研究任务的执行环境。",
      body:
        "Wenjin 的价值不是生成一段文字，而是让研究上下文持续沉淀：文献、证据、记忆、实验材料和稿件确认都在同一个 workspace 里推进。",
      ordinaryLabel: "普通 AI 写作",
      ordinaryTitle: "回答结束后，工作流也断了。",
      ordinaryBody:
        "用户还要自己搬运文献、引用、实验、图表和正文。结果能看，但很难变成稳定的研究过程。",
      wenjinLabel: "Wenjin",
      wenjinTitle: "Agent 带着 workspace 上下文持续工作。",
      wenjinBody:
        "每次执行都沉淀到 Library、Memory、Documents 和 Prism，形成能被确认、复用和继续推进的研究链路。",
    },
    loop: {
      eyebrow: "Operating Loop",
      title: "用户掌方向，Agent 跑链路。",
      body:
        "系统自动推进文献、证据、实验和写作；关键结果回到用户确认。它不是把人排除在外，而是把人的判断放在最重要的位置。",
      steps: [
        {
          index: "01",
          title: "确定研究意图",
          body: "把模糊想法变成清晰目标、约束和交付物。",
        },
        {
          index: "02",
          title: "自动组织上下文",
          body: "文献、记忆、引用和材料进入同一个 workspace。",
        },
        {
          index: "03",
          title: "确认成为稿件",
          body: "最终产出进入 Prism，由用户确认修改和引用。",
        },
      ],
    },
    scenes: {
      eyebrow: "Use Cases",
      title: "为长流程研究与写作任务设计。",
    },
    final: {
      eyebrow: "Deliver",
      title: "把科研从临时问答推进到可持续交付。",
      body:
        "从一个想法开始，进入 workspace，让 Agent 组织上下文、推进任务，并在 Prism 中完成最终确认。",
    },
    quickStartItems: {
      sci: "SCI",
      thesis: "学位论文",
      proposal: "项目书",
      patent: "专利",
      software_copyright: "软著",
    },
  },
  en: {
    nav: {
      product: "Product",
      docs: "Docs",
      login: "Log in",
      register: "Sign up",
      enter: "Enter Workbench",
      quickStart: "Quick Start",
      pricing: "Pricing",
    },
    hero: {
      eyebrow: "Research OS / Prism-native",
      title: "Wenjin",
      subtitle:
        "From a research idea, an academic harness recruits custom expert agents to organize literature, evidence, experiments, and drafts while you confirm citations, edits, and final manuscript state in Prism.",
      caption: "Academic harness, expert agents, Library, Memory, Run History, and Prism move inside one workspace.",
      previewAlt: "Wenjin Prism research workbench preview",
      signals: ["Academic Harness", "Expert Agents", "Evidence Graph", "Prism"],
    },
    positioning: {
      eyebrow: "Positioning",
      title: "Not a chat box or a template library. A runtime for research work.",
      body:
        "Wenjin is not built to generate one isolated answer. It keeps literature, evidence, memory, experiments, and manuscript confirmation moving inside one workspace.",
      ordinaryLabel: "Ordinary AI writing",
      ordinaryTitle: "Once the answer ends, the workflow breaks.",
      ordinaryBody:
        "Researchers still have to move references, citations, charts, and drafts across tools. The output may be usable, but the process is fragile.",
      wenjinLabel: "Wenjin",
      wenjinTitle: "Agents keep working with workspace context.",
      wenjinBody:
        "Runs write back into Library, Memory, Documents, and Prism, creating a research loop that can be confirmed, reused, and continued.",
    },
    loop: {
      eyebrow: "Operating Loop",
      title: "You steer. Agents run the research loop.",
      body:
        "Wenjin advances literature, evidence, experiments, and writing automatically while returning critical decisions to the user.",
      steps: [
        {
          index: "01",
          title: "Frame intent",
          body: "Turn a rough idea into goals, constraints, and deliverables.",
        },
        {
          index: "02",
          title: "Organize context",
          body: "Literature, memory, citations, and materials stay in one workspace.",
        },
        {
          index: "03",
          title: "Confirm into manuscript",
          body: "Final outputs enter Prism for user-confirmed edits and citations.",
        },
      ],
    },
    scenes: {
      eyebrow: "Use Cases",
      title: "Built for long-form research and writing work.",
    },
    final: {
      eyebrow: "Deliver",
      title: "Move research from one-off answers to sustained delivery.",
      body:
        "Start from an idea, enter a workspace, let agents organize context and progress the work, then confirm the manuscript in Prism.",
    },
    quickStartItems: {
      sci: "SCI",
      thesis: "Thesis",
      proposal: "Proposal",
      patent: "Patent",
      software_copyright: "Software copyright",
    },
  },
};

const QUICK_START_ORDER: WorkspaceType[] = [
  "sci",
  "thesis",
  "proposal",
  "patent",
  "software_copyright",
];

const HERO_SIGNAL_ICONS: LucideIcon[] = [Library, Database, FileText, FileCheck2];

function quickStartHref(type: WorkspaceType): string {
  return `/workspaces?create=${type}`;
}

function LandingLanguageToggle() {
  const { locale, setLocale } = useLocaleStore();

  return (
    <div
      aria-label="Language"
      className="hidden min-h-10 items-center rounded-full border border-[rgba(16,24,40,0.1)] bg-white p-1 text-xs font-semibold text-[#475467] shadow-[0_10px_28px_rgba(16,24,40,0.06)] sm:inline-flex"
    >
      <button
        type="button"
        onClick={() => setLocale("cn")}
        className={`rounded-full px-3 py-1.5 transition ${
          locale === "cn" ? "bg-[#101828] text-white" : "hover:bg-[#f2f4f7]"
        }`}
      >
        中
      </button>
      <button
        type="button"
        onClick={() => setLocale("en")}
        className={`rounded-full px-3 py-1.5 transition ${
          locale === "en" ? "bg-[#101828] text-white" : "hover:bg-[#f2f4f7]"
        }`}
      >
        EN
      </button>
    </div>
  );
}

function QuickStartMenu({ copy }: { copy: LandingCopy }) {
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
        className="inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-full bg-[#f2f4f7] px-4 text-sm font-bold text-[#101828] transition hover:bg-[#e8ebf0]"
      >
        {copy.nav.quickStart}
        <ChevronDown aria-hidden="true" className="ml-1 h-4 w-4 text-[#667085]" />
      </button>

      {isOpen ? (
        <div
          role="menu"
          className="absolute right-0 top-14 z-50 w-56 rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-white p-2 shadow-[var(--wjn-shadow-md)]"
        >
          {QUICK_START_ORDER.map((type) => (
            <Link
              key={type}
              role="menuitem"
              href={quickStartHref(type)}
              className="flex min-h-11 items-center rounded-[var(--wjn-radius)] px-3 text-sm font-semibold text-[#344054] transition hover:bg-[#f2f4f7]"
            >
              {copy.quickStartItems[type]}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LandingNav({
  copy,
  onAuth,
}: {
  copy: LandingCopy;
  onAuth: (mode: AuthMode) => void;
}) {
  const { isAuthenticated } = useAuthStore();

  return (
    <header className="fixed left-0 right-0 top-0 z-50 border-b border-[rgba(16,24,40,0.08)] bg-[rgba(251,252,254,0.9)] backdrop-blur-xl">
      <nav className="mx-auto grid h-20 max-w-7xl grid-cols-[auto_1fr_auto] items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-3 text-base font-bold text-[#101828]">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#101828] text-sm font-black text-white">
            问
          </span>
          <span>问津 Wenjin</span>
        </Link>

        <div className="hidden items-center justify-center gap-1 md:flex">
          <a
            href="#product"
            className="inline-flex min-h-11 items-center rounded-full px-4 text-sm font-bold text-[#344054] transition hover:bg-[#f2f4f7]"
          >
            {copy.nav.product}
          </a>
          <Link
            href="/docs"
            className="inline-flex min-h-11 items-center rounded-full px-4 text-sm font-bold text-[#344054] transition hover:bg-[#f2f4f7]"
          >
            {copy.nav.docs}
          </Link>
          <Link
            href="/pricing"
            className="inline-flex min-h-11 items-center rounded-full px-4 text-sm font-bold text-[#344054] transition hover:bg-[#f2f4f7]"
          >
            {copy.nav.pricing}
          </Link>
        </div>

        <div className="flex items-center justify-end gap-2">
          <LandingLanguageToggle />

          {isAuthenticated ? (
            <div className="hidden sm:block">
              <UserDropdown />
            </div>
          ) : (
            <div className="hidden items-center gap-1 sm:flex">
              <button
                type="button"
                onClick={() => onAuth("login")}
                className="inline-flex min-h-10 items-center rounded-full px-4 text-sm font-bold text-[#344054] transition hover:bg-[#f2f4f7]"
              >
                {copy.nav.login}
              </button>
              <button
                type="button"
                onClick={() => onAuth("register")}
                className="inline-flex min-h-10 items-center rounded-full border border-[rgba(16,24,40,0.12)] bg-white px-4 text-sm font-bold text-[#101828] transition hover:bg-[#f9fafb]"
              >
                {copy.nav.register}
              </button>
            </div>
          )}

          <Link
            href="/workspaces"
            className="inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-full bg-[#101828] px-4 text-sm font-bold text-white shadow-[0_14px_34px_rgba(16,24,40,0.18)] transition hover:bg-[#1f2937]"
          >
            {copy.nav.enter}
          </Link>

          <QuickStartMenu copy={copy} />
        </div>
      </nav>
    </header>
  );
}

function SectionHeader({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body?: string;
}) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-[0.08em] text-[var(--wjn-text-secondary)]">
        {eyebrow}
      </p>
      <h2 className="mt-4 max-w-4xl text-3xl font-bold leading-tight text-[var(--wjn-text)] sm:text-4xl lg:text-5xl">
        {title}
      </h2>
      {body ? (
        <p className="mt-5 max-w-3xl text-base leading-8 text-[var(--wjn-text-secondary)] sm:text-lg">
          {body}
        </p>
      ) : null}
    </div>
  );
}

export default function HomePage() {
  const { locale } = useLocaleStore();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const copy = COPY[locale];

  const openAuth = useCallback((mode: AuthMode) => {
    setAuthMode(mode);
    setIsAuthOpen(true);
  }, []);

  return (
    <main className="min-h-screen bg-[var(--wjn-bg-base)] text-[var(--wjn-text)]">
      <LandingNav copy={copy} onAuth={openAuth} />

      <section className="relative isolate min-h-[86dvh] overflow-hidden border-b border-[var(--wjn-line)] px-4 pb-12 pt-28 sm:px-6 lg:pt-32">
        <Image
          priority
          alt={copy.hero.previewAlt}
          className="absolute inset-0 -z-30 h-full w-full object-cover object-[62%_50%]"
          data-testid="landing-hero-visual"
          fill
          sizes="100vw"
          src="/hero-prism-workbench.jpg"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-20 bg-[linear-gradient(90deg,rgba(251,252,254,0.98)_0%,rgba(251,252,254,0.92)_34%,rgba(251,252,254,0.56)_58%,rgba(251,252,254,0.12)_100%)]"
        />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 -z-10 h-40 bg-[linear-gradient(180deg,transparent,rgba(245,247,250,0.98))]"
        />

        <div className="mx-auto flex min-h-[calc(86dvh-10rem)] w-full max-w-7xl items-center">
          <div className="max-w-2xl py-10">
            <p className="inline-flex items-center gap-3 text-xs font-bold uppercase tracking-[0.08em] text-[var(--wjn-text-secondary)] before:h-px before:w-7 before:bg-[var(--wjn-text)]">
              {copy.hero.eyebrow}
            </p>
            <h1 className="mt-6 text-6xl font-black leading-[0.95] text-[var(--wjn-text)] sm:text-7xl lg:text-8xl">
              {copy.hero.title}
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-[var(--wjn-text-secondary)]">
              {copy.hero.subtitle}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href="/workspaces"
                className="inline-flex min-h-12 items-center justify-center whitespace-nowrap rounded-full bg-[var(--wjn-text)] px-6 text-sm font-bold text-white shadow-[0_16px_44px_rgba(16,24,40,0.18)] transition hover:bg-[#1f2937]"
              >
                {copy.nav.enter}
                <ArrowRight aria-hidden="true" className="ml-2 h-4 w-4" />
              </Link>
              <span className="max-w-md text-sm font-semibold leading-6 text-[var(--wjn-text-secondary)]">
                {copy.hero.caption}
              </span>
            </div>
            <div className="mt-10 grid max-w-2xl grid-cols-2 gap-2 sm:grid-cols-4">
              {copy.hero.signals.map((signal, index) => {
                const Icon = HERO_SIGNAL_ICONS[index] ?? FileText;
                return (
                  <div
                    key={signal}
                    className="flex min-h-11 items-center gap-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white/78 px-3 text-sm font-bold text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)] backdrop-blur"
                  >
                    <Icon aria-hidden="true" className="h-4 w-4 text-[var(--wjn-blue)]" />
                    {signal}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section id="product" className="px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <SectionHeader
            eyebrow={copy.positioning.eyebrow}
            title={copy.positioning.title}
            body={copy.positioning.body}
          />

          <div className="mt-11 grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
            <article className="min-h-72 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white p-8 shadow-[var(--wjn-shadow-sm)]">
              <span className="inline-flex rounded-full bg-[var(--wjn-surface-subtle)] px-3 py-2 text-xs font-bold text-[var(--wjn-text-secondary)]">
                {copy.positioning.ordinaryLabel}
              </span>
              <h3 className="mt-7 max-w-lg text-3xl font-bold leading-tight text-[var(--wjn-text)]">
                {copy.positioning.ordinaryTitle}
              </h3>
              <p className="mt-4 max-w-xl text-base leading-8 text-[var(--wjn-text-secondary)]">
                {copy.positioning.ordinaryBody}
              </p>
            </article>

            <article className="min-h-72 rounded-[var(--wjn-radius)] bg-[var(--wjn-text)] p-8 text-white shadow-[var(--wjn-shadow-md)]">
              <span className="inline-flex rounded-full bg-white/10 px-3 py-2 text-xs font-bold text-white/70">
                {copy.positioning.wenjinLabel}
              </span>
              <h3 className="mt-7 max-w-lg text-3xl font-bold leading-tight">
                {copy.positioning.wenjinTitle}
              </h3>
              <p className="mt-4 max-w-xl text-base leading-8 text-white/65">
                {copy.positioning.wenjinBody}
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <SectionHeader
            eyebrow={copy.loop.eyebrow}
            title={copy.loop.title}
            body={copy.loop.body}
          />

          <div className="mt-11 grid gap-4 lg:grid-cols-3">
            {copy.loop.steps.map((step, index) => (
              <article
                key={step.index}
                className={`min-h-56 rounded-[var(--wjn-radius)] border bg-white p-7 shadow-[var(--wjn-shadow-sm)] ${
                  index === 1
                    ? "border-[var(--wjn-accent-line)] shadow-[var(--wjn-shadow-md)]"
                    : "border-[var(--wjn-line)]"
                }`}
              >
                <span className="text-xs font-bold text-[#98a2b3]">{step.index}</span>
                <h3 className="mt-14 text-2xl font-bold leading-tight text-[var(--wjn-text)]">
                  {step.title}
                </h3>
                <p className="mt-4 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                  {step.body}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <SectionHeader eyebrow={copy.scenes.eyebrow} title={copy.scenes.title} />
          <div className="mt-9 flex flex-wrap gap-3">
            {QUICK_START_ORDER.map((type) => (
              <Link
                key={type}
                href={quickStartHref(type)}
                className="inline-flex min-h-11 items-center rounded-full border border-[var(--wjn-line)] bg-white px-5 text-sm font-bold text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] transition hover:bg-[#f9fafb]"
              >
                {copy.quickStartItems[type]}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 pb-28 pt-20 sm:px-6">
        <div className="mx-auto grid min-h-80 max-w-6xl items-end gap-8 rounded-[var(--wjn-radius-xl)] bg-[var(--wjn-text)] p-8 text-white shadow-[var(--wjn-shadow-lg)] lg:grid-cols-[1fr_auto] lg:p-11">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.08em] text-white/55">
              {copy.final.eyebrow}
            </p>
            <h2 className="mt-4 max-w-4xl text-3xl font-bold leading-tight sm:text-4xl lg:text-5xl">
              {copy.final.title}
            </h2>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/65">
              {copy.final.body}
            </p>
          </div>
          <Link
            href="/workspaces"
            className="inline-flex min-h-12 items-center justify-center rounded-full bg-white px-6 text-sm font-bold text-[#101828] transition hover:bg-[#f2f4f7]"
          >
            {copy.nav.enter}
          </Link>
        </div>
      </section>

      <AuthModal
        isOpen={isAuthOpen}
        initialMode={authMode}
        onClose={() => setIsAuthOpen(false)}
      />
    </main>
  );
}
