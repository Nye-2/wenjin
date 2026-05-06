# Wenjin UI/UX 重设计规划

> 基于 Compute Architecture 重构后的前端界面重设计
> 更新时间：2026-04-29
> 状态：Planning

---

## 0. 为什么要重设计

架构迁移完成后，产品形态发生了根本变化：

| 维度 | 旧形态 | 新形态 |
|------|--------|--------|
| 核心交互区 | Thread 消息流堆一切 | Chat Dock + Compute Stage 双区协作 |
| 长任务展示 | 消息卡片嵌套 | Compute Stage 专用工作台 |
| 文件/日志 | 消息附件 | Sandbox 文件树 + 终端日志面板 |
| Review Gate | 消息确认卡片 | Compute Stage 内嵌 diff + apply/revert |
| 状态恢复 | 从 thread message 反推 | 从 ExecutionSession/ComputeSession 投影 |

旧 UI 没有为 Compute Stage 预留空间，ThreadPanel 承担了过多职责，ComputeStage.tsx 已膨胀到 44KB 单文件。需要一次系统性的界面重构。

---

## 1. 设计系统升级

### 1.1 设计哲学

**「问津」= 探路者的罗盘**

- **Chat Dock** 像罗盘——简洁、聚焦、只给方向。
- **Compute Stage** 像地图——信息密集、层次丰富、可缩放探索。
- **Knowledge Rail** 像笔记——安静、有序、随时查阅。

### 1.2 配色系统

保留品牌色核心，但为 Compute Stage 引入专门的深色工作面。

```
┌─────────────────────────────────────────────────────────────┐
│  品牌色（保持不变）                                            │
│  ─────────────────                                           │
│  ink    #132235  墨——最深文字                                 │
│  navy   #1F4263   Navy——主按钮、品牌标识                       │
│  teal   #2E6F6D  青——聚焦态、hover、成功                       │
│  cyan   #5C97A5  水——次要强调、标签                             │
│  brass  #A67C39  铜——警告、待确认、accent                       │
│  paper  #F7F4EE  纸——Chat Dock 背景                            │
│  wash   #EEF2F3  洗——elevated surface                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Compute Stage 专用深色工作面（新增）                           │
│  ─────────────────────────────────                               │
│  compute-bg-base      #0B0F14   深渊——最深背景                  │
│  compute-bg-elevated  #111820   井——卡片/面板背景               │
│  compute-bg-surface   #1A2330   潭——输入框、hover 态           │
│  compute-border       #232D3D   界——分割线                      │
│  compute-text-primary   #E8ECF2  主文字                        │
│  compute-text-secondary #8A94A6  次文字                        │
│  compute-text-muted     #5A6378  辅助文字                       │
│  compute-accent-cyan    #5C97A5  运行时高亮（与品牌 cyan 一致）  │
│  compute-accent-gold    #C8A050  警告/待确认                    │
│  compute-accent-green   #2D9D78  成功/完成                      │
│  compute-accent-red     #D14B4B  失败/错误                      │
└─────────────────────────────────────────────────────────────┘
```

> **为什么 Compute Stage 用深色？**
> 1. 长任务工作台需要长时间注视，深色减少 eye strain
> 2. 文件树、代码块、日志、终端等内容在深色底上对比度更好
> 3. 与 Chat Dock 的暖纸色形成视觉分区，用户 subconsciously 知道自己在哪个 plane
> 4. 与 Kimi Computer / Claude Artifacts / V0 等 AI 工作台的设计语言对齐

### 1.3 字体系统

当前使用系统默认字体，缺乏辨识度。引入精细化字体搭配：

```
Display / 大标题：Inter 600-700
  → 干净、现代、高可读性
  → 用于 workspace 标题、feature 名称、阶段标题

Body / UI 文字：Inter 400-500
  → 与 display 同族，保持统一
  → 用于按钮、标签、描述、表单

Mono / 代码与数据：JetBrains Mono 400-500
  → 技术感、等宽对齐
  → 用于文件路径、token count、日志、代码块、hash

Serif / 学术引用（可选）：Noto Serif SC
  → 保留问津的学术气质
  → 用于论文标题预览、引用块
```

