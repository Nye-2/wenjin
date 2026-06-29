"use client";

import Link from "next/link";
import { PublicMarketingNav } from "@/components/layout/public-marketing-nav";
import { useLocaleStore, type Locale } from "@/stores/locale";

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

const DOCS_COPY: Record<Locale, DocsCopy> = {
  cn: {
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
          "每个 workspace 都沉淀文献、Prism 文件、决策、运行历史、实验环境、任务、设置，以及后台隐藏维护的一份 workspace memory，保证长程研究上下文连续。",
      },
      {
        label: "Agent Team",
        title: "左侧对话理解意图，右侧研究团队推进执行",
        body:
          "用户在左侧描述任务；问津在右侧按 capability 召集团队成员、分配技能，并把过程投射成可确认工作面。",
      },
      {
        label: "Confirm",
        title: "结果自动写回，再支持撤回",
        body:
          "执行产出会自动写入 Prism 文件、资料库、决策或任务；用户可以在运行面板里查看写入状态并撤回本次保存。",
      },
    ],
    contract: {
      eyebrow: "Product contract",
      title: "后续扩展都围绕同一套业务结构。",
      body:
        "无论扩充团队角色、调整提示词、改进工作流，最终都应回到这些稳定对象，避免功能越做越散。",
      items: [
        "Workspace 持久层：Library、Prism 文件、Decisions、Run History、实验环境、Tasks、Settings，以及后台隐藏维护的一份 workspace memory。",
        "7 种消息 block：text、thinking、status_line、question_card、result_card、tool_invocation、tool_result。",
        "Capability 数据驱动：YAML seed + DB 配置，管理员可在后台调整。",
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
          body: "问津从 capability 和团队模板中选择合适成员，推进检索、写作、实验或质量检查。",
        },
        {
          index: "03",
          title: "确认结果并进入 Prism",
          body: "确认 result_card 后写回对应房间，稿件类成果进入 Prism 继续编辑、编译和优化。",
        },
      ],
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
      eyebrow: "Docs",
      title: "A practical guide from workspace to delivery.",
      subtitle:
        "Wenjin is not a one-off chat surface. It keeps sources, decisions, execution, confirmation, and manuscripts inside one traceable research workspace.",
      primary: "Enter Workbench",
      secondary: "View pricing",
    },
    guides: [
      {
        label: "Workspace",
        title: "One research space per project",
        body:
          "Each workspace stores library items, Prism files, decisions, run history, experiment-environment state, tasks, settings, and one hidden workspace memory document for long-running continuity.",
      },
      {
        label: "Agent Team",
        title: "Conversation frames intent. The research team runs work.",
        body:
          "Users describe work on the left. Wenjin recruits team members through capabilities and projects execution into the right workbench.",
      },
      {
        label: "Confirm",
        title: "Outputs are confirmed before commit",
        body:
          "Execution results are staged as result cards. Users can accept all by default or select the exact items to commit.",
      },
    ],
    contract: {
      eyebrow: "Product contract",
      title: "Future expansion should return to one stable structure.",
      body:
        "New team roles, prompts, and workflows should converge on the same product objects instead of creating scattered feature paths.",
      items: [
        "Workspace persistence: Library, Prism files, Decisions, Run History, Experiment Environment, Tasks, Settings, plus one hidden workspace memory document.",
        "7 message blocks: text, thinking, status_line, question_card, result_card, tool_invocation, tool_result.",
        "Data-driven capabilities: YAML seeds plus DB-backed runtime configuration.",
        "One experiment environment per workspace, reused across experiments, with startup billed in credits.",
      ],
    },
    loop: {
      title: "Recommended operating loop",
      steps: [
        {
          index: "01",
          title: "Describe the research task",
          body: "Provide topic, materials, target venue, or deliverable. The conversation asks follow-up questions when context is insufficient.",
        },
        {
          index: "02",
          title: "Let the research team organize execution",
          body: "Wenjin selects the right capability and team members for retrieval, writing, experiment, or quality-check work.",
        },
        {
          index: "03",
          title: "Confirm results and continue in Prism",
          body: "Accepted result cards write back to rooms. Manuscript outputs continue through Prism editing and compile flows.",
        },
      ],
    },
  },
};

export default function DocsPage() {
  const { locale } = useLocaleStore();
  const copy = DOCS_COPY[locale];

  return (
    <main className="min-h-screen bg-[#fbfcfe] text-[#101828]">
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
                href="/workspaces"
                className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#101828] px-6 text-sm font-bold text-white shadow-[0_16px_44px_rgba(16,24,40,0.18)] transition hover:bg-[#1f2937]"
              >
                {copy.hero.primary}
              </Link>
              <Link
                href="/pricing"
                className="inline-flex min-h-12 items-center justify-center rounded-full border border-[rgba(16,24,40,0.12)] bg-white px-6 text-sm font-bold text-[#101828] transition hover:bg-[#f9fafb]"
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
                <h2 className="mt-5 text-2xl font-bold leading-tight text-[#101828]">
                  {guide.title}
                </h2>
                <p className="mt-4 text-sm leading-7 text-[#667085]">
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
              <h2 className="mt-5 text-3xl font-bold leading-tight text-[#101828]">
                {copy.contract.title}
              </h2>
              <p className="mt-4 text-base leading-8 text-[#667085]">
                {copy.contract.body}
              </p>
            </div>
            <div className="rounded-[1.75rem] border border-[rgba(16,24,40,0.08)] bg-white p-8 shadow-[0_18px_60px_rgba(16,24,40,0.05)]">
              <ul className="space-y-4">
                {copy.contract.items.map((item) => (
                  <li
                    key={item}
                    className="border-b border-[rgba(16,24,40,0.08)] pb-4 text-sm leading-7 text-[#475467] last:border-b-0 last:pb-0"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="mt-16">
            <h2 className="text-3xl font-bold tracking-[-0.02em] text-[#101828]">
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
                  <h3 className="mt-5 text-xl font-bold leading-tight text-[#101828]">
                    {step.title}
                  </h3>
                  <p className="mt-4 text-sm leading-7 text-[#667085]">
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
