# Wenjin v2 设计语言 — Glass / visionOS

> **状态**: 已确定，进入 Phase 3 实施基线
> **作者**: Ze + Claude (in collab)
> **日期**: 2026-05-09
> **关联**: [2026-05-09-wenjin-workspace-rebuild-design.md](./2026-05-09-wenjin-workspace-rebuild-design.md)
> **范围**: Phase 3 v2 路由全部使用；全局 `/` 路由后续逐步迁移；最终替代旧"墨/纸/水/铜"古风视觉根脉

---

## 1. 哲学

### 1.1 一句话定位

**学术专业 + Apple 出品级未来感**。chat 朴素到几乎消失（参考 ChatGPT），panel 是一个会发光的玻璃工坊（参考 Apple visionOS / Arc 浏览器）。

### 1.2 视觉哲学

| 维度 | 选择 | 拒绝 |
|------|------|------|
| **左右分工** | 非对称：chat 隐入背景，panel 是焦点 | 对称的双栏、每栏都同等装饰 |
| **科技感来源** | 玻璃 + 光斑 + 渐变球 + 流动进度条 | 暗黑底 + 高饱和霓虹 / 网格底图 / 工业贴纸 |
| **学术感来源** | 精确数字（tabular-nums）+ 极简留白 + 节制 accent | 衬线宋体 / 罗马数字 / 印章 / 拟物纸张 |
| **温度** | 冷静、未来、像精密仪器 | 暖黄 / 古典 / 像信纸 |
| **复杂度** | 信息密度适中，玻璃层级可读 | 超扁平（信息无层级）/ 超拟物（视觉噪声） |

### 1.3 反例（不要做）

- ❌ 米黄纸 + 墨蓝（旧 wenjin 古风）
- ❌ 思源宋体作 display
- ❌ 朱红印章 / 罗马数字 / 中文数字编号
- ❌ 暗色全场（虽然 Linear-Stripe 那样也漂亮，但用户选了亮色 Glass）
- ❌ 工业贴纸 / 偏移阴影 / Brutalist 倾斜
- ❌ 厚阴影、边框 2-3px、强对比

### 1.4 全站交互密度原则

这条原则适用于 Workbench、Prism、room drawers、admin、settings 和后续所有主页面。它不是 Workbench 的局部修复。

1. **自动适配优先**：界面应像浏览器响应式布局一样自动根据 viewport、任务状态和当前选择调整。不要让用户手动恢复“自动聚焦”、理解锁定状态，或管理内部 focus 模式。
2. **信息分层优先**：一屏只承载当前决策所需的信息。列表、摘要、详情、编辑、审计 trace 应分层进入二级导航、详情 pane、drawer、fullscreen 或 Prism，而不是在同一层堆满。
3. **内部状态不外露**：`focusedRunId`、`manualTabLock`、hydration、projection、retry 等工程状态不得直接成为用户可见按钮或文案。用户看到的是“运行中 / 待审阅 / 已保存 / 已完成 / 需要补充”。
4. **导航先折叠，内容后折叠**：当空间不足时，导航和次级操作先收敛为 icon-only + tooltip；核心内容区域不能被重复按钮、冗长标题和状态标签挤压。
5. **详情渐进展开**：窄面板默认 list-first；选择条目后进入更宽详情面或 fullscreen split view。宽屏才同时展示 list + detail。
6. **长文本必须受控**：标题、作者、文件名、run 名称、URL 等必须在列表中 ellipsis 或 line-clamp，完整内容进入详情区。
7. **操作显隐跟随上下文**：运行中才突出“中断并补充”；已完成才突出“审阅/保存”；不可用操作应降级为图标或隐藏，不长期占据主操作区。
8. **二级导航轻量化**：结果类型、room 类型、证据类型等使用 compact segmented controls / pills，不使用大卡片或重复标题。

设计评审时，如果出现“用户需要知道这个按钮是恢复某个内部状态”的解释，默认判定为 UI 泄漏，需要重新设计为自动行为或明确的产品动作。

---

## 2. 色板

### 2.1 主背景