Tailwind 配置：

```typescript
fontFamily: {
  display: ["Inter", "var(--font-sans)", "system-ui", "sans-serif"],
  sans: ["Inter", "var(--font-sans)", "system-ui", "sans-serif"],
  mono: ["JetBrains Mono", "var(--font-mono)", "monospace"],
  serif: ["var(--font-serif)", '"STSong"', '"SimSun"', "serif"],
}
```

### 1.4 间距系统

```
4px   xs   — 图标内边距、紧凑标签
8px   sm   — 按钮内边距、列表项间距
12px  md   — 卡片内边距、表单字段间距
16px  lg   — 面板内边距、段落间距
24px  xl   — 区块间距、section 分隔
32px  2xl  — 大模块间距
48px  3xl  — 页面级间距
```

### 1.5 圆角系统

```
4px   — 按钮、标签、badge
8px   — 输入框、小卡片
12px  — 面板、对话框
16px  — 大卡片、模态框
9999px — pill 按钮、头像
```

### 1.6 阴影与层级

```
z-0   Chat Dock 背景（paper）
z-10  Chat Dock 头部（glass）
z-20  Compute Stage 侧边栏
z-30  浮动操作按钮（FAB）
z-40  模态框、抽屉
z-50  Toast、全局提示
```

Glass morphism 保留但增强：
```css
.glass-chat {
  background: rgba(251, 248, 242, 0.85);
  backdrop-filter: blur(20px) saturate(120%);
  border-bottom: 1px solid rgba(31, 66, 99, 0.08);
}

.glass-compute {
  background: rgba(17, 24, 32, 0.85);
  backdrop-filter: blur(20px) saturate(110%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
```

### 1.7 动画系统

```
布局过渡：  400ms  cubic-bezier(0.16, 1, 0.3, 1)  — Apple 弹性缓出
状态切换：  200ms  cubic-bezier(0.4, 0, 0.2, 1)   — 标准 ease
微交互：    150ms  cubic-bezier(0.4, 0, 0.2, 1)   — 按钮、hover
进度动画：  300ms  linear                         — progress bar
骨架屏：    shimmer 1.5s ease-in-out infinite
```

---

## 2. 页面布局架构：Workspace Shell

### 2.1 整体结构

