"use client";

import Link from "next/link";
import { PublicMarketingNav } from "@/components/layout/public-marketing-nav";
import { useLocaleStore, type Locale } from "@/stores/locale";

interface PricingCopy {
  nav: {
    product: string;
    docs: string;
    pricing: string;
    workbench: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    subtitle: string;
    badge: string;
    account: string;
    start: string;
  };
  cards: Array<{
    title: string;
    body: string;
    price: string;
  }>;
  note: {
    title: string;
    body: string;
  };
}

const PRICING_COPY: Record<Locale, PricingCopy> = {
  cn: {
    nav: {
      product: "产品",
      docs: "文档",
      pricing: "定价",
      workbench: "进入工作台",
    },
    hero: {
      eyebrow: "Pricing",
      title: "清晰的 credits 定价，按科研任务实际使用结算。",
      subtitle:
        "Wenjin 用 credits 承载模型调用、文献检索、capability 执行和 sandbox 运行消耗。余额、规则和流水统一回到账户后台查看。",
      badge: "当前阶段采用 credits 积分结算",
      account: "查看积分后台",
      start: "进入工作台",
    },
    cards: [
      {
        title: "主线对话",
        body: "用于需求确认、研究方向讨论和 workspace 上下文维护。",
        price: "按实际使用折算积分",
      },
      {
        title: "Capability 执行",
        body: "覆盖文献定位、全文写作、审稿回复、实验结果包等长链路任务。",
        price: "按运行节点和模型消耗结算",
      },
      {
        title: "Sandbox 与数据分析",
        body: "用于后续实验、统计检验、图表生成和数据服务调用。",
        price: "按工具与计算资源结算",
      },
    ],
    note: {
      title: "账户资产不放在首页。",
      body:
        "首页只介绍产品；积分余额、流水、成本规则和后续充值能力都在个人后台承载，避免把研究入口变成账单页。",
    },
  },
  en: {
    nav: {
      product: "Product",
      docs: "Docs",
      pricing: "Pricing",
      workbench: "Enter Workbench",
    },
    hero: {
      eyebrow: "Pricing",
      title: "Transparent credits pricing for research work.",
      subtitle:
        "Wenjin uses credits for model calls, literature search, capability execution, and sandbox runs. Balance, rules, and history live in the account dashboard.",
      badge: "Credits-based billing",
      account: "Open credits dashboard",
      start: "Enter Workbench",
    },
    cards: [
      {
        title: "Mainline chat",
        body: "For requirement clarification, research direction, and workspace context maintenance.",
        price: "Calculated by actual usage",
      },
      {
        title: "Capability runs",
        body: "Long-running tasks such as literature positioning, manuscript writing, reviewer response, and experiment packs.",
        price: "Charged by run nodes and model usage",
      },
      {
        title: "Sandbox and analysis",
        body: "Future-facing experiments, statistical tests, chart generation, and data-service calls.",
        price: "Charged by tools and compute resources",
      },
    ],
    note: {
      title: "Account assets stay out of the home page.",
      body:
        "The home page explains the product. Credit balance, history, cost rules, and future recharge flows belong in the account dashboard.",
    },
  },
};

export default function PricingPage() {
  const { locale } = useLocaleStore();
  const copy = PRICING_COPY[locale];

  return (
    <main className="min-h-screen bg-[#fbfcfe] text-[#101828]">
      <PublicMarketingNav
        productLabel={copy.nav.product}
        docsLabel={copy.nav.docs}
        pricingLabel={copy.nav.pricing}
        workbenchLabel={copy.nav.workbench}
        active="pricing"
      />

      <section className="px-4 py-24 sm:px-6 lg:py-32">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-4xl">
            <p className="inline-flex items-center gap-3 text-xs font-bold uppercase tracking-[0.08em] text-[#344054] before:h-px before:w-7 before:bg-[#101828]">
              {copy.hero.eyebrow}
            </p>
            <h1 className="mt-6 text-5xl font-black leading-[0.96] text-[#101828] sm:text-7xl">
              {copy.hero.title}
            </h1>
            <p className="mt-7 max-w-3xl text-lg leading-8 text-[#667085]">
              {copy.hero.subtitle}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href="/dashboard/me"
                className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#101828] px-6 text-sm font-bold text-white shadow-[0_16px_44px_rgba(16,24,40,0.18)] transition hover:bg-[#1f2937]"
              >
                {copy.hero.account}
              </Link>
              <Link
                href="/workspaces"
                className="inline-flex min-h-12 items-center justify-center rounded-full border border-[rgba(16,24,40,0.12)] bg-white px-6 text-sm font-bold text-[#101828] transition hover:bg-[#f9fafb]"
              >
                {copy.hero.start}
              </Link>
            </div>
          </div>

          <div className="mt-16 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-[1.75rem] border border-[rgba(16,24,40,0.08)] bg-white p-7 shadow-[0_18px_60px_rgba(16,24,40,0.06)]">
              <p className="text-sm font-bold text-[var(--wjn-blue)]">{copy.hero.badge}</p>
              <h2 className="mt-6 text-3xl font-bold leading-tight text-[#101828]">
                {copy.note.title}
              </h2>
              <p className="mt-4 text-base leading-8 text-[#667085]">
                {copy.note.body}
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {copy.cards.map((card) => (
                <article
                  key={card.title}
                  className="rounded-[1.5rem] border border-[rgba(16,24,40,0.08)] bg-white p-6 shadow-[0_18px_60px_rgba(16,24,40,0.05)]"
                >
                  <h3 className="text-lg font-bold leading-tight text-[#101828]">
                    {card.title}
                  </h3>
                  <p className="mt-4 text-sm leading-7 text-[#667085]">{card.body}</p>
                  <p className="mt-6 text-sm font-bold text-[var(--wjn-blue)]">{card.price}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