```css
/* Glass panel 背景渐变（米白基底带蓝紫倾向）*/
--glass-bg-gradient: linear-gradient(135deg, #E0EFFF 0%, #F0F4FF 50%, #E8E0FF 100%);

/* 备选：纯米白基底（chat 等次区域） */
--surface-white: #FFFFFF;
--surface-soft: #FAFAFA;
--surface-card: #F4F4F4;     /* user message bubble */
```

### 2.2 光斑（panel 背景气氛）

每个 panel 都该有 ≥2 个光斑作背景气氛，相互错开位置：

```css
--orb-purple: rgba(139, 92, 246, 0.4);   /* 紫光（主） */
--orb-blue:   rgba(56, 189, 248, 0.35);  /* 蓝光（辅） */
--orb-blur:   filter: blur(40px);        /* 大尺寸光斑 */
--orb-blur-l: filter: blur(50px);        /* 超大柔光 */
```

**实现样式**：
```css
.panel-bg::before {
  content: ''; position: absolute; top: 20px; right: 40px;
  width: 180px; height: 180px; border-radius: 50%;
  background: radial-gradient(circle, var(--orb-purple), transparent 70%);
  filter: var(--orb-blur);
  pointer-events: none;
}
.panel-bg::after {
  content: ''; position: absolute; bottom: 30px; left: 30px;
  width: 200px; height: 200px; border-radius: 50%;
  background: radial-gradient(circle, var(--orb-blue), transparent 70%);
  filter: var(--orb-blur-l);
  pointer-events: none;
}
```

### 2.3 文字

```css
--text-primary:   #14141E;                   /* 深色但带蓝（避免纯黑） */
--text-secondary: rgba(20, 20, 30, 0.55);    /* 次级 / meta */
--text-tertiary:  rgba(20, 20, 30, 0.4);     /* 占位 / 时间戳辅助 */
--text-disabled:  rgba(20, 20, 30, 0.25);    /* 禁用 / queued state */
```

### 2.4 玻璃（核心）

```css
--glass-bg:           rgba(255, 255, 255, 0.45);  /* 标准玻璃卡 */
--glass-bg-elevated:  rgba(255, 255, 255, 0.7);   /* 重要 / hover 玻璃 */
--glass-bg-subtle:    rgba(255, 255, 255, 0.3);   /* 次级 / queued 玻璃 */

--glass-border:       rgba(255, 255, 255, 0.6);   /* 标准玻璃边 */
--glass-border-hi:    rgba(255, 255, 255, 0.7);   /* 重要玻璃边 */

--glass-blur:         blur(20px);
--glass-blur-hi:      blur(24px);

--glass-shadow:       0 4px 16px rgba(20, 20, 30, 0.04);
--glass-shadow-hi:    0 8px 32px rgba(139, 92, 246, 0.15);   /* 重要卡（紫色发光） */
--glass-shadow-up:    0 2px 12px rgba(20, 20, 30, 0.03);     /* 上浮浅阴影 */
```

### 2.5 Accent（状态/交互色）

```css
/* Primary accent — 紫色：execution running、active state、用户偏好覆盖 */
--accent-purple-100: rgba(139, 92, 246, 0.12);   /* 浅底 */
--accent-purple-200: rgba(139, 92, 246, 0.18);   /* glow ring */
--accent-purple-300: rgba(139, 92, 246, 0.25);   /* border / 强调 */
--accent-purple-500: #A78BFA;                    /* 渐变浅 */
--accent-purple-700: #7C3AED;                    /* 渐变深 / 文字 */

/* Secondary accent — 蓝色：capability link、informational */
--accent-blue-100:   rgba(0, 122, 255, 0.06);
--accent-blue-500:   #38BDF8;
--accent-blue-700:   #007AFF;

/* Status — success（已完成 phase）*/
--status-success-light: #4ADE80;
--status-success-deep:  #16A34A;
--status-success-shadow: rgba(22, 163, 74, 0.35);

/* Status — running（运行中 phase）*/
--status-running-light: #A78BFA;
--status-running-deep:  #7C3AED;
--status-running-shadow: rgba(139, 92, 246, 0.4);

/* Status — error/failed */
--status-error: #DC2626;
--status-error-light: #FCA5A5;

/* Status — idle/queued（虚线 + 灰）*/
--status-idle: rgba(20, 20, 30, 0.25);
```

### 2.6 边框 / 分隔线

