# Homepage Enrichment + Workspace Simplification Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the homepage to a full product showcase (7 sections) and simplify the workspace list page by removing the redundant "Recent" section and compressing the template area.

**Architecture:** Homepage is a pure frontend rewrite — static content page with i18n, Framer Motion, and existing design system components. Workspace page is a focused simplification — delete the "Recent" section, compress templates to inline buttons, simplify the header. No backend changes.

**Tech Stack:** Next.js 16, React 19, TypeScript, TailwindCSS, Framer Motion, lucide-react

---

### Task 1: Add homepage i18n keys

**Files:**
- Modify: `frontend/locales/cn.json`
- Modify: `frontend/locales/en.json`

**Step 1: Add new i18n keys for the 3 new homepage sections**

In `cn.json`, add these keys inside the `"home"` object (after the existing `"cta"` block):

```json
"philosophy": {
  "eyebrow": "设计理念",
  "title": "为什么问津不一样",
  "subtitle": "学术写作不是一次性生成任务，而是阶段性的、迭代的、高度个人化的过程。",
  "cards": {
    "conversation": {
      "title": "对话即工作流",
      "description": "不是填表单，不是点按钮执行任务。通过自然对话完成所有工作，AI 会主动询问它需要知道的信息，引导你逐步推进。"
    },
    "stages": {
      "title": "阶段感知",
      "description": "每个工作区都有清晰的研究阶段——调研、收集、结构、写作、评审。系统知道你现在在哪里，推荐下一步该做什么。"
    },
    "singleThread": {
      "title": "一个空间，一段对话",
      "description": "每个工作区只维护一个持续的对话。你不需要管理多个分支，AI 通过摘要压缩和长期记忆保持上下文连贯。"
    },
    "artifacts": {
      "title": "成果驱动",
      "description": "每次对话产出的章节、综述、大纲都作为成果持久保存，可追溯来源，可在后续工作中复用，积累为研究档案。"
    }
  }
},
"workspaceTypes": {
  "eyebrow": "工作区类型",
  "title": "覆盖五种学术写作场景",
  "subtitle": "选择你的工作类型，问津会配置对应的 AI 能力和工作流程。",
  "thesis": {
    "description": "从选题到答辩的全程支持",
    "modules": "深度调研 · 文献管理 · 大纲设计 · 论文撰写 · 图表生成 · 编译导出"
  },
  "sci": {
    "description": "面向期刊投稿的全流程辅助",
    "modules": "文献检索 · 论文分析 · 章节写作 · 同行评审 · 期刊推荐"
  },
  "proposal": {
    "description": "基金申请和研究计划撰写",
    "modules": "背景调研 · 实验设计 · 计划书撰写"
  },
  "software_copyright": {
    "description": "软件著作权登记材料准备",
    "modules": "著作权材料 · 技术文档"
  },
  "patent": {
    "description": "发明专利和实用新型申请",
    "modules": "专利撰写 · 现有技术检索"
  }
},
"useCases": {
  "eyebrow": "使用场景",
  "title": "看看问津能帮你做什么",
  "subtitle": "从真实学术场景出发，展示 AI 辅助的工作方式。",
  "cases": {
    "thesis": {
      "title": "硕士论文调研",
      "description": "从零开始确定研究方向，系统检索 50+ 篇文献，自动生成带引用的文献综述报告。"
    },
    "sci": {
      "title": "SCI 论文投稿",
      "description": "从 research gap 识别到 revision response letter，覆盖 SCI 论文从初稿到录用的全流程。"
    },
    "proposal": {
      "title": "国自然基金申请",
      "description": "梳理技术路线，撰写创新性论证和可行性分析，生成符合申报格式的计划书。"
    }
  }
},
"stats": {
  "skills": "21 个 AI Skill",
  "types": "5 种工作区类型",
  "disciplines": "8 个学科方向",
  "templates": "模板导入",
  "models": "多模型支持"
}
```

Do the same for `en.json` with equivalent English translations:

```json
"philosophy": {
  "eyebrow": "Design Philosophy",
  "title": "Why Wenjin Is Different",
  "subtitle": "Academic writing isn't a one-shot generation task — it's a staged, iterative, and deeply personal process.",
  "cards": {
    "conversation": {
      "title": "Conversation as Workflow",
      "description": "No forms, no buttons. Natural conversation drives all work. The AI proactively asks for what it needs and guides you step by step."
    },
    "stages": {
      "title": "Stage Awareness",
      "description": "Every workspace has clear research stages — research, collection, structure, writing, review. The system knows where you are and suggests what's next."
    },
    "singleThread": {
      "title": "One Space, One Conversation",
      "description": "Each workspace maintains a single persistent conversation. No thread management — AI uses summarization and long-term memory to keep context coherent."
    },
    "artifacts": {
      "title": "Artifact-Driven",
      "description": "Every output — chapters, reviews, outlines — is persisted as a traceable artifact that accumulates into a research portfolio."
    }
  }
},
"workspaceTypes": {
  "eyebrow": "Workspace Types",
  "title": "Five Academic Writing Scenarios",
  "subtitle": "Choose your work type. Wenjin configures the right AI capabilities and workflow.",
  "thesis": {
    "description": "Full support from topic selection to defense",
    "modules": "Deep Research · Literature · Outline · Writing · Figures · Export"
  },
  "sci": {
    "description": "End-to-end journal submission support",
    "modules": "Literature · Analysis · Section Writing · Peer Review · Journal Match"
  },
  "proposal": {
    "description": "Grant applications and research proposals",
    "modules": "Background · Experiment Design · Proposal Writing"
  },
  "software_copyright": {
    "description": "Software copyright registration materials",
    "modules": "Copyright Materials · Technical Docs"
  },
  "patent": {
    "description": "Invention and utility model patents",
    "modules": "Patent Drafting · Prior Art Search"
  }
},
"useCases": {
  "eyebrow": "Use Cases",
  "title": "See What Wenjin Can Do",
  "subtitle": "Real academic scenarios showing AI-assisted workflows.",
  "cases": {
    "thesis": {
      "title": "Master's Thesis Research",
      "description": "Start from scratch, systematically search 50+ papers, and auto-generate a cited literature review report."
    },
    "sci": {
      "title": "SCI Paper Submission",
      "description": "From research gap identification to revision response letters — the full lifecycle from draft to acceptance."
    },
    "proposal": {
      "title": "Research Grant Application",
      "description": "Structure your technical roadmap, write innovation justification and feasibility analysis in the required format."
    }
  }
},
"stats": {
  "skills": "21 AI Skills",
  "types": "5 Workspace Types",
  "disciplines": "8 Disciplines",
  "templates": "Template Import",
  "models": "Multi-Model"
}
```

Also update the existing `"home.workflow"` step content in `cn.json`:

```json
"workflow": {
  "title": "如何推进一项复杂任务",
  "subtitle": "让来源、判断、写作与交付留在同一条工作线上",
  "step1": {
    "title": "创建工作区",
    "description": "选择类型和学科方向，一键创建专属工作区。"
  },
  "step2": {
    "title": "对话引导",
    "description": "AI 主动了解你的研究方向、进展阶段和具体需求。"
  },
  "step3": {
    "title": "智能调研",
    "description": "系统性检索文献，分析研究空白，生成调研报告。"
  },
  "step4": {
    "title": "迭代写作",
    "description": "按阶段推进大纲、正文、修订，每个产出可追溯。"
  },
  "step5": {
    "title": "成果交付",
    "description": "编译排版，符合学校或期刊规范，导出终稿。"
  }
}
```

And same for `en.json`:

```json
"workflow": {
  "title": "How It Works",
  "subtitle": "Sources, analysis, writing, and delivery in one continuous workflow",
  "step1": {
    "title": "Create Workspace",
    "description": "Choose your project type and discipline, create a dedicated workspace."
  },
  "step2": {
    "title": "Conversational Guidance",
    "description": "AI proactively learns your research direction, progress, and needs."
  },
  "step3": {
    "title": "Smart Research",
    "description": "Systematic literature search, gap analysis, and research report generation."
  },
  "step4": {
    "title": "Iterative Writing",
    "description": "Progress through outline, drafts, and revisions — every output is traceable."
  },
  "step5": {
    "title": "Final Delivery",
    "description": "Compile, format to school or journal standards, and export."
  }
}
```

**Step 2: Commit**

```bash
git add frontend/locales/cn.json frontend/locales/en.json
git commit -m "feat: add homepage philosophy, workspace types, use cases i18n keys"
```

---

### Task 2: Rewrite homepage with 7 sections

**Files:**
- Modify: `frontend/app/page.tsx`

**Step 1: Rewrite the homepage**

Replace the entire file. The structure is:

1. **Helper components** — Keep `EnterWorkspaceButton`, `LearnMoreButton`, `SectionHeading` as-is
2. **Section 1: Hero** — Keep existing Hero but remove the CTA inside the stage preview card (line 365-369 `EnterWorkspaceButton compact`). Keep main CTA + Learn More.
3. **Section 2: Design Philosophy** — New. 4 cards in a 2x2 grid (md:2 cols). Icons: `MessageSquare` (conversation), `Layers` (stages), `GitMerge` (single thread), `Archive` (artifacts). Each card: icon + title + description from `home.philosophy.cards.*`.
4. **Section 3: Five Workspace Types** — Replace existing 4-card capabilities section. 5 cards in responsive grid. Icons: same `workspaceTypeIcons` from workspace page (`BookOpen`, `FileText`, `FlaskConical`, `Code2`, `Lightbulb`). Each card: icon + type name from `workspace.types.*` + description from `home.workspaceTypes.{type}.description` + modules badge row from `home.workspaceTypes.{type}.modules`.
5. **Section 4: How It Works** — Keep existing 5-step workflow, but content comes from updated i18n keys (task 1).
6. **Section 5: Use Cases** — New. 3 cards in a row. Each card: title + description + a small colored accent. Data from `home.useCases.cases.*`.
7. **Section 6: Technical Stats** — New. Single row of 5 compact badges/pills. Data from `home.stats.*`.
8. **Section 7: CTA + Footer** — Keep existing, no changes.

New imports to add: `MessageSquare`, `Layers`, `GitMerge`, `Archive`, `Code2`, `FileText` from lucide-react.

Key layout details:
- Philosophy cards: `grid grid-cols-1 gap-5 md:grid-cols-2` — each card uses `LiquidGlassCard` with an icon circle + title + description
- Workspace type cards: `grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3` with the first two cards spanning standard width — each card shows the type icon, name, description, and a `text-xs text-[var(--text-muted)]` line showing the modules
- Use case cards: `grid grid-cols-1 gap-5 md:grid-cols-3` — simpler cards with a colored left border accent
- Stats row: `flex flex-wrap justify-center gap-4` of `rounded-full border bg-white/78 px-5 py-2.5 text-sm` pills

**Step 2: Verify**

```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: rewrite homepage with philosophy, workspace types, use cases, stats sections"
```

---

### Task 3: Simplify workspace list page

**Files:**
- Modify: `frontend/app/workspaces/page.tsx`

**Step 1: Remove "Recent" section and merge into single list**

Delete the entire "Recent" section (lines 421-476: the `<section className="space-y-5">` block containing `recentWorkspaces`).

Delete the `recentWorkspaces` memo (lines 299-302).

In the "All Workspaces" section, update the card rendering: the first card in `filteredWorkspaces` gets `featured={true}` and `latestLabel={t("workspace.cards.latest")}` — same visual treatment the first "Recent" card currently gets, just within the unified list.

**Step 2: Compress template section to inline buttons**

Replace the template section (lines 478-522) with a compact single row:

```tsx
<div className="flex flex-wrap gap-2">
  {workspaceTypes.map((type) => {
    const Icon = workspaceTypeIcons[type.value];
    return (
      <button
        key={type.value}
        type="button"
        onClick={() => openCreateModal(type.value)}
        className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-white/78 px-4 py-2.5 text-sm font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--brand-navy)]/30 hover:bg-white"
      >
        <Icon className="h-4 w-4 text-[var(--text-secondary)]" />
        {type.label}
        <Plus className="h-3.5 w-3.5 text-[var(--text-muted)]" />
      </button>
    );
  })}
</div>
```

No section heading needed — the buttons sit between the header and the workspace list.

**Step 3: Simplify header**

Replace the `LiquidGlassCard`-wrapped header (lines 359-406) with a simpler layout:

```tsx
<div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
  <div className="flex items-center gap-4">
    <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
      {t("workspace.title")}
    </h1>
    <span className="rounded-full border border-[var(--border-default)] bg-white/78 px-3 py-1 text-sm text-[var(--text-secondary)]">
      {sortedWorkspaces.length}
    </span>
  </div>
  <div className="flex items-center gap-3">
    {/* search input */}
    {/* new workspace button */}
  </div>
</div>
```

Keep the search input and button from the current header, just remove the LiquidGlassCard wrapper, the subtitle text, and the brand eyebrow.

**Step 4: Verify**

```bash
cd frontend && npx tsc --noEmit
```

**Step 5: Commit**

```bash
git add frontend/app/workspaces/page.tsx
git commit -m "feat: simplify workspace page — merge lists, compress templates, lighter header"
```

---

### Task 4: Build verification

**Step 1:** `cd frontend && npx tsc --noEmit`
**Step 2:** `cd frontend && npx next build`
**Step 3:** Fix any errors
**Step 4:** Final commit if needed
