# Thesis Workspace 全流程体验重设计

## 1. 概述

### 1.1 目标

重新设计 thesis（本科毕业论文）workspace 的前后端体验，从当前的"聊天框为主"模式，转变为"工具卡片式工作台 + 模块内引导"模式，体现 workspace 定制化的差异价值。

### 1.2 核心设计原则

1. **Workspace 是工具箱，不是流水线**：所有功能模块平等可达，不强制使用顺序
2. **模块内部可有引导**：如"论文写作"内部有大纲→全文两个阶段，但用户可以从已有大纲直接进入全文
3. **AI 是辅助角色，不是主角**：工作台围绕具体任务组织，而非围绕聊天框
4. **产出落 artifact**：所有模块的产出统一落入 artifact 体系，跨模块可复用

### 1.3 设计范围

本次设计覆盖 thesis workspace 的完整前端交互和必要的后端改动。设计完成后，其他 workspace 类型（sci / proposal / software_copyright / patent）可照抄此模式。

---

## 2. Workspace 首页：工具卡片仪表盘

### 2.1 布局结构

用户打开 thesis workspace 后看到的第一屏。

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 我的空间]  本科毕业论文 · 计算机科学                    │
│               "基于深度学习的图像分割研究"                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  功能模块 (3列网格)                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │ 🔬 Deep      │ │ 📚 文献管理   │ │ 📋 开题调研  │     │
│  │   Research   │ │              │ │              │     │
│  │ 多智能体协作  │ │ 搜索、导入    │ │ 背景分析     │     │
│  │ 文献+空白+创意│ │ 管理参考文献  │ │ 研究现状梳理  │     │
│  │              │ │              │ │              │     │
│  │ ✅ 已完成     │ │ 18 篇文献    │ │ 未开始       │     │
│  │  3个研究创意  │ │ [管理 →]     │ │ [开始 →]     │     │
│  │ [查看结果 →]  │ │              │ │              │     │
│  └──────────────┘ └──────────────┘ └──────────────┘     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │ 📝 论文写作   │ │ 📊 图表生成   │ │ 📄 编译导出  │     │
│  │              │ │              │ │              │     │
│  │ 大纲规划     │ │ 流程图、数据  │ │ LaTeX 编译   │     │
│  │ → 全文生成   │ │ 可视化图表   │ │ PDF 预览导出  │     │
│  │              │ │              │ │              │     │
│  │ ● 大纲已完成  │ │ 未开始       │ │ 未开始       │     │
│  │ [继续写作 →]  │ │ [开始 →]     │ │ [开始 →]     │     │
│  └──────────────┘ └──────────────┘ └──────────────┘     │
│                                                          │
│  最近产出                                     [查看全部]  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 💡 研究创意: 轻量级分割网络设计         3小时前    │   │
│  │ 📋 论文大纲 v1                        昨天       │   │
│  │ 📚 Deep Research 文献报告              2天前      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2.2 功能模块顺序

按本科毕业论文的自然工作流排列，但不强制顺序：

| 顺序 | 模块 | 核心功能 |
|------|------|----------|
| 1 | 🔬 Deep Research | 多智能体协作：文献侦察 + 研究空白分析 + 创意生成 |
| 2 | 📚 文献管理 | 搜索、导入、管理参考文献 |
| 3 | 📋 开题调研 | 背景分析、研究现状梳理、开题报告生成 |
| 4 | 📝 论文写作 | 大纲生成 → 全文写作（内部两阶段融合） |
| 5 | 📊 图表生成 | 流程图、数据可视化图表 |
| 6 | 📄 编译导出 | LaTeX 编译、PDF 预览、多格式导出 |

### 2.3 卡片设计要点

- **状态感知**：卡片根据 artifact/task 数据显示真实进度（"未开始" / "大纲已完成" / "3个研究创意"等）
- **行动按钮语义化**：根据状态变化 —— "开始" / "继续写作" / "查看结果"
- **卡片数据来源**：由后端 registry + dashboard 接口驱动，不同 workspace type 展示不同卡片集合
- **最近产出**：底部展示该 workspace 的 artifact 时间线，跨模块统一

### 2.4 交互行为

- 点击卡片或行动按钮 → 进入该模块的专属工作区（全屏视图，顶部有"返回工作台"）
- 所有卡片同时可点击，无强制前置依赖

---

## 3. Deep Research 工具工作区

### 3.1 布局结构

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  Deep Research                            │
├─────────────────────────────────┬────────────────────────┤
│                                 │                        │
│  主工作区 (flex:1)              │  结果面板 (400px)       │
│                                 │  (生成前隐藏，          │
│  输入区 → 进度区 →              │   生成中/后展开)        │
│  Agent 思考流 → 最终报告        │                        │
│                                 │  Tab 切换:              │
│                                 │  [文献][空白][趋势][创意]│
│                                 │                        │
└─────────────────────────────────┴────────────────────────┘
```

### 3.2 三个 UI 状态

**状态 1 — 未开始**：
- 主工作区显示输入表单（研究方向、初步想法、上传核心文献、联网搜索开关）
- 结果面板隐藏，主工作区占满宽度

**状态 2 — 生成中**：
- 结果面板展开，实时填充数据（文献、空白、趋势、创意逐步出现）
- 主工作区显示阶段进度条（Scout → TrendSpotter → GapMiner → Synthesizer）
- 主工作区下方显示 Agent 思考流面板
- 支持取消

**状态 3 — 已完成**：
- 结果面板展示完整结果，按 Tab 切换
- 主工作区显示最终报告（Markdown 渲染）+ 下载/复制按钮
- 创意卡片支持"保留到知识库"操作

### 3.3 输入区

```
研究方向 (必填)
[________________________]