```css
--border-default: #EEEEEE;             /* chat 区分隔 */
--border-soft:    rgba(20, 20, 30, 0.08);
--border-glass:   var(--glass-border);
```

---

## 3. 字体

### 3.1 字族

```css
/* 主字体 — 紧凑现代 grotesk，所有 UI 文字默认 */
--font-sans: 'SF Pro Display', 'Inter', system-ui, -apple-system,
             'PingFang SC', 'Helvetica Neue', sans-serif;

/* 数据字体 — 等宽，所有数字 / 时间 / 节点 ID / 计量 */
--font-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace;

/* 不再使用 */
/* ❌ Noto Serif SC（旧古风 display）*/
/* ❌ Noto Sans SC（旧 body）*/
/* ❌ EB Garamond / Fraunces / GT Sectra（其他设计稿衬线）*/
```

### 3.2 字号 / 字重 / 字距

| 用途 | size | weight | letter-spacing | line-height |
|------|------|--------|---------------|-------------|
| 大标题（panel 标题、execution name）| 19px | 600 | -0.4px | 1.3 |
| 中标题（卡片标题）| 14px | 600 | -0.3px | 1.4 |
| 小标题（label cap）| 9-10px | 500 | 0.5-1px (uppercase) | 1.4 |
| Body（chat 消息、卡片正文）| 13.5px | 400-500 | -0.1px | 1.55-1.65 |
| Stats value | 16px | 600 | -0.2px (tabular-nums) | 1.2 |
| 时间戳 / meta | 9-10px | 400-500 | 0.4-0.5px | 1.4 |
| 节点名 / 数据 | 11-13px (mono) | 400-600 | 0 | 1.4 |

**强制规则**：
- 所有数字（计数、时间、cost、token usage）**必须用 `font-feature-settings: 'tnum'`** 等宽数字
- 所有标题用负 letter-spacing（-0.2 to -0.5px）让字形紧凑
- 所有 uppercase label 加正 letter-spacing（0.5-1px）易读

### 3.3 写字风格（文案）

- chat agent 输出："Got it. Started deep_research → workspace." 简短、专业、不卖萌、不文绉绉
- panel 状态："running"、"queued"、"31 sources"，数字开头
- 不写："presently weaving"、"awaits its turn"、"已派遣"等拟人/古风
- 中文 OK 但与英文混用要专业（"已启动 deep_research → 见右侧"）

---

## 4. 形状 & 间距

### 4.1 圆角

```css
--radius-sm:  6px;    /* 小标签、tag */
--radius-md:  10px;   /* 输入框、按钮 */
--radius-lg:  14px;   /* 标准玻璃卡 */
--radius-xl:  16-18px; /* 容器卡（panel 内 stats 容器、phase 容器） */
--radius-pill: 999px; /* 状态徽章 */
--radius-bubble-user:  12px;            /* 用户气泡 4 角 */
--radius-bubble-ai:    14px 14px 14px 4px; /* AI 气泡（左下尖角，可选）*/
```

