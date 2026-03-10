# AcademiaGPT UI/UX 重新设计文档

## 概述

本文档描述了 AcademiaGPT 前端 UI/UX 的重新设计方案，目标是解决当前设计"配色太亮太浅、不够学术风格、看起来廉价劣质"的问题。

## 设计目标

1. **专业学术感** - 深色但不过于黑暗，传达严肃学术氛围
2. **现代玻璃态** - 保留轻度毛玻璃效果但更沉稳
3. **弱化渐变** - 标题使用纯色，渐变仅用于 hover/active 状态
4. **中等改造** - 配色 + 主要组件样式调整，保持现有架构

## 设计方案：学术深空风

### 配色系统

#### 背景层级
```css
--bg-base: #0C1222;       /* 主背景 - 深夜空蓝 */
--bg-elevated: #151D30;   /* 卡片/面板 - 深靛蓝 */
--bg-surface: #1E293B;    /* 表面层 - 中灰蓝 */
--bg-muted: #243044;      /* 输入框等 - 暗灰蓝 */
```

#### 强调色
```css
--accent-primary: #2563EB;    /* 主强调 - 学术蓝 */
--accent-secondary: #38BDF8;  /* 次强调/hover - 天蓝 */
--accent-tertiary: #0EA5E9;   /* 第三级 - 行动蓝 */
--accent-gold: #CA8A04;       /* 金色 - 成就/徽章 */
```

#### 语义色
```css
--semantic-success: #10B981;  /* 成功 - 翠绿 */
--semantic-warning: #F59E0B;  /* 警告 - 琥珀 */
--semantic-error: #EF4444;    /* 错误 - 红 */
--semantic-info: #3B82F6;     /* 信息 - 蓝 */
```

#### 文字色
```css
--text-primary: #F1F5F9;      /* 主文字 - 暖白 */
--text-secondary: #94A3B8;    /* 次文字 - 中灰 */
--text-muted: #64748B;        /* 辅助文字 - 暗灰 */
--text-inverse: #0F172A;      /* 反色文字 */
```

#### 边框与分割
```css
--border-default: #2D3A4F;    /* 默认边框 */
--border-subtle: #1E293B;     /* 微妙边框 */
--border-focus: #3B82F6;      /* 聚焦边框 */
```

### 玻璃效果系统

#### 基础玻璃
```css
--glass-bg: rgba(21, 29, 48, 0.85);
--glass-blur: blur(24px) saturate(120%);
--glass-border: rgba(56, 189, 248, 0.12);
--glass-shadow:
  0 4px 24px rgba(0, 0, 0, 0.25),
  inset 0 1px 0 rgba(255, 255, 255, 0.05);
```

#### 悬浮玻璃
```css
--glass-elevated-bg: rgba(30, 41, 59, 0.9);
--glass-elevated-shadow:
  0 8px 32px rgba(0, 0, 0, 0.35),
  inset 0 1px 0 rgba(255, 255, 255, 0.08);
```

#### 与当前效果对比

| 属性 | 当前 | 优化后 |
|-----|------|-------|
| 背景透明度 | 0.72 (很透) | 0.85 (更实) |
| 模糊强度 | 40px | 24px (更清晰) |
| 边框色 | 白色 0.18 | 天蓝 0.12 |
| 阴影 | 浅而散 | 深而聚 |

### 组件样式系统

#### 按钮变体

**Primary (主按钮)**
- bg: `linear-gradient(135deg, #2563EB, #1D4ED8)`
- text: `#FFFFFF`
- hover: 渐变加深 + 微上移 `scale(1.02)`

**Secondary (次按钮)**
- bg: `rgba(37, 99, 235, 0.15)`
- text: `#38BDF8`
- border: `1px solid rgba(56, 189, 248, 0.3)`
- hover: bg 加深 + border 变亮