```
┌────────────────────────────────────────────────────────────────────────────┐
│  App Header (fixed, z-10)                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Logo    Workspace Selector    [Thread Tabs]    User Avatar        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┬────────────────────────────────────┬─────────────┐           │
│  │          │                                    │             │           │
│  │ Knowledge│      Compute Stage                 │  Chat Dock  │           │
│  │  Rail    │      (resizable)                   │ (resizable) │           │
│  │          │                                    │             │           │
│  │  240px   │      ┌────────────────────────┐   │             │           │
│  │  fixed   │      │  Phase Timeline        │   │  ┌───────┐  │           │
│  │  collapsible│   │  ┌──────────────────┐  │   │  │Header │  │           │
│  │          │      │  │ Runtime Blocks   │  │   │  └───────┘  │           │
│  │ 文献      │      │  │ ┌──┐ ┌──┐ ┌──┐  │  │   │             │           │
│  │ 历史产物  │      │  │ │  │ │  │ │  │  │  │   │  Messages   │           │
│  │ Activity │      │  │ └──┘ └──┘ └──┘  │  │   │             │           │
│  │ Workspace│      │  └──────────────────┘  │   │  ┌───────┐  │           │
│  │ Memory   │      │  ┌──────────────────┐  │   │  │Input  │  │           │
│  │          │      │  │ Sandbox / Files  │  │   │  └───────┘  │           │
│  │          │      │  │ ┌────┐ ┌────┐   │  │   │             │           │
│  │          │      │  │ │file│ │file│   │  │   │             │           │
│  │          │      │  │ └────┘ └────┘   │  │   │             │           │
│  │          │      │  └──────────────────┘  │   │             │           │
│  │          │      │  ┌──────────────────┐  │   │             │           │
│  │          │      │  │ Review Gate      │  │   │             │           │
│  │          │      │  │ [diff preview]   │  │   │             │           │
│  │          │      │  │ [Apply] [Discard]│  │   │             │           │
│  │          │      │  └──────────────────┘  │   │             │           │
│  │          │      └────────────────────────┘   │             │           │
│  │          │                                    │             │           │
│  └──────────┴────────────────────────────────────┴─────────────┘           │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 三种交互模式

#### 模式 A：普通聊天（默认）

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌────────┬───────────────────────────────────────┐ │
│  │Knowledge│                                      │ │
│  │  Rail   │         Chat Dock (主区域)            │ │
│  │         │         占 70%+ 宽度                  │ │
│  │         │                                      │ │
│  │         │                                      │ │
│  │         │         Compute Stage (收起)          │ │
│  │         │         底部摘要条 / 或隐藏           │ │
│  │         │                                      │ │
│  └─────────┴───────────────────────────────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- Chat Dock 占主区域，Compute Stage 收起为底部状态条或隐藏
- 底部状态条显示：最近任务名称 + 状态图标 + 「展开」按钮
- 用户可手动展开 Compute Stage

#### 模式 B：长任务执行中

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌────────┬──────────────────────────┬────────────┐ │
│  │Knowledge│                          │            │ │
│  │  Rail   │    Compute Stage (主区域) │ Chat Dock  │ │
│  │         │    占 55-65% 宽度         │ (缩为控制) │ │
│  │         │                          │ 占 25-30%  │ │
│  │         │                          │            │ │
│  │         │                          │  ┌──────┐  │ │
│  │         │                          │  │消息流 │  │ │
│  │         │                          │  │(缩小) │  │ │
│  │         │                          │  └──────┘  │ │
│  │         │                          │  ┌──────┐  │ │
│  │         │                          │  │输入框 │  │ │
│  │         │                          │  │(保留) │  │ │
│  │         │                          │  └──────┘  │ │
│  └─────────┴──────────────────────────┴────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- Compute Stage 自动展开，占据大部分屏幕
- Chat Dock 缩为控制区，保留消息流（缩小字体/间距）和输入框
- 用户可在 Chat 中追问、确认、取消
- 两个面板之间可拖拽调整宽度（resizable split）

#### 模式 C：任务完成

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌────────┬──────────────────────────┬────────────┐ │
│  │Knowledge│                          │            │ │
│  │  Rail   │    Compute Stage         │ Chat Dock  │ │
│  │         │    (保留过程和产物)       │ (恢复)     │ │
│  │         │    占 50% 宽度            │ 占 30%     │ │
│  │         │                          │            │ │
│  │         │                          │  完成摘要   │ │
│  │         │                          │  下一步建议 │ │
│  │         │                          │            │ │
│  └─────────┴──────────────────────────┴────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- Compute Stage 保留过程、文件和产物，用户可继续浏览
- Chat Dock 恢复，写入完成摘要和下一步建议
- 用户可关闭 Compute Stage 回到模式 A

### 2.3 Resizable Panel 实现

使用 `react-resizable-panels`（轻量、无依赖、支持 SSR）：

```tsx
// 三栏布局
<PanelGroup direction="horizontal">
  <Panel defaultSize={15} minSize={10} maxSize={25} collapsible>
    <KnowledgeRail />
  </Panel>
  <PanelResizeHandle />
  <Panel defaultSize={55} minSize={30}>
    <ComputeStage />
  </Panel>
  <PanelResizeHandle />
  <Panel defaultSize={30} minSize={20} maxSize={50}>
    <ChatDock />
  </Panel>