初步想法 (可选)
[________________________]

上传核心文献 (可选, 最多10个)
[拖拽或点击上传 PDF/Word/MD]

☐ 启用联网搜索

[🔬 开始 Deep Research]
```

### 3.4 Agent 思考流面板

深色背景终端风格，展示 Agent 的工作过程，提升"高级感"：

```
┌─ Agent 思考流 ──────────────────────────┐
│  (深色背景, 等宽字体, 自动滚动到底部)    │
│                                          │
│  🤖 Scout-1                             │
│  💭 搜索关键词:                          │
│     "image segmentation lightweight"     │
│  🔍 正在检索 Semantic Scholar API...     │
│  ✅ 发现 23 篇相关论文                   │
│                                          │
│  🤖 Gap-Miner                           │
│  💭 分析论文间的研究空白                 │
│  📊 识别到 5 个潜在空白:                 │
│     1. 边缘设备实时推理...               │
│     2. 小样本场景泛化...                 │
│                                          │
└──────────────────────────────────────────┘
```

### 3.5 文献注入选择面板

Deep Research 完成后，结果面板"文献"Tab 中提供 [注入文献管理 →] 按钮，点击弹出选择面板：

```
┌─ 文献注入选择 ─────────────────────────────────────────┐
│                                                          │
│  Deep Research 共发现 23 篇论文，选择要导入文献管理的:     │
│  [全选] [取消全选]  已选: 8/23     [按引用数排序 ▼]      │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ☑ U-Net: Convolutional Networks for Biomedical   │   │
│  │   Image Segmentation                             │   │
│  │   Ronneberger et al. · 2015 · 引用: 42,156       │   │
│  │   Q1 · MICCAI                                    │   │
│  │   ▸ 摘要: We present a network architecture...   │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ ☑ Segment Anything                               │   │
│  │   Kirillov et al. · 2023 · 引用: 8,234           │   │
│  │   Q1 · ICCV                                      │   │
│  │   ▸ 摘要: (点击展开)                              │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ ...                                               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│                    [取消]    [导入选中的 8 篇到文献管理]   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**设计要点**：
- 每篇论文显示：标题、作者、年份、引用数、分区（Q1/Q2）、期刊/会议名
- 摘要默认折叠，点击 ▸ 展开
- 支持全选/取消全选、排序（引用数/年份/相关度）
- 前端组件预留接口，后端导入逻辑后续实现

**前端接口预留**：

```typescript
interface LiteratureInjectionPanelProps {
  papers: DeepResearchPaper[]
  onConfirm: (selectedIds: string[]) => void
  onCancel: () => void
}

interface DeepResearchPaper {
  id: string
  title: string
  authors: string[]
  year: number
  citations: number
  quartile?: string          // "Q1" | "Q2" | ...
  venue?: string
  abstract?: string
  doi?: string
  source: string             // "semantic_scholar" | "arxiv" | ...
}
```

### 3.6 与后端的对接

- 后端已有 `DeepResearchSkillV2`，走 skill 执行路径（task_type = `deep_research`）
- 进度通过 task polling 获取（四阶段）
- 产出保存为 artifact，返回 `refresh_targets: ["artifacts"]`
- 文献注入预留接口：`POST /workspaces/{id}/literature/import`（body: `{ source: "deep_research", paper_ids: [...] }`）

---

## 4. 文献管理工具工作区

### 4.1 布局结构

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  文献管理                    [+ 添加文献]  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  统计: 共 18 篇 │ 核心文献 5 篇 │ 来源: DR 12 / 手动 6   │
│                                                          │
│  [搜索文献...]   [全部 ▼] [来源 ▼] [分区 ▼] [年份 ▼]    │
│                                                          │
│  文献列表 (卡片式)                                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ⭐ 论文标题                                       │   │
│  │   作者 · 年份 · 引用数                             │   │
│  │   分区 · 期刊/会议 · 来源标签                      │   │
│  │   ▸ 摘要                           [⭐] [删除]    │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ ...                                               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 4.2 设计要点

- **来源追踪**：每篇文献标注来源（Deep Research / 手动导入 / DOI 导入）
- **核心文献标记**：⭐ 标记为核心文献，论文写作时优先引用
- **筛选和搜索**：按来源、分区、年份筛选，全文搜索
- **添加文献**：支持手动输入、上传 PDF、DOI 导入三种方式
- **轻量设计**：重管理不重分析，分析能力在 Deep Research 中

---

## 5. 开题调研工具工作区