### 4.2 间距系统（4px 基）

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;   /* 卡片内紧凑 padding */
--space-4: 14px;   /* 卡片标准 padding */
--space-5: 16px;
--space-6: 20px;
--space-7: 24px;   /* 段落间 */
--space-8: 32px;   /* panel padding */
```

### 4.3 边框宽度

- 玻璃卡边：`1px solid var(--glass-border)` —— 永远 1px，不要 2-3px
- 强调态边：`1px solid var(--accent-purple-300)` + 加 `box-shadow: 0 0 0 3px rgba(139,92,246,0.05)` 做"光环"
- queued 状态：`1px dashed rgba(20,20,30,0.15)`

---

## 5. 关键组件 specs

### 5.1 状态点（渐变球）

```html
<!-- 完成 ✓ -->
<div style="
  width: 22px; height: 22px; border-radius: 50%;
  background: linear-gradient(135deg, #4ADE80, #16A34A);
  box-shadow: 0 4px 14px rgba(22, 163, 74, 0.35),
              inset 0 0 0 2px rgba(255, 255, 255, 0.4);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: white; font-weight: 700;
">✓</div>

<!-- 运行中（脉冲动画） -->
<div style="
  width: 22px; height: 22px; border-radius: 50%;
  background: linear-gradient(135deg, #A78BFA, #7C3AED);
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.4),
              inset 0 0 0 2px rgba(255, 255, 255, 0.4);
  animation: pulse-soft 1.6s ease-in-out infinite;
"></div>

<!-- 等待 -->
<div style="
  width: 22px; height: 22px; border-radius: 50%;
  border: 1.5px dashed rgba(20, 20, 30, 0.25);
"></div>

<!-- 失败 -->
<div style="
  width: 22px; height: 22px; border-radius: 50%;
  background: linear-gradient(135deg, #FCA5A5, #DC2626);
  box-shadow: 0 4px 14px rgba(220, 38, 38, 0.3),
              inset 0 0 0 2px rgba(255, 255, 255, 0.4);
"></div>
```

### 5.2 玻璃卡片

**标准卡**：
```css
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--glass-shadow);
  padding: var(--space-3) var(--space-4);
}
```

**重要 / 运行中卡**（更白、更厚阴影）：
```css
.glass-card-active {
  background: var(--glass-bg-elevated);
  backdrop-filter: var(--glass-blur-hi);
  border: 1px solid var(--accent-purple-300);
  box-shadow: var(--glass-shadow-hi);
  padding: var(--space-4);
}
```

### 5.3 进度条

```html
<div style="
  height: 4px;
  background: var(--accent-purple-100);
  border-radius: 3px;
  overflow: hidden;
