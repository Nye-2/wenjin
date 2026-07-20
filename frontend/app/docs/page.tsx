"use client";

import Link from "next/link";
import { PublicMarketingNav } from "@/components/layout/public-marketing-nav";

interface DocsCopy {
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
    primary: string;
    secondary: string;
  };
  guides: Array<{
    label: string;
    title: string;
    body: string;
  }>;
  contract: {
    eyebrow: string;
    title: string;
    body: string;
    items: string[];
  };
  loop: {
    title: string;
    steps: Array<{ index: string; title: string; body: string }>;
  };
}

const DOCS_COPY: DocsCopy = {
  nav: {
    product: "产品",
    docs: "文档",
    pricing: "定价",
    workbench: "进入工作台",
  },
  hero: {
    eyebrow: "Docs",
    title: "从 workspace 到交付的使用手册。",
    subtitle:
      "Wenjin 的核心不是一次聊天，而是把来源、判断、执行、确认和成稿放进同一个可追踪工作空间。这里按真实使用链路整理关键概念。",
    primary: "进入工作台",
    secondary: "查看定价",
  },
  guides: [
    {
      label: "Workspace",
      title: "一个项目一个研究空间",
      body:
        "每个工作空间都沉淀资料、来源、Prism 文件、关键决策、实验环境与项目记忆，保证长程研究上下文连续。",
    },
    {
      label: "Agent Team",
      title: "左侧对话理解意图，右侧研究团队推进执行",
      body:
        "用户在左侧描述任务；问津依据 MissionPolicy 组织任务、分配 WorkerSkill，并把过程投射成可确认工作面。",
    },
    {
      label: "Confirm",
      title: "结果先暂存，审核后保存",
      body:
        "受保护的产出会先进入待确认区；用户在 Mission Console 查看候选变更，再确认保存选中的 Prism 文件、资料或项目决策。",
    },
  ],
  contract: {
    eyebrow: "Product contract",
    title: "后续扩展都围绕同一套业务结构。",
    body:
      "无论扩充团队角色、调整提示词、改进工作流，最终都应回到这些稳定对象，避免功能越做越散。",
    items: [
      "工作空间持久层：资料库、Prism 文件、项目记忆与设置；长任务统一由 Mission 聚合记录进展、来源、成果、复核和提交。",
      "7 种消息 block：text、thinking、status_line、question_card、result_card、tool_invocation、tool_result。",
      "MissionPolicy 与 WorkerSkill 由数据库目录统一管理，阶段契约和工具范围随任务固定。",
      "实验环境单 workspace 单实例，随任务复用，启动按积分计费。",
    ],
  },
  loop: {
    title: "推荐使用路径",
    steps: [
      {
        index: "01",
        title: "先描述研究任务",
        body: "给出主题、材料、目标期刊或交付物。信息不足时，左侧对话会先追问。",
      },
      {
        index: "02",
        title: "让研究团队组织执行",
        body: "问津依据 MissionPolicy 选择合适的 WorkerSkill，推进检索、写作、实验或质量检查。",
      },
      {
        index: "03",
        title: "确认结果并进入 Prism",
        body: "确认 result_card 后写回对应房间，稿件类成果进入 Prism 继续编辑、编译和优化。",
      },
    ],
  },
};

export default function DocsPage() {
  const copy = DOCS_COPY;

  return (
    <main className="min-h-screen bg-[var(--wjn-surface)] text-[var(--wjn-text)]">
      <PublicMarketingNav
        productLabel={copy.nav.product}
        docsLabel={copy.nav.docs}
        pricingLabel={copy.nav.pricing}
        workbenchLabel={copy.nav.workbench}
        active="docs"
      />

      <section className="px-4 py-24 sm:px-6 lg:py-32">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-4xl">
            <p className="inline-flex items-center gap-3 text-xs font-bold uppercase tracking-[0.08em] text-[var(--wjn-text-secondary)] before:h-px before:w-7 before:bg-[var(--wjn-text)]">
              {copy.hero.eyebrow}
            </p>
            <h1 className="mt-6 text-5xl font-black leading-[0.96] text-[var(--wjn-text)] sm:text-7xl">
              {copy.hero.title}
            </h1>
            <p className="mt-7 max-w-3xl text-lg leading-8 text-[var(--wjn-text-secondary)]">
              {copy.hero.subtitle}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href="/workspaces"
                className="inline-flex min-h-12 items-center justify-center rounded-full bg-[var(--wjn-text)] px-6 text-sm font-bold text-white shadow-[0_16px_44px_rgba(16,24,40,0.18)] transition hover:bg-[var(--wjn-text)]"
              >
                {copy.hero.primary}
              </Link>
              <Link
                href="/pricing"
                className="inline-flex min-h-12 items-center justify-center rounded-full border border-[rgba(16,24,40,0.12)] bg-white px-6 text-sm font-bold text-[var(--wjn-text)] transition hover:bg-[var(--wjn-surface)]"
              >
                {copy.hero.secondary}
              </Link>
            </div>
          </div>

          <div className="mt-16 grid gap-4 md:grid-cols-3">
            {copy.guides.map((guide) => (
              <article
                key={guide.label}
                className="rounded-[1.5rem] border border-[rgba(16,24,40,0.08)] bg-white p-6 shadow-[0_18px_60px_rgba(16,24,40,0.05)]"
              >
                <p className="text-sm font-bold text-[var(--wjn-blue)]">
                  {guide.label}
                </p>
                <h2 className="mt-5 text-2xl font-bold leading-tight text-[var(--wjn-text)]">
                  {guide.title}
                </h2>
                <p className="mt-4 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                  {guide.body}
                </p>
              </article>
            ))}
          </div>

          <section className="mt-16 grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-[1.75rem] border border-[rgba(16,24,40,0.08)] bg-white p-8 shadow-[0_18px_60px_rgba(16,24,40,0.06)]">
              <p className="text-sm font-bold text-[var(--wjn-blue)]">
                {copy.contract.eyebrow}
              </p>
              <h2 className="mt-5 text-3xl font-bold leading-tight text-[var(--wjn-text)]">
                {copy.contract.title}
              </h2>
              <p className="mt-4 text-base leading-8 text-[var(--wjn-text-secondary)]">
                {copy.contract.body}
              </p>
            </div>
            <div className="rounded-[1.75rem] border border-[rgba(16,24,40,0.08)] bg-white p-8 shadow-[0_18px_60px_rgba(16,24,40,0.05)]">
              <ul className="space-y-4">
                {copy.contract.items.map((item) => (
                  <li
                    key={item}
                    className="border-b border-[rgba(16,24,40,0.08)] pb-4 text-sm leading-7 text-[var(--wjn-text-secondary)] last:border-b-0 last:pb-0"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="mt-16">
            <h2 className="text-3xl font-bold tracking-[-0.02em] text-[var(--wjn-text)]">
              {copy.loop.title}
            </h2>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {copy.loop.steps.map((step) => (
                <article
                  key={step.index}
                  className="rounded-[1.5rem] border border-[rgba(16,24,40,0.08)] bg-white p-6 shadow-[0_18px_60px_rgba(16,24,40,0.05)]"
                >
                  <p className="text-sm font-bold text-[var(--wjn-blue)]">
                    {step.index}
                  </p>
                  <h3 className="mt-5 text-xl font-bold leading-tight text-[var(--wjn-text)]">
                    {step.title}
                  </h3>
                  <p className="mt-4 text-sm leading-7 text-[var(--wjn-text-secondary)]">
                    {step.body}
                  </p>
                </article>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