### 5.1 布局结构

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  开题调研                                  │
├──────────────────────────────┬───────────────────────────┤
│                              │                           │
│  左侧输入区 (320px)          │  中央内容区 (flex:1)       │
│                              │                           │
│  输入表单:                   │  生成前: 空状态引导        │
│  - 研究主题 (必填)           │  生成中: 流式分段输出      │
│  - 研究创意 (可选,            │  生成后: Markdown 渲染报告 │
│    可从 DR 选择)             │          + 操作栏          │
│  - 报告类型:                 │                           │
│    ○ 开题报告               │                           │
│    ○ 文献综述报告            │                           │
│    ○ 研究可行性分析          │                           │
│  - [生成报告]                │                           │
│                              │                           │
│  上下文预览:                 │  操作栏:                   │
│  - 将使用的 DR 创意/文献     │  [编辑] [重新生成]         │
│                              │  [下载 Word] [复制]        │
│                              │  [保存到知识库]            │
│                              │                           │
└──────────────────────────────┴───────────────────────────┘
```

### 5.2 设计要点

- **自动利用已有上下文**：从 workspace 的 Deep Research 创意、文献库自动获取素材，左下角预览将使用的上下文
- **多种报告类型**：同一个模块支持生成不同类型的报告
- **生成后可编辑**：完成后支持在 Markdown 编辑器中直接修改
- **产出为 artifact**：保存到知识库，后续论文写作时可作为参考上下文

---

## 6. 论文写作工具工作区

这是最核心的模块，内部融合大纲规划和全文写作两个阶段。

### 6.1 进入逻辑

```
用户点击"论文写作"卡片
    ↓
检测是否已有大纲 (artifact 查询)
    ↓
┌─ 有大纲 ──────────────────────────────┐
│  弹窗:                                │
│  "检测到已有论文大纲 (3小时前生成)"    │
│                                        │
│  [使用已有大纲，直接写全文]  → Step 2  │
│  [编辑已有大纲]              → Step 1  │
│  [重新生成大纲]              → Step 1  │
└────────────────────────────────────────┘
┌─ 无大纲 ──────────────────────────────┐
│  直接进入 Step 1                       │
└────────────────────────────────────────┘
```

### 6.2 Step 1：大纲规划

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  论文写作                                  │
│ [● ① 大纲规划 ─────────── ○ ② 全文写作]                  │
├──────────────────────────────┬───────────────────────────┤
│                              │                           │
│  左侧输入区 (320px)          │  中央内容区 (flex:1)       │
│                              │                           │
│  输入表单:                   │  生成前: 空状态引导        │
│  - 研究主题 (必填)           │  生成中: 流式卡片预览      │
│  - 具体研究创意 (可选,        │          (摘要卡 + 大纲卡) │
│    可从 DR 下拉选择)         │  生成后: 可视化大纲编辑器  │
│  - [生成论文大纲]            │                           │
│                              │                           │
│  上下文预览:                 │                           │
│  - 选中的 DR 创意详情        │                           │
│                              │                           │
└──────────────────────────────┴───────────────────────────┘
```

**生成时不联网搜索**：后端自动从 workspace 已有产出（DR 创意、文献、开题调研结果）获取上下文。

**可视化大纲编辑器**（生成完成后）：

```
┌─ 中央内容区 ────────────────────────────────────────────┐
│                                                          │
│  ┌─ 摘要区 ───────────────────────────────────────────┐ │
│  │ 📄 摘要                                    [编辑]  │ │
│  │ 摘要正文内容...                                    │ │
│  │ 关键词: 关键词1, 关键词2, 关键词3                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ 章节大纲 ─────────────────────────────────────────┐ │
│  │                                                      │ │
│  │  ▼ 第一章 绪论                    约 3,000 字 [编辑] │ │
│  │    定位: 介绍研究背景和意义                          │ │
│  │    ├─ 1.1 研究背景                                  │ │
│  │    ├─ 1.2 研究目的与意义                             │ │
│  │    └─ 1.3 论文结构安排                               │ │
│  │                                                      │ │
│  │  ▶ 第二章 文献综述                 约 5,000 字 [编辑] │ │
│  │  ▶ 第三章 研究方法                 约 4,000 字 [编辑] │ │
│  │  ▶ 第四章 实验与结果分析           约 5,000 字 [编辑] │ │
│  │  ▶ 第五章 结论与展望               约 2,000 字 [编辑] │ │
│  │                                                      │ │
│  │  总计约 19,000 字                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  [重新生成大纲]              [确认大纲，进入全文写作 →]   │
└──────────────────────────────────────────────────────────┘
```

**编辑态**（点击章节 [编辑]）：

```
▼ 第一章 绪论                              [保存] [取消]
  标题: [绪论________________________]
  定位: [介绍研究背景和意义__________]
  目标字数: [3000]
  核心论点:
    • [论点1___________________________] [×]
    • [论点2___________________________] [×]
    [+ 添加论点]
  小节:
    1.1 [研究背景_____________________]
    1.2 [研究目的与意义_______________]
    1.3 [论文结构安排_________________]
    [+ 添加小节]
```