">
  <div style="
    height: 100%; width: 60%;
    background: linear-gradient(90deg, #A78BFA, #7C3AED);
    border-radius: 3px;
  "></div>
</div>
```

**流光版**（运行中加扫光动效，可选）：
```css
@keyframes flow {
  0% { transform: translateX(-100%) }
  100% { transform: translateX(300%) }
}
.progress-flow::before {
  content: ''; position: absolute; left: 0; top: 0;
  height: 100%; width: 60%;
  background: linear-gradient(90deg, transparent, #7C3AED, transparent);
  animation: flow 1.8s ease-in-out infinite;
}
```

### 5.4 Stats 卡（panel header）

3 列网格，gap 10px：

```html
<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px">
  <div class="glass-card">
    <div style="font-size: 9px; color: var(--text-secondary);
                letter-spacing: 1px; text-transform: uppercase;
                margin-bottom: 4px; font-weight: 500">tokens</div>
    <div style="font-size: 16px; font-weight: 600; color: var(--text-primary);
                font-feature-settings: 'tnum'">32,184</div>
  </div>
  <!-- ... cost / progress 同结构 -->
</div>
```

### 5.5 Chat 气泡

**用户消息**（右靠）：
```html
<div style="display: flex; justify-content: flex-end; margin-bottom: 18px">
  <div style="
    font-size: 13.5px; color: var(--text-primary); line-height: 1.55;
    padding: 10px 14px;
    background: #F4F4F4;
    border-radius: 12px;
    max-width: 78%;
  ">
    Run a deep literature review on conditional GAN.
  </div>
</div>
```

**AI 消息**（左靠，无气泡）：
```html
<div style="margin-bottom: 18px">
  <div style="
    font-size: 13.5px; color: var(--text-primary); line-height: 1.6;
  ">
    Got it. Using academic voice in zh+en.
    <span style="color: var(--accent-blue-700); font-weight: 500">deep_research</span>
    is now running →
  </div>
</div>
```

**关键**：AI 消息不要边框、不要背景。**capability 名字 / link 用蓝色 #007AFF + font-weight 500** 作为唯一交互高亮。

### 5.6 Phase 卡（panel 内节点列表）

```html
<!-- 已完成 -->
<div class="glass-card" style="display: flex; align-items: center; gap: 10px">
  <div class="status-dot status-dot--success">✓</div>
  <div style="font-size: 13.5px; flex: 1; font-weight: 500">discover</div>
  <div style="font-size: 11px; color: var(--text-secondary); font-feature-settings: 'tnum'">31 sources</div>
</div>

<!-- 运行中 -->
<div class="glass-card-active">
  <div style="display: flex; align-items: center; gap: 10px">
    <div class="status-dot status-dot--running"></div>
    <div style="font-size: 13.5px; flex: 1; font-weight: 600">cluster</div>
    <div style="font-size: 11px; color: var(--accent-purple-700);
                font-weight: 600; font-feature-settings: 'tnum'">1m 18s</div>
  </div>
  <div class="progress" style="margin-top: 10px"><div class="progress__fill" style="width: 60%"></div></div>
</div>

<!-- 队列中 -->
<div style="
  background: var(--glass-bg-subtle);
  backdrop-filter: var(--glass-blur);
  border: 1px dashed rgba(20, 20, 30, 0.15);
  border-radius: var(--radius-lg);
  padding: 12px 14px; opacity: 0.65;
  display: flex; align-items: center; gap: 10px;
">
  <div class="status-dot status-dot--idle"></div>
  <div style="font-size: 13.5px; flex: 1; color: var(--text-secondary)">compose</div>
  <div style="font-size: 11px; color: var(--text-tertiary)">queued</div>
</div>
```

### 5.7 Result Card（完成后 chat 中渲染）

result_card 是 AI 消息中嵌入的特殊 block，应该**比普通 chat 消息略有"卡片感"**但仍保留极简：

```html
<div style="
  background: var(--glass-bg-elevated);
  backdrop-filter: var(--glass-blur-hi);
  border: 1px solid rgba(22, 163, 74, 0.2);
  border-radius: var(--radius-xl);
  padding: 16px 18px;
  margin: 8px 0;
">
  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px">
    <div class="status-dot status-dot--success" style="width: 16px; height: 16px">✓</div>
    <div style="font-size: 13px; font-weight: 600">deep_research · completed</div>
    <div style="font-size: 10px; color: var(--text-tertiary); margin-left: auto;
                font-feature-settings: 'tnum'">2m 14s · $0.42</div>
  </div>
  <div style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6;
              margin-bottom: 14px">
    我对 conditional GAN 做了系统性文献调研。请确认要保留哪些到 workspace。
  </div>
  <!-- 输出列表（低风险默认全勾；证据/引用/claim 高风险项默认取消勾选）+ 操作按钮 -->
</div>
```

Review / Evidence 的风险文案使用产品语言：`高风险`、`需要确认`、`保存已勾选`。不要展示 schema、contract、projection 等工程词。高风险时禁用一键“全部接受”，保留逐项确认和保存已勾选。

---

## 6. 动效

### 6.1 缓动（easing）

```css
--ease-standard: cubic-bezier(0.16, 1, 0.3, 1);  /* Apple 风长缓动 */
--ease-snappy:   cubic-bezier(0.4, 0, 0.2, 1);   /* 标准 material */

--duration-fast:    150ms;   /* hover、tap */
--duration-medium:  300ms;   /* 卡片进出 */
--duration-slow:    500ms;   /* 大区块切换 */
```

### 6.2 关键动画

```css
/* 状态点脉冲（运行中）*/
@keyframes pulse-soft {
  0%, 100% { opacity: 0.4 }
  50%      { opacity: 1   }
}

/* 进度条扫光（运行中）*/
@keyframes flow {
  0%   { transform: translateX(-100%) }
  100% { transform: translateX(300%)  }
}

/* 卡片进入（执行流新增节点）*/
@keyframes glass-in {
  from { opacity: 0; transform: translateY(4px) scale(0.99) }
  to   { opacity: 1; transform: translateY(0)   scale(1)    }
}

/* 涟漪（可选，运行中节点四周）*/
@keyframes ripple {
  0%   { transform: scale(1);   opacity: 0.6 }
  100% { transform: scale(2.4); opacity: 0   }
}
```

### 6.3 Hover 行为

- 玻璃卡 hover：`translateY(-1px)` + box-shadow 加深 30%
- 按钮 hover：背景饱和度增加，无大尺寸变化
- 链接 hover：下划线 fade-in

### 6.4 不要做的动效

- ❌ 弹跳 / 旋转 / 闪烁
- ❌ 扫光过度（一个 panel 同时跑 3 条 flow 太花）
- ❌ 朱印盖章、纸张翻页（古风余韵）

---

## 7. 布局栅格

### 7.1 V2 Workspace 主布局

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar (sticky, 48-52px) — workspace name + rooms badges +⚙ │
├─────────────┬────────────────────────────────────────────────┤
│             │                                                │
│  Chat       │  Live Workflow Panel                           │
│  (左, 42%)  │  (右, 58%)                                     │
│             │                                                │
│  白底       │  Glass 渐变背景 + 光斑                         │
│  极简       │  科技感、stats、phase cards                    │
│             │                                                │
└─────────────┴────────────────────────────────────────────────┘
```

- **Chat 宽度**：380-420px 固定（不随 viewport 拉伸到太宽以保聊天行长适中），剩余给 panel
- **TopBar 高度**：48px
- **Chat padding**：28px 24px
- **Panel padding**：32px

### 7.2 Topbar / Rooms badges

```html
<header style="
  display: flex; align-items: center; gap: 16px;
  padding: 12px 24px;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border-soft);
">
  <div style="font-size: 13px; font-weight: 600">张三硕士论文</div>
  <span style="color: var(--text-tertiary)">·</span>
  <div style="font-size: 11px; color: var(--text-secondary)">thesis</div>

  <div style="margin-left: auto; display: flex; gap: 6px">
    <button class="badge">📄 Documents <sup>3</sup></button>
    <button class="badge">📚 Library <sup>23</sup></button>
    <button class="badge">📜 Runs</button>
    <button class="badge">✓ Tasks <sup>2</sup></button>
    <button class="badge badge--icon">⚙</button>
  </div>
</header>

<style>
.badge {
  font-size: 11px; padding: 5px 10px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-pill);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-standard);
}
.badge:hover { background: var(--glass-bg-elevated) }
.badge sup {
  font-size: 9px; color: var(--accent-purple-700);
  font-weight: 600; margin-left: 2px;
}
</style>
```

---

## 8. globals.css 迁移计划

### 8.1 新增 CSS 变量

**Phase 3 W7 第一步**：在 `frontend/app/globals.css` 顶部加入新 design tokens（保留旧的，并存阶段）：

```css
:root {
  /* ═══════════ V2 Glass Design Language (2026-05-09) ═══════════ */

  /* Surfaces */
  --v2-surface-white: #FFFFFF;
  --v2-surface-soft:  #FAFAFA;
  --v2-surface-card:  #F4F4F4;

  /* Glass */
  --v2-glass-bg:          rgba(255, 255, 255, 0.45);
  --v2-glass-bg-elevated: rgba(255, 255, 255, 0.7);
  --v2-glass-bg-subtle:   rgba(255, 255, 255, 0.3);
  --v2-glass-border:      rgba(255, 255, 255, 0.6);
  --v2-glass-border-hi:   rgba(255, 255, 255, 0.7);
  --v2-glass-blur:        blur(20px);
  --v2-glass-blur-hi:     blur(24px);
  --v2-glass-shadow:      0 4px 16px rgba(20, 20, 30, 0.04);
  --v2-glass-shadow-hi:   0 8px 32px rgba(139, 92, 246, 0.15);

  /* Background gradient + orbs */
  --v2-bg-gradient: linear-gradient(135deg, #E0EFFF 0%, #F0F4FF 50%, #E8E0FF 100%);
  --v2-orb-purple:  rgba(139, 92, 246, 0.4);
  --v2-orb-blue:    rgba(56, 189, 248, 0.35);

  /* Text */
  --v2-text-primary:   #14141E;
  --v2-text-secondary: rgba(20, 20, 30, 0.55);
  --v2-text-tertiary:  rgba(20, 20, 30, 0.4);
  --v2-text-disabled:  rgba(20, 20, 30, 0.25);

  /* Accents */
  --v2-accent-purple-100: rgba(139, 92, 246, 0.12);
  --v2-accent-purple-300: rgba(139, 92, 246, 0.25);
  --v2-accent-purple-500: #A78BFA;
  --v2-accent-purple-700: #7C3AED;
  --v2-accent-blue-700:   #007AFF;

  /* Status */
  --v2-status-success-light: #4ADE80;
  --v2-status-success-deep:  #16A34A;
  --v2-status-running-light: #A78BFA;
  --v2-status-running-deep:  #7C3AED;
  --v2-status-error:         #DC2626;
  --v2-status-idle:          rgba(20, 20, 30, 0.25);

  /* Borders */
  --v2-border-default: #EEEEEE;
  --v2-border-soft:    rgba(20, 20, 30, 0.08);

  /* Radius */
  --v2-radius-sm:    6px;
  --v2-radius-md:   10px;
  --v2-radius-lg:   14px;
  --v2-radius-xl:   16px;
  --v2-radius-pill: 9999px;

  /* Spacing */
  --v2-space-1:  4px;
  --v2-space-2:  8px;
  --v2-space-3: 12px;
  --v2-space-4: 14px;
  --v2-space-5: 16px;
  --v2-space-6: 20px;
  --v2-space-7: 24px;
  --v2-space-8: 32px;

  /* Motion */
  --v2-ease-standard: cubic-bezier(0.16, 1, 0.3, 1);
  --v2-ease-snappy:   cubic-bezier(0.4, 0, 0.2, 1);
  --v2-duration-fast:   150ms;
  --v2-duration-medium: 300ms;

  /* Fonts */
  --v2-font-sans: 'SF Pro Display', 'Inter', system-ui, -apple-system, 'PingFang SC', sans-serif;
  --v2-font-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', monospace;
}

/* Global keyframes for v2 */
@keyframes v2-pulse-soft {
  0%, 100% { opacity: 0.4 }
  50%      { opacity: 1 }
}
@keyframes v2-flow {
  0%   { transform: translateX(-100%) }
  100% { transform: translateX(300%) }
}
@keyframes v2-glass-in {
  from { opacity: 0; transform: translateY(4px) scale(0.99) }
  to   { opacity: 1; transform: translateY(0) scale(1) }
}
```

### 8.2 旧变量处理

- Phase 3 期间：保留旧 `--brand-*` / `--bg-base` 等变量，旧路由不动
- Phase 4 cutover：把 `/v2` 改为默认路由后，开始系统替换旧路由的视觉实现
- Phase 5+：删除旧 `--brand-*` 变量、删除 `--font-display: serif` 等遗留

### 8.3 字体加载

`frontend/app/layout.tsx` 添加：

```tsx
import { Inter, JetBrains_Mono } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});

export default function RootLayout({ children }) {
  return (
    <html className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>...</body>
    </html>
  );
}
```

> 注：SF Pro Display 不在 Google Fonts 上 — V1 用 Inter 兜底，macOS 用户自动 fallback 到 SF Pro。

---

## 9. 配套页面预览（参考 mockup 10）

第三轮 mockup 编号 10 是这套语言的"权威 reference"。落地实现时如有歧义，以 mockup 10 为准。Mockup 文件留在 `.superpowers/brainstorm/3488-1778323161/content/03-academic-tech.html`。

实施时如需新组件没在本文档中明确，应：
1. 沿用色板 + 字体 + 玻璃卡 + 渐变球 + tabular-nums 几条核心规则
2. 不要引入新装饰元素（衬线/印章/网格底图/工业贴纸等）
3. 优先复用 mockup 10 的视觉语汇

---

## 10. 一致性 checklist

实施 Phase 3 任何 v2 组件时，提交前自检：

- [ ] 字体：所有数字加 `font-feature-settings: 'tnum'`？
- [ ] 字体：所有 mono 区域用了 JetBrains Mono？没误用衬线？
- [ ] 色板：用了本文档定义的 `--v2-*` 变量，没硬编码 hex？
- [ ] 玻璃：用了 `backdrop-filter: blur(20-24px)` + 半透白 + 白边线？
- [ ] 边框：1px 不是 2-3px？
- [ ] 圆角：14-18px 是标准卡，6px 小标签，pill 用于徽章？
- [ ] 状态点：用渐变球 + 投影发光，不是纯色圆？
- [ ] Panel 背景：有 ≥2 个 radial gradient 光斑（紫 + 蓝）+ blur 40-50px？
- [ ] 动效：用 `cubic-bezier(0.16, 1, 0.3, 1)` 缓动？运行中状态有 `pulse-soft`？
- [ ] 文案：英文短句、不卖萌、不文绉绉？
- [ ] 不该出现：宋体？衬线？印章？罗马数字？纸张纹理？古风色？

---

*文档结束 · Phase 3 起所有 v2 FE 工作以本文档为唯一视觉依据*