**Ghost (幽灵按钮)**
- bg: `transparent`
- text: `#94A3B8`
- hover: `bg rgba(255,255,255,0.05)`

**Destructive (危险按钮)**
- bg: `rgba(239, 68, 68, 0.15)`
- text: `#EF4444`
- hover: bg 加深

#### 输入框

**默认状态**
- bg: `rgba(30, 41, 59, 0.5)`
- border: `1px solid #2D3A4F`
- text: `#F1F5F9`

**聚焦状态**
- border: `1px solid #3B82F6`
- ring: `0 0 0 3px rgba(59, 130, 246, 0.2)`

**placeholder**: `#64748B`

#### 徽章/标签

**类型徽章**
- SCI Paper: bg `emerald-500/15`, text `emerald-400`
- Thesis: bg `purple-500/15`, text `purple-400`
- Proposal: bg `blue-500/15`, text `blue-400`
- Grant: bg `amber-500/15`, text `amber-400`

**卡片**
- 标题: text `#F1F5F9`, font-weight 600
- 正文: text `#94A3B8`
- 图标: text `#38BDF8` (次强调色)
- hover: 轻微上移 + 阴影加深

### 渐变与动画策略

#### 渐变策略 (弱化处理)

**标题文字**
- 主标题: 纯白色 `#F1F5F9`，无渐变
- 副标题: 次文字色 `#94A3B8`
- 强调词: 主强调色 `#38BDF8`

**CTA按钮 (保留轻微渐变)**
- bg: `linear-gradient(135deg, #2563EB, #1D4ED8)`
- 范围: 仅限主要行动按钮

**装饰性渐变 (背景装饰)**
- 现有: 彩虹渐变 (靛蓝→紫→青→绿)
- 改为: 单色渐变 (深蓝→天蓝，低透明度)

#### 动画策略

**时长**
- 微交互: 150ms
- 标准过渡: 200-300ms
- 复杂动画: 400ms (减少使用)

**缓动函数**: `ease-out` 为主

**范围**
- 保留: 页面入场、消息气泡
- 弱化: shimmer效果、持续动画

#### GradientText 组件调整

```
variant="default" → 纯色文字 (默认)
variant="subtle" → 深蓝微渐变
variant="shimmer" → 移除或仅用于加载状态
```

## 改造文件清单

### 需要修改的文件

1. **全局样式**: `app/globals.css`
   - 更新所有 CSS 变量
   - 更新玻璃效果类
   - 更新渐变文字类
   - 更新滚动条、选中、聚焦样式

2. **Tailwind 配置**: `tailwind.config.ts`
   - 更新 academic 颜色配置
   - 添加新的设计 tokens
   - 更新动画配置

3. **玻璃组件**: `components/glass/`
   - `liquid-glass-card.tsx` (更新样式)
   - `gradient-text.tsx` (弱化渐变，添加纯色模式)

4. **UI 组件**: `components/ui/`
   - `button.tsx` (更新变体颜色)
   - `input.tsx` (更新样式)
   - `card.tsx` (更新样式)
   - `badge.tsx` (更新颜色)

5. **页面组件** (样式微调):
   - `app/page.tsx` (首页背景、按钮)
   - `app/workspaces/page.tsx` (列表样式)
   - `app/(workbench)/workspaces/[id]/` (工作台面板样式)

6. **布局**: `app/layout.tsx` (确保 dark class 正确)

### 不需要修改的文件

- `lib/` 目录 (工具函数)
- `stores/` 目录 (状态管理)
- `hooks/` 目录 (自定义 hooks)
- API 相关文件

## 预计改动量

- CSS 变量重写：约 60 行
- 组件样式调整：约 200-300 行
- Tailwind 配置：约 30 行

## 参考设计

- Overleaf 暗色模式
- Notion 学术版
- Linear (极简交互)
- Nature/Science 品牌调性 (金色点缀)

---

*设计确认日期: 2026-03-10*
*设计方案: 学术深空风*