### 6.3 Step 2：全文写作

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  论文写作                                  │
│ [✅ ① 大纲规划 ─────────── ● ② 全文写作]                 │
├──────────────────────────────┬───────────────────────────┤
│                              │                           │
│  左侧章节导航 (280px)        │  中央编辑区 (flex:1)       │
│                              │                           │
│  章节列表:                   │  当前章节标题              │
│  ✅ 第一章 绪论              │                           │
│     2,847 / 3,000 字        │  工具栏:                   │
│  🔄 第二章 文献综述          │  [AI续写] [重写] [插入引用] │
│     ████░░ 2,100/5,000      │                           │
│  ⏳ 第三章 研究方法          │  Markdown 编辑器           │
│     未开始                   │  (富文本/源码切换)         │
│  ⏳ 第四章 实验与结果        │  实时编辑 + 流式生成       │
│     未开始                   │                           │
│  ⏳ 第五章 结论与展望        │  底部章节信息:             │
│     未开始                   │  字数 / 引用数 / 状态      │
│                              │                           │
│  生成控制:                   │                           │
│  ☐ 启用 AI 配图              │                           │
│  [▶ 生成当前章节]            │                           │
│  [▶▶ 生成全部剩余章节]       │                           │
│                              │                           │
└──────────────────────────────┴───────────────────────────┘
```

**章节状态图标**：✅ 已完成 / 🔄 生成中 / ⏳ 未开始 / ✏️ 已手动修改

**不联网搜索文献**：直接使用文献库中的文献。如果文献不足，弹窗提示：

```
┌─ 弹窗 ────────────────────────────────┐
│                                        │
│  ⚠️ 文献库中仅有 3 篇文献，            │
│  可能影响论文的引用质量和内容深度。      │
│                                        │
│  建议补充至 10 篇以上再开始生成。       │
│                                        │
│  [前往文献管理，手动导入]               │
│  [启动 Deep Research 自动检索]          │
│  [仍然继续生成]                         │
│                                        │
└────────────────────────────────────────┘
```

- "前往文献管理" → 跳回 workspace 首页文献管理卡片
- "启动 Deep Research" → 跳回 workspace 首页 Deep Research 卡片
- "仍然继续" → 忽略警告，用现有文献继续

---

## 7. 图表生成工具工作区

### 7.1 布局结构

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  图表生成                                  │
├──────────────────────────────┬───────────────────────────┤
│                              │                           │
│  左侧配置区 (320px)          │  中央预览区 (flex:1)       │
│                              │                           │
│  图表类型:                   │  图表渲染预览              │
│  ○ 流程图 / 架构图           │  (SVG / PNG)              │
│  ○ 数据可视化图表            │                           │
│  ○ 概念示意图               │  操作:                    │
│                              │  [重新生成] [下载 PNG]     │
│  图表描述:                   │  [下载 SVG] [插入论文]     │
│  [多行文本输入]              │                           │
│                              │                           │
│  关联章节 (可选):             │                           │
│  [第三章 研究方法 ▼]          │                           │
│                              │                           │
│  [生成图表]                  │                           │
│                              │                           │
│  已生成图表:                 │                           │
│  📊 系统架构图    ch.3       │                           │
│  📊 实验流程图    ch.4       │                           │
│  (点击切换预览)              │                           │
│                              │                           │
└──────────────────────────────┴───────────────────────────┘
```

### 7.2 设计要点

- 三种图表类型对应后端三种生成策略（mermaid / python matplotlib / AI 生成）
- 可关联论文具体章节，[插入论文] 将图表关联到对应章节
- 左下角列出已生成图表历史，点击切换预览

---

## 8. 编译导出工具工作区

### 8.1 布局结构

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│ [← 返回工作台]  编译导出                                  │
├──────────────────────────────┬───────────────────────────┤
│                              │                           │
│  左侧配置区 (280px)          │  中央预览区 (flex:1)       │
│                              │                           │
│  论文完成度:                 │  PDF 预览                  │
│  ✅ 第一章 2,847 字          │  (iframe 渲染)             │
│  ✅ 第二章 4,923 字          │                           │
│  ✅ 第三章 3,812 字          │                           │
│  🔄 第四章 写作中            │                           │
│  ⏳ 第五章 未开始            │                           │
│  总字数: 11,582              │                           │
│  引用: 23 篇 / 图表: 4 个   │                           │
│                              │  操作:                    │
│  编译选项:                   │  [下载 PDF] [下载 Word]    │
│  LaTeX 模板:                 │  [下载 LaTeX 源码]         │
│  [学校毕业论文模板 ▼]        │  [复制全文 Markdown]       │
│  编译器:                     │                           │
│  ○ XeLaTeX (推荐)            │                           │
│  ○ pdfLaTeX                  │                           │
│  参考文献格式:                │                           │
│  [GB/T 7714 ▼]               │                           │
│  [编译预览]                  │                           │
│                              │                           │
└──────────────────────────────┴───────────────────────────┘
```

### 8.2 设计要点

- 左上角显示论文各章节完成度
- 支持 LaTeX 模板选择（后续可扩展各高校模板）
- 编译后右侧直接 PDF 预览
- 多格式导出：PDF、Word、LaTeX 源码、Markdown

---

## 9. 后端改动

### 9.1 新增接口

#### Dashboard 概览接口

```python
# GET /workspaces/{id}/dashboard
# 返回各模块状态摘要，从现有 artifact/task 记录聚合

{
  "modules": [
    {
      "id": "deep_research",
      "status": "completed",
      "summary": {"ideas_count": 3, "papers_count": 18}
    },
    {
      "id": "literature",
      "status": "completed",
      "summary": {"total": 18, "core": 5}
    },
    {
      "id": "thesis_writing",
      "status": "in_progress",
      "summary": {"outline_done": true, "chapters_done": 1, "chapters_total": 5}
    },
    ...
  ],
  "recent_artifacts": [...]
}
```

#### 文献注入接口（预留）

```python
# POST /workspaces/{id}/literature/import
# 预留接口，暂不实现具体逻辑