</PanelGroup>
```

面板尺寸持久化到 `localStorage`，按 workspace 隔离。

---

## 3. 组件拆分规划

### 3.1 ComputeStage 拆分（44KB → 8 个组件）

```
components/compute/
├── ComputeStage.tsx              # 3KB   orchestrator，只负责 layout 和状态分发
├── ComputeHeader.tsx             # 2KB  标题栏：feature 名、状态 badge、操作按钮
├── PhaseTimeline.tsx             # 4KB  阶段时间线：垂直/水平进度条
├── RuntimeBlockGrid.tsx          # 5KB  runtime blocks 网格展示
├── SandboxFileTree.tsx           # 4KB  文件树：文件夹、文件、预览
├── LogTerminal.tsx               # 3KB  日志终端：滚动、搜索、级别过滤
├── SubagentPanel.tsx             # 3KB  subagent 列表和时间线
├── ArtifactGallery.tsx           # 3KB  产物画廊：卡片、预览、下载
├── ReviewGate.tsx                # 5KB  review gate：diff preview、apply/revert
├── ComputeEmptyState.tsx         # 1KB  空状态：提示用户启动 feature
└── index.ts                      # 导出
```

### 3.2 ChatDock 拆分

```
components/chat/
├── ChatDock.tsx                  # 3KB  orchestrator
├── ChatHeader.tsx                # 2KB  thread 标题、模型选择、设置
├── ChatMessageList.tsx           # 4KB  消息列表：virtual scroll、分组
├── ChatMessage.tsx               # 3KB  单条消息：avatar、内容、 reasoning、操作
├── ChatComposer.tsx              # 3KB  输入框：附件、发送、快捷键
├── ChatPointerCard.tsx           # 2KB  feature 指针卡片：launch/resume/completed
├── ChatEmptyState.tsx            # 1KB  空状态
└── index.ts
```

### 3.3 KnowledgeRail 拆分

```
components/knowledge/
├── KnowledgeRail.tsx             # 2KB  orchestrator
├── PaperLibrary.tsx              # 3KB  文献库
├── ArtifactHistory.tsx           # 3KB  历史产物
├── ActivityFeed.tsx              # 2KB  activity 时间线
├── WorkspaceMemory.tsx           # 2KB  workspace memory 摘要
└── index.ts
```

### 3.4 共享组件

```
components/ui/
├── badge.tsx                     # 已存在，增强变体
├── button.tsx                    # 已存在，增加 compute 主题变体
├── card.tsx                      # 已存在，增加 compute 变体
├── dialog.tsx                    # 已存在
├── progress.tsx                  # 已存在，增加阶段进度变体
├── skeleton.tsx                  # 已存在
├── tooltip.tsx                   # 新增
├── tabs.tsx                      # 新增（Radix）
├── separator.tsx                 # 新增
├── scroll-area.tsx               # 新增（自定义滚动条）
├── resizable.tsx                 # 新增（react-resizable-panels wrapper）
├── status-indicator.tsx          # 新增（状态点：running/success/failed/waiting）
├── code-block.tsx                # 新增（代码展示，深色主题）
├── file-icon.tsx                 # 新增（按扩展名显示图标）
└── index.ts
```

---

## 4. 关键交互设计

### 4.1 Compute Stage 展开动画

```
触发：feature_launch / 用户点击「展开」

动画：
1. Chat Dock 宽度从 70% → 30%，400ms ease-apple
2. Compute Stage 从底部滑入，同时透明度 0→1，300ms
3. Compute Header 从顶部滑入，200ms delay
4. Phase Timeline 从左到右 stagger 入场，每个 80ms delay
5. Runtime Blocks 从下方 fade in，stagger 60ms

Framer Motion：
<AnimatePresence mode="wait">
  {mode === "executing" && (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <ComputeStage />
    </motion.div>
  )}
</AnimatePresence>
```

### 4.2 Runtime Block 实时更新

```
设计：
- 每个 runtime block 是一个卡片，包含：图标、标题、状态、内容预览
- 状态：pending → running → completed / failed
- running 态：顶部有流动的进度条（shimmer animation）
- 新 block 出现时：从下方滑入，已有 block 向下推移（layout animation）

Framer Motion：
<motion.div layout layoutId={block.id}>
  <RuntimeBlockCard {...block} />
</motion.div>
```

### 4.3 Review Gate Diff Preview

```
设计：
- 左右分栏：旧文件（左侧，暗色背景） vs 新文件（右侧，高亮背景）
- diff 行用颜色标识：删除（红底）、新增（绿底）、不变（透明）
- 行号对齐
- 底部操作栏：[Preview 签名] [Apply] [Discard] [Revert]
- Apply 后：卡片变为「已应用」状态，显示 undo 按钮

