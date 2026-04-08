# Homepage Enrichment + Workspace Page Simplification

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

**Date:** 2026-03-31
**Status:** Approved
**Goal:** Upgrade the homepage from a lightweight landing page to a full product showcase, and simplify the workspace list page by removing redundant sections.

## Context

The homepage (`/`) is currently a ~500-line marketing landing page with 4 sections (Hero, 4 capability cards, 5 workflow steps, CTA). It's the only public-facing surface — unauthenticated users hitting `/workspaces` get redirected to login. Despite being the sole product showcase, the homepage is light on content and has 3 redundant CTA entry points.

The workspace list page (`/workspaces`) has ~720 lines with a "Recent Workspaces" section (top 3) and an "All Workspaces" section (full list) that show the same data, plus a separate template quick-create area that takes up significant space.

## Design Decisions

### 1. Keep Two Separate Pages

Homepage = product showcase for unauthenticated/evaluating users.
Workspace page = functional tool for authenticated users.
These serve different mental models and should not be merged.

### 2. Homepage: Expand to Full Product Showcase

**Narrative arc:** Brand recognition → Philosophy resonance → Capability showcase → Trust building → Action conversion

#### Section 1: Hero (keep, simplify)
- Brand name + one-line positioning + single CTA button
- Right side: keep the existing stage preview card
- **Remove** the second CTA inside the card (reduce from 3 to 2 total entry points: Hero CTA + footer CTA)

#### Section 2: Design Philosophy (new)
4 principle cards, content sourced from README:
- **对话即工作流** — Not forms or buttons, but natural conversation to drive all work. AI proactively asks for what it needs.
- **阶段感知** — Each workspace has clear research stages (research → collection → structure → writing → review). The system knows where you are and recommends what's next.
- **单线程模型** — One workspace, one continuous conversation. No thread management. Context preserved through summarization + memory extraction.
- **成果驱动** — Every output (outlines, drafts, reviews) persisted as traceable Artifacts that accumulate into a research portfolio.

Each card: icon + title + 2-3 sentence description.

#### Section 3: Five Workspace Types (replaces current 4 capability cards)
5 type cards replacing the current 4 generic capability cards:
- 学位论文 (Thesis): icon + "深度调研 · 文献管理 · 大纲设计 · 论文撰写 · 图表生成 · 编译导出"
- 学术论文 (SCI/EI): icon + "文献检索 · 论文分析 · 章节写作 · 同行评审 · 期刊推荐"
- 研究计划 (Proposal): icon + "背景调研 · 实验设计 · 计划书撰写"
- 软件著作权 (Copyright): icon + "著作权材料 · 技术文档"
- 专利申请 (Patent): icon + "专利撰写 · 现有技术检索"

Each card shows the workspace type name, its icon, a brief description, and the list of available work modules.

#### Section 4: How It Works (keep, refine content)
5-step workflow, updated to match actual usage:
1. 创建工作区 — 选择类型和学科，一键创建
2. 对话引导 — AI 主动了解你的研究方向和需求
3. 智能调研 — 系统性检索文献，分析研究空白
4. 迭代写作 — 按阶段推进，每个产出可追溯
5. 成果交付 — 编译排版，符合学校/期刊规范

#### Section 5: Use Case Showcase (new)
2-3 scenario cards showing realistic usage:
- **硕士论文调研**: "从零开始确定研究方向，检索50+篇文献，生成综述报告"
- **SCI 论文投稿**: "从 research gap 到 revision response，全流程辅助"
- **基金申请**: "梳理技术路线，撰写创新性论证"

Each: scenario title + brief description + key outcome. No screenshots (static mockup data instead — simpler to maintain).

#### Section 6: Technical Capabilities (new)
A single row of key metrics/badges:
- 21 个 AI Skill
- 5 种工作区类型
- 8 个学科方向
- 模板导入
- 多模型支持

Compact, horizontal layout. Aimed at technical evaluators and institutional buyers.

#### Section 7: Footer CTA + Footer (keep)
Existing bottom CTA section + footer. No changes.

### 3. Workspace Page: Remove Redundancy

#### Remove "Recent Workspaces" section
The "Recent" section (top 3 cards, not searchable) is redundant with "All Workspaces" (full list, searchable, same sort order). Merge into a single list.

The most recently updated workspace gets a "最近" badge on its card — no separate section needed.

#### Compress template quick-create area
From: 5-column card grid (each with icon + label + description + "Create" link)
To: Single row of 5 compact buttons: `[学位论文+] [学术论文+] [研究计划+] [软著+] [专利+]`

Each button opens the create modal with that type pre-selected. Same functionality, ~1/4 the vertical space.

#### Simplify header
Remove LiquidGlassCard wrapper. Use a simpler header: title + workspace count badge + search + new button.

#### Result layout

```
┌──────────────────────────────────────────────────┐
│  标题「我的工作区」(N)    [搜索] [+ 新建工作区]     │
├──────────────────────────────────────────────────┤
│  [学位论文+] [学术论文+] [研究计划+] [软著+] [专利+] │
├──────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │ Card 1  │ │ Card 2  │ │ Card 3  │  (最近badge)│
│  │ (最近)  │ │         │ │         │            │
│  └─────────┘ └─────────┘ └─────────┘            │
│  ┌─────────┐ ┌─────────┐                        │
│  │ Card 4  │ │ Card 5  │                        │
│  └─────────┘ └─────────┘                        │
├──────────────────────────────────────────────────┤
│  创建弹窗（保持不变）                              │
└──────────────────────────────────────────────────┘
```

## Files to Modify

| File | Change |
|------|--------|
| `frontend/app/page.tsx` | Rewrite: 7-section product showcase |
| `frontend/app/workspaces/page.tsx` | Simplify: merge lists, compress templates, simplify header |

## No Backend Changes

This is a frontend-only redesign. No API changes, no new data requirements.