{
  "source": "deep_research",
  "paper_ids": ["id1", "id2", ...]
}
```

### 9.2 论文写作后端拆分

**现状**：thesis workflow 是 LangGraph 6 节点状态机，一次性从头跑到尾。

**拆分为两个阶段**：

**阶段 1：大纲生成**
- 独立为一个 task
- 输入：研究主题 + 创意 + workspace 已有上下文（自动获取）
- 输出：结构化大纲 JSON + 摘要（保存为 artifact）
- 不走完整 thesis workflow

**阶段 2：全文写作**
- 支持逐章提交任务（`chapter_index` 参数）
- 输入：大纲 artifact + 文献库引用
- 输出：章节内容（逐章保存为 artifact）
- 文献不足时返回 warning 而非直接联网搜索

```python
# POST /workspaces/{id}/features/thesis_writing/execute
{
  "params": {
    "action": "generate_outline",      # 或 "write_chapter" 或 "write_all"
    "chapter_index": 2,                # write_chapter 时指定
    "enable_figures": true
  }
}

# 文献不足时返回
{
  "task_id": null,
  "warning": "literature_insufficient",
  "detail": {"current": 3, "recommended": 10}
}
```

### 9.3 不需要改动的部分

- registry / handler_key / runtime 机制：继续沿用
- artifact 体系：大纲、章节、报告等都落 artifact，现有 taxonomy 已覆盖
- refresh_targets 机制：继续沿用
- Deep Research skill：后端已完整实现，前端对接即可
- task polling：继续沿用现有轮询机制

### 9.4 改动复杂度总结

| 改动类型 | 内容 | 复杂度 |
|---------|------|--------|
| 新增接口 | dashboard 概览接口 | 低 |
| 新增接口 | 文献注入接口（预留） | 低 |
| 拆分逻辑 | 大纲生成独立为单独 task | 中 |
| 改造逻辑 | 全文写作支持逐章生成 | 中 |
| 改造逻辑 | 文献不足检测 + warning 返回 | 低 |
| 不动 | registry / runtime / artifact / refresh | — |

---

## 10. Registry 改动计划

### 10.1 现有 THESIS_FEATURES 与新设计的映射

现有 registry 中的 thesis feature 定义需要调整以匹配新的模块划分：

| 新模块 | 现有 registry feature | 改动 |
|--------|----------------------|------|
| Deep Research | 不在 registry 中（走 skill 路径） | 新增注册，task_type 设为 `deep_research` |
| 文献管理 | `literature`（文献综述，语义不同） | 重命名为 `literature_management`，handler 改为管理型 |
| 开题调研 | 无 | 新增 `opening_research` |
| 论文写作 | `outline` + `chapter`（两个独立 feature） | 合并为 `thesis_writing`，通过 `action` 参数区分大纲/章节 |
| 图表生成 | `figure` | 保留，handler_key 不变 |
| 编译导出 | `compile` + `export`（两个独立 feature） | 合并为 `compile_export` |

### 10.2 新的 THESIS_FEATURES 定义

```python
THESIS_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="deep_research",
        name="Deep Research",
        description="多智能体协作：文献侦察、研究空白分析、创意生成",
        icon="flask",
        agent="deep_research",
        agent_label="DeepResearch",
        handler_key="thesis.deep_research",
        task_type="deep_research",        # 走 skill 执行路径
        panel="deep_research_panel",
        stages=(_stage("scout", "搜索文献"), _stage("trend", "趋势分析"),
                _stage("gap", "空白挖掘"), _stage("synthesize", "创意综合")),
        color="blue",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="literature_management",
        name="文献管理",
        description="搜索、导入、管理参考文献",
        icon="book",
        agent="librarian",
        agent_label="Librarian",
        handler_key="thesis.literature_management",
        task_type="workspace_feature",
        panel=None,                       # 纯管理型，无异步 task
        stages=(),
        color="emerald",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="opening_research",
        name="开题调研",
        description="背景分析、研究现状梳理、开题报告生成",
        icon="search",
        agent="scout",
        agent_label="Scout",
        handler_key="thesis.opening_research",
        task_type="workspace_feature",
        panel="opening_research_panel",
        stages=(_stage("collect", "收集资料"), _stage("analyze", "分析整理"),
                _stage("generate", "生成报告")),
        color="amber",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="thesis_writing",
        name="论文写作",
        description="大纲规划与全文写作",
        icon="pen",
        agent="thesis_writer",
        agent_label="ThesisWriter",
        handler_key="thesis.thesis_writing",
        task_type="thesis_generation",    # 走 thesis workflow 路径
        panel="thesis_writing_panel",
        stages=(_stage("outline", "大纲规划"), _stage("writing", "全文写作")),
        color="purple",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="figure_generation",
        name="图表生成",
        description="流程图、数据可视化图表生成",
        icon="chart",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="thesis.figure_generation",
        task_type="workspace_feature",
        panel="figure_panel",
        stages=(_stage("plan", "规划图表"), _stage("generate", "生成图表")),
        color="rose",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="compile_export",
        name="编译导出",
        description="LaTeX 编译、PDF 预览、多格式导出",
        icon="file",
        agent="thesis_writer",
        agent_label="ThesisWriter",
        handler_key="thesis.compile_export",
        task_type="workspace_feature",
        panel="compile_panel",
        stages=(_stage("assemble", "组装 LaTeX"), _stage("compile", "编译 PDF")),
        color="cyan",
    ),
)
```

### 10.3 Deep Research 的双路径接入

Deep Research 在 registry 中注册（`task_type="deep_research"`），但执行时仍走现有的 `SkillTaskHandler → SkillExecutor → DeepResearchSkillV2` 路径。`workspace_feature_handler.py` 中的分流逻辑需要增加对 `deep_research` task_type 的识别：

```python
async def _dispatch_task(task_type, payload, progress):
    if task_type == "thesis_generation":
        return await execute_thesis_generation(payload, progress)
    if task_type == "deep_research":
        return await execute_skill_task("deep-research", payload, progress)
    if task_type == "workspace_feature":
        return await execute_workspace_feature(payload, progress)