配色（在 compute 深色主题下）：
- 删除背景：rgba(209, 75, 75, 0.15)
- 删除文字：#E88A8A
- 新增背景：rgba(45, 157, 120, 0.15)
- 新增文字：#7DD3A8
- 行号：#5A6378
```

### 4.4 Sandbox File Tree

```
设计：
- 左侧文件树（类似 VS Code explorer）
- 点击文件 → 右侧打开预览面板
- 文件夹可折叠/展开
- 文件类型图标：pdf、tex、png、txt、json 等
- 右键菜单：Open / Download / Copy Path
- 拖拽上传（如果 sandbox 支持写入）

交互：
- 文件夹展开：旋转 chevron，children stagger 入场
- 文件选中：左侧高亮条 + 背景色变化
- 新文件出现：高亮闪烁一次（gold）然后正常
```

### 4.5 Phase Timeline

```
设计：
- 垂直时间线（左侧）或水平步骤条（顶部）
- 每个阶段：图标 + 名称 + 状态
- 状态：pending（灰）、running（cyan 流动动画）、completed（green ✓）、failed（red ✗）、skipped（灰虚线）
- 当前 running 阶段高亮，过往阶段可点击展开详情
- 未来阶段显示为灰态

动画：
- 阶段完成时：图标从 spinner → check，颜色从 cyan → green，200ms
- 新阶段开始：图标放大弹跳一次（scale 1→1.2→1），300ms spring
```

### 4.6 Chat Pointer Card

```
设计：
- 消息流中的特殊卡片，不是普通 assistant message
- 显示：feature 图标 + feature 名称 + 状态 + 操作按钮
- 状态：launching → running → awaiting_input → completed / failed
- 点击卡片 → 展开 Compute Stage 并定位到对应 session
- 卡片样式与普通消息区分：左侧有彩色竖条（cyan = running, green = done, red = failed）

变体：
- Launch Pointer：「正在启动「深度研究」...」+ 展开按钮
- Resume Pointer：「「深度研究」等待您补充信息」+ 去补充按钮
- Complete Pointer：「「深度研究」已完成」+ 查看结果按钮
- Failed Pointer：「「深度研究」执行失败」+ 重试按钮
```

---

## 5. 响应式设计

### 5.1 断点

```
sm:   640px   — 手机横屏
md:   768px   — 平板竖屏
lg:   1024px  — 平板横屏 / 小笔记本
xl:   1280px  — 笔记本
2xl:  1536px  — 桌面大屏
```

### 5.2 各断点布局

```
< 768px（手机/小平板）：
  - Knowledge Rail 变为抽屉（从左侧滑出）
  - Chat Dock 和 Compute Stage 全宽堆叠
  - 模式切换用 Tab 切换器
  - 默认显示 Chat，手动切换到 Compute

768px - 1024px（平板）：
  - Knowledge Rail 可折叠为图标栏
  - Chat + Compute 并排，Compute 默认收起
  - 长任务时 Compute 展开，Chat 变为底部输入条

> 1024px（桌面）：
  - 完整三栏布局
  - Resizable panels
  - 所有功能可用