```

这样 Deep Research 既能通过 `/features` 接口被前端发现（registry 注册），又能复用已有的 skill 执行基础设施。

---

## 11. Thesis Workflow 改造详细方案

### 11.1 改造策略

保留现有 LangGraph workflow 框架，但拆分为可独立调用的两个入口。不重写，而是新增路由层。

### 11.2 大纲生成（action: "generate_outline"）

**执行路径**：
```
features router → task_service.submit_task(task_type="thesis_generation")
→ workspace_feature_handler._dispatch_task()
→ execute_thesis_generation()
→ 检查 action == "generate_outline"
→ 调用新增的 generate_outline_only() 函数
```

**generate_outline_only() 实现要点**：
- 不走完整 LangGraph 6 节点工作流
- 直接调用 LLM（thesis_writer agent）生成结构化大纲
- 输入：研究主题 + 创意 + workspace 上下文（从 artifact 自动获取）
- 输出：大纲 JSON + 摘要文本，保存为 `framework_outline` 类型的 artifact
- 进度：简单的 0% → 50% → 100% 三段

### 11.3 全文写作（action: "write_chapter" / "write_all"）

**执行路径**：
```
features router → task_service.submit_task(task_type="thesis_generation")
→ workspace_feature_handler._dispatch_task()
→ execute_thesis_generation()
→ 检查 action == "write_chapter" 或 "write_all"
→ 调用改造后的 thesis workflow
```

**改造要点**：

1. `execute_thesis_generation()` 增加 `action` 参数路由：
```python
async def execute_thesis_generation(payload, progress):
    action = payload.get("action", "write_all")
    if action == "generate_outline":
        return await generate_outline_only(payload, progress)
    elif action == "write_chapter":
        return await write_single_chapter(payload, progress)
    elif action == "write_all":
        return await write_all_chapters(payload, progress)
```

2. `write_single_chapter()`：
   - 从 artifact 加载大纲
   - 从文献库加载引用
   - 只执行 `section_writer_node` 一次（指定 chapter_index）
   - 产出保存为 `thesis_chapter` artifact
   - 返回 `refresh_targets: ["artifacts"]`

3. `write_all_chapters()`：
   - 循环调用 `section_writer_node`，逐章生成
   - 每章完成时保存 artifact 并更新进度

4. 文献不足检测（在 router 层）：
```python
# features.py execute_feature() 中
if action in ("write_chapter", "write_all"):
    lit_count = await count_workspace_literature(workspace_id)
    if lit_count < LITERATURE_THRESHOLD:
        return ExecuteResponse(
            task_id=None,
            warning="literature_insufficient",
            detail={"current": lit_count, "recommended": LITERATURE_THRESHOLD}
        )
```

### 11.4 _is_thesis_payload 调整

现有的 `_is_thesis_payload()` 判断逻辑保持不变（检查 task_type == "thesis_generation"），但 `execute_thesis_generation()` 内部增加 `action` 分流。这样对现有代码的侵入最小。

---

## 12. 文献管理后端设计

### 12.1 数据模型

文献数据不复用 artifact 体系（artifact 是产出物，文献是输入物）。新增独立的 `workspace_literature` 表：

```python
class WorkspaceLiterature(Base):
    __tablename__ = "workspace_literature"

    id: str                    # UUID
    workspace_id: str          # FK → workspaces.id
    title: str
    authors: list[str]         # JSON array
    year: int | None
    citations: int | None
    venue: str | None          # 期刊/会议名
    quartile: str | None       # "Q1" | "Q2" | ...（后续实现）
    abstract: str | None
    doi: str | None
    source: str                # "deep_research" | "manual" | "doi_import" | "pdf_upload"
    is_core: bool = False      # 核心文献标记
    created_at: datetime
    updated_at: datetime
```

### 12.2 CRUD 接口

```python
# 文献列表
GET /workspaces/{id}/literature
  ?source=deep_research     # 可选筛选
  &is_core=true             # 可选筛选
  → { "items": [...], "total": 18, "core_count": 5 }

# 添加文献（手动输入）
POST /workspaces/{id}/literature
  { "title": "...", "authors": [...], "year": 2024, ... }

# 批量导入（从 Deep Research）
POST /workspaces/{id}/literature/import
  { "source": "deep_research", "paper_ids": [...] }

# 更新文献（标记核心等）
PATCH /workspaces/{id}/literature/{lit_id}
  { "is_core": true }

# 删除文献
DELETE /workspaces/{id}/literature/{lit_id}

# 文献数量（供文献不足检测使用）
GET /workspaces/{id}/literature/count
  → { "total": 18, "core": 5 }
```

### 12.3 与 Deep Research 的关联

Deep Research skill 执行完成后，论文数据保存在 task result 中。文献注入面板从 task result 中读取论文列表，用户选择后调用 `POST /literature/import` 批量导入。导入时从 task result 中提取论文元数据写入 `workspace_literature` 表。

---

## 13. Artifact 类型补充

### 13.1 现有类型与模块产出的映射

| 模块 | 产出物 | Artifact Type | 状态 |
|------|--------|---------------|------|
| Deep Research | 文献报告 | `literature_search_results` | ✅ 已有 |
| Deep Research | 研究创意 | `research_ideas` | ✅ 已有 |
| 开题调研 | 开题报告 | `opening_report` | ❌ **需新增** |
| 开题调研 | 文献综述报告 | `literature_review` | ✅ 已有 |
| 开题调研 | 可行性分析 | `feasibility_analysis` | ❌ **需新增** |
| 论文写作 | 论文大纲 | `framework_outline` | ✅ 已有 |
| 论文写作 | 章节内容 | `thesis_chapter` | ❌ **需新增** |
| 图表生成 | 生成的图表 | `figure` | ✅ 已有 |
| 编译导出 | PDF 文件 | `paper_draft` | ✅ 已有 |

### 13.2 需要在 ArtifactType 枚举中新增

```python
# backend/src/artifacts/types.py 新增：
OPENING_REPORT = "opening_report"
FEASIBILITY_ANALYSIS = "feasibility_analysis"
THESIS_CHAPTER = "thesis_chapter"
```

同步更新：
- `backend/src/artifacts/types.py`（共享 taxonomy）
- `backend/src/database/models/artifact.py`（ORM 验证，如有）
- `frontend/.../KnowledgePanel.tsx`（icon/color 映射）

---

## 14. 前端架构改动

### 14.1 路由设计

每个工具工作区是独立的子路由页面：

```
/workspaces/[id]                          → Workspace 首页（卡片仪表盘）
/workspaces/[id]/deep-research            → Deep Research 工作区
/workspaces/[id]/literature               → 文献管理工作区
/workspaces/[id]/opening-research         → 开题调研工作区
/workspaces/[id]/thesis-writing           → 论文写作工作区
/workspaces/[id]/figure-generation        → 图表生成工作区
/workspaces/[id]/compile-export           → 编译导出工作区
```

### 14.2 与现有组件的关系

| 现有组件 | 处置方式 |
|---------|---------|
| `ChatPanel.tsx` | 降级为辅助角色，不再是主交互入口。可在各工具工作区中作为"AI 助手"侧边栏组件复用 |
| `KnowledgePanel.tsx` | 保留，改造为 Workspace 首页的"最近产出"区域。各工具工作区不再直接引用 |
| `LiteraturePanel.tsx` | 内容合并到新的文献管理工作区组件中 |
| `SkillSelector.tsx` | 替换为 Workspace 首页的工具卡片网格 |

### 14.3 新增前端组件

```
frontend/app/(workbench)/workspaces/[id]/
├── page.tsx                              # 改造为卡片仪表盘
├── deep-research/page.tsx                # Deep Research 工作区
├── literature/page.tsx                   # 文献管理工作区
├── opening-research/page.tsx             # 开题调研工作区
├── thesis-writing/page.tsx               # 论文写作工作区
├── figure-generation/page.tsx            # 图表生成工作区
├── compile-export/page.tsx               # 编译导出工作区
└── components/
    ├── ModuleCard.tsx                    # 通用工具卡片组件
    ├── RecentArtifacts.tsx               # 最近产出列表
    ├── OutlineEditor.tsx                 # 可视化大纲编辑器
    ├── ChapterNav.tsx                    # 章节导航面板
    ├── ChapterEditor.tsx                 # 章节 Markdown 编辑器
    ├── AgentThoughtStream.tsx            # Agent 思考流面板
    ├── LiteratureInjectionPanel.tsx      # 文献注入选择面板
    └── LiteratureInsufficiencyDialog.tsx # 文献不足提示弹窗
```

### 14.4 状态管理

新增或改造的 store：

```typescript
// stores/dashboard.ts - Workspace 首页模块状态
interface DashboardState {
  modules: ModuleStatus[]
  recentArtifacts: Artifact[]
  fetchDashboard: (workspaceId: string) => Promise<void>
}

// stores/thesis-writing.ts - 论文写作状态
interface ThesisWritingState {
  currentStep: 1 | 2                    // 大纲 or 全文
  outline: OutlineData | null
  chapters: ChapterStatus[]
  currentChapterIndex: number
}