```

---

## 6. 实现顺序

### Phase 1：设计系统基础（1-2 天）

1. **globals.css**：更新 CSS variables，增加 compute 主题色
2. **tailwind.config.ts**：更新字体、颜色、间距配置
3. **layout.tsx**：加载 Inter + JetBrains Mono 字体
4. **新组件**：
   - `components/ui/status-indicator.tsx`
   - `components/ui/scroll-area.tsx`
   - `components/ui/code-block.tsx`
   - `components/ui/file-icon.tsx`
5. **安装依赖**：`react-resizable-panels`

### Phase 2：Workspace Shell 框架（2-3 天）

1. **新布局**：
   - `app/(workbench)/workspaces/[id]/layout.tsx` — Workspace Shell 框架
   - 三栏 resizable panel
   - 三种模式状态机
2. **KnowledgeRail**：
   - 从 page.tsx 中拆出
   - 基础结构：PaperLibrary / ArtifactHistory / ActivityFeed
3. **ChatDock**：
   - 从 ThreadPanel 改名并瘦身
   - 保留核心：消息流、输入框、pointer cards
   - 移除 Compute 相关逻辑

### Phase 3：ComputeStage 拆分（3-4 天）

1. **ComputeStage.tsx** 重写为 orchestrator
2. **子组件逐个实现**：
   - ComputeHeader
   - PhaseTimeline
   - RuntimeBlockGrid
   - SandboxFileTree
   - LogTerminal
   - SubagentPanel
   - ArtifactGallery
   - ReviewGate
3. **stores/compute.ts** 适配：增加 active view 管理

### Phase 4：交互与动画（2-3 天）

1. **模式切换动画**：A↔B↔C 过渡
2. **Runtime block 实时更新**：layout animation
3. **Phase timeline 动画**：stagger、状态切换
4. **Review gate diff**：左右分栏、颜色标识
5. **Chat pointer cards**：入场动画、状态变化

### Phase 5：响应式适配（1-2 天）

1. **移动端**：抽屉式 Knowledge Rail，Tab 切换 Chat/Compute
2. **平板端**：可折叠 Rail，Compute 默认收起
3. **断点测试**：sm / md / lg / xl / 2xl

### Phase 6：细节打磨（1-2 天）

1. **深色主题一致性**：所有 compute 组件检查对比度
2. **Loading 状态**：骨架屏、spinner、progress
3. **Empty state**：各面板空态设计
4. **Error state**：错误边界、重试
5. **无障碍**：键盘导航、焦点管理、ARIA

---

## 7. 设计决策记录

### 7.1 为什么 Compute Stage 用深色？

- 长任务工作台需要长时间注视，深色减少 eye strain
- 文件树、代码块、日志、终端在深色底上对比度更好
- 与 Chat Dock 的暖纸色形成视觉分区
- 与 Kimi Computer / Claude Artifacts 等 AI 工作台设计语言对齐

### 7.2 为什么用 Inter + JetBrains Mono？

- Inter：现代、高可读性、广泛使用的无衬线字体，适合 UI
- JetBrains Mono：专为代码设计，等宽、 ligatures、高辨识度
- 两者搭配形成「专业工具」气质，区别于普通聊天应用

### 7.3 为什么三栏而不是两栏？

- Knowledge Rail（文献、历史产物）是学术工作流的核心资产
- 放在独立栏中可随时查阅，不抢占 Chat/Compute 空间
- 可折叠，小屏幕时不占用空间
- 参考：Notion（sidebar + main + comments）、VS Code（explorer + editor + panel）

### 7.4 为什么用 react-resizable-panels？

- 轻量（~3KB gzipped），无额外依赖
- 原生支持 SSR，与 Next.js 兼容
- 支持 collapsible panels、持久化、触摸设备
- 比自写 splitter 更稳定

---

## 8. 风险与回退

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 深色主题与现有浅色组件冲突 | 中 | 高 | 先增量更新，保留旧变量作为 fallback |
| react-resizable-panels 与现有布局不兼容 | 低 | 中 | 先 POC 验证，再全面替换 |
| 移动端三栏布局体验差 | 中 | 中 | 移动端退化为 Tab 切换 + 抽屉 |
| ComputeStage 拆分引入回归 | 中 | 高 | 每拆一个组件就跑对应测试 |
| 字体加载影响 FCP | 低 | 低 | font-display: swap，系统字体 fallback |

---

## 9. 验收标准

- [ ] 三种交互模式（普通/执行中/完成）均可正常切换
- [ ] Compute Stage 所有子组件可独立渲染和测试
- [ ] Chat Dock 不再包含 Compute 逻辑
- [ ] Knowledge Rail 可折叠/展开，内容可浏览
- [ ] Resizable panels 可拖拽调整，尺寸持久化
- [ ] 移动端可用（Tab 切换 + 抽屉）
- [ ] 深色主题对比度符合 WCAG AA
- [ ] 所有动画流畅，不卡顿（60fps）
- [ ] 现有测试通过，新增测试覆盖新组件