// stores/literature.ts - 文献管理状态
interface LiteratureState {
  items: Literature[]
  filters: LiteratureFilters
  fetchLiterature: (workspaceId: string) => Promise<void>
  importFromDeepResearch: (paperIds: string[]) => Promise<void>
}
```

### 14.5 模块间跳转的状态传递

文献不足弹窗跳转到文献管理或 Deep Research 时，通过 URL query 参数传递来源信息：

```
/workspaces/[id]/literature?from=thesis-writing&reason=insufficient
/workspaces/[id]/deep-research?from=thesis-writing&reason=insufficient
```

目标页面可根据 `from` 参数显示提示（如"论文写作需要更多文献，请补充后返回"），但不强制任何操作。

---

## 15. 图表生成与编译导出后端对接

### 15.1 图表生成后端

**现有能力**：
- `figure_planner_node` 和 `figure_generator_node` 已在 thesis workflow 中实现
- `ExecutionService` 已支持 `MERMAID_DIAGRAM`、`PYTHON_PLOT`、`AI_IMAGE` 三种执行类型
- 但 provider 实现尚不完整（mermaid-cli、matplotlib、kling API 需要对接）

**改动**：
- 将图表生成从 thesis workflow 中解耦，独立为 `thesis.figure_generation` handler
- handler 接收图表描述和类型，调用 `ExecutionService`
- 产出保存为 `figure` 类型 artifact，包含 `chapter_index` 元数据用于关联章节
- [插入论文] 操作：更新 artifact 的 metadata，添加 `linked_chapter` 字段

**接口**：
```python
# POST /workspaces/{id}/features/figure_generation/execute
{
  "params": {
    "description": "系统整体架构流程图",
    "type": "flowchart",           # flowchart | data_chart | concept
    "chapter_index": 3             # 可选，关联章节
  }
}
```

### 15.2 编译导出后端

**现有能力**：
- `assemble_latex_node` 和 `compile_latex_node` 已在 thesis workflow 中实现
- `LaTeX 模板` 和 `compile_latex()` 工具已完整
- 支持 xelatex 和 pdflatex

**改动**：
- 将编译功能从 thesis workflow 中解耦，独立为 `thesis.compile_export` handler
- handler 从 artifact 中收集所有已完成章节 + 大纲 + 图表
- 组装 LaTeX 并调用编译
- 新增模板选择参数和参考文献格式参数

**接口**：
```python
# POST /workspaces/{id}/features/compile_export/execute
{
  "params": {
    "template": "default",          # 后续扩展高校模板
    "compiler": "xelatex",          # xelatex | pdflatex
    "bib_style": "gbt7714",         # gbt7714 | apa | ieee
    "output_formats": ["pdf"]       # pdf, docx, latex_source
  }
}
```

---

## 16. 错误处理与边界情况

### 16.1 Deep Research 异常

| 场景 | 处理策略 |
|------|---------|
| API 配额耗尽 | 进度面板显示错误信息 + 重试按钮 |
| 网络超时 | Agent 思考流显示超时提示，支持重试 |
| 部分阶段失败 | 已完成阶段的结果保留展示，失败阶段标红并提示 |

### 16.2 论文写作异常

| 场景 | 处理策略 |
|------|---------|
| 单章生成失败 | 该章节标记为"生成失败"，其他章节不受影响，支持重试 |
| "生成全部"中途失败 | 已完成章节的 artifact 已保存不丢失，失败章节标记错误，可单独重试 |
| 大纲生成失败 | 显示错误信息 + 重试按钮，不影响 Step 1 表单内容 |

### 16.3 编译失败

| 场景 | 处理策略 |
|------|---------|
| LaTeX 语法错误 | 显示编译日志（错误行号 + 描述），用户可回到论文写作修改后重新编译 |
| 缺少章节 | 编译前检查，提示"第X章尚未完成，编译将不包含该章节内容"，用户确认后继续 |

### 16.4 模块间跳转状态保持

- 各工具工作区的状态通过 Zustand store 持久化（sessionStorage），跳转不丢失
- 论文写作的编辑器内容实时保存到 store，离开页面后返回可恢复
- 弹窗跳转使用 URL query 参数，不依赖内存状态传递

### 16.5 并发任务控制

- 同一 workspace 同一时间只允许一个 task 处于运行状态（后端 task_service 层面控制）
- 如果用户在模块 A 有任务运行中，进入模块 B 点击执行时，提示"当前有任务正在运行，请等待完成或取消后再操作"

---

## 17. DeepResearchPaper 数据结构与后端对齐

### 17.1 现有后端 Paper 结构

```python
# backend/src/skills/implementations/deep_research.py
@dataclass
class Paper:
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    citations: int | None
    url: str | None
    doi: str | None
    paper_id: str | None = None
```

### 17.2 前端接口调整

将 `quartile` 标记为可选字段，当前后端不提供该数据，后续通过 journal ranking 查询补充：

```typescript
interface DeepResearchPaper {
  id: string              // 对应 paper_id
  title: string
  authors: string[]
  year: number | null
  citations: number | null
  venue?: string
  abstract?: string
  doi?: string
  url?: string
  quartile?: string       // 后续实现，当前为 undefined
  source: string          // 从 skill 结果中推断
}
```

文献注入面板中，如果 `quartile` 为空则不显示分区标签。

---

## 18. 与现有架构的兼容性

### 10.1 完全复用的部分

- **Feature registry**：各模块在 registry 中注册，前端通过 `/features` 接口发现
- **Artifact 体系**：所有模块产出落 artifact，KnowledgePanel 展示
- **Task polling**：异步任务提交 + 轮询状态的模式不变
- **refresh_targets**：handler 返回刷新目标，前端统一消费

### 10.2 架构边界遵守

- Router 不写 feature 业务逻辑
- Registry 是 feature 元数据唯一来源
- 非 thesis feature 通过 handler_key 扩展
- Artifact 是 feature 输出的第一落点
- 前端刷新依赖 refresh_targets

### 10.3 后续其他 workspace 类型的复用

本次设计建立的模式可直接复用：
- **Workspace 首页**：卡片仪表盘模式，不同 workspace type 展示不同卡片集合
- **工具工作区**：左侧输入/导航 + 中央内容区的通用布局
- **模块内引导**：如论文写作的 Step 1 → Step 2 模式
- **上下文自动利用**：各模块自动从 workspace 已有产出获取素材
