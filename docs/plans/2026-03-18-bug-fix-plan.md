# Bug Fix Plan - P0 & P1 Issues

**Date:** 2026-03-18
**Type:** Bug Fix Implementation Plan
**Priority:** P0 (阻断上线) → P1 (强烈建议)

---

## Overview

本计划针对 UX Review 中确认的 P0 和 P1 级别问题，按照 systematic debugging 流程制定修复方案。

**修复原则：**
1. 一次只修复一个问题
2. 为每个修复添加测试验证
3. 修复后验证无副作用
4. 优先修复 P0 阻断上线的问题

---

## Phase 1: P0 Issues (阻断上线 - 必须修复)

### Fix P0-1: 导出功能按钮为占位符

**问题位置:** `compile-export/page.tsx:158-166`

**Root Cause:**
- 导出格式按钮缺少 onClick 处理器
- 没有实际的导出逻辑

**修复方案:**
1. **短期方案（推荐）：** 暂时移除这些按钮，避免用户困惑
2. **长期方案：** 实现真实的导出功能

**实施步骤:**

#### 方案 A: 暂时移除按钮（快速修复）

```typescript
// 在 compile-export/page.tsx 中
// 将第 153-168 行的导出格式部分改为：

{/* Export Options - Coming Soon */}
<div className="mt-6 pt-6 border-t border-[var(--border-default)]">
  <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
    导出格式
  </h3>
  <p className="text-sm text-[var(--text-muted)]">
    多格式导出功能即将推出，敬请期待
  </p>
</div>
```

#### 方案 B: 添加"即将推出"提示（保留按钮）

```typescript
{/* Export Options */}
<div className="mt-6 pt-6 border-t border-[var(--border-default)]">
  <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
    导出格式
  </h3>
  <div className="space-y-2">
    {["PDF", "Word (.docx)", "LaTeX (.tex)", "Markdown"].map((format) => (
      <button
        key={format}
        onClick={() => {
          toast.info(`${format} 导出功能即将推出`);
        }}
        className="w-full flex items-center gap-2 p-2 bg-[var(--bg-elevated)] rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] opacity-50 cursor-not-allowed"
      >
        <Download className="w-4 h-4" />
        {format}
        <span className="ml-auto text-xs text-[var(--text-muted)]">即将推出</span>
      </button>
    ))}
  </div>
</div>
```

**测试验证:**
- [ ] 点击按钮不再无反应
- [ ] 显示友好的提示信息
- [ ] 不影响现有编译 PDF 功能

---

### Fix P0-2: 图表生成章节关联硬编码

**问题位置:** `figure-generation/page.tsx:114-124`

**Root Cause:**
- 章节下拉框硬编码，未从 thesis_writing 的 artifact 动态获取

**修复方案:**
从 workspace artifacts 中获取实际的章节列表

**实施步骤:**

```typescript
// 在 figure-generation/page.tsx 中添加

// 1. 从 useWorkspaceStore 获取 artifacts
const { artifacts } = useWorkspaceStore();

// 2. 提取章节列表
const chapters = useMemo(() => {
  const outlineArtifact = artifacts.find(
    (a) => a.type === "thesis_outline" || a.type === "outline"
  );

  if (!outlineArtifact?.content) return [];

  const content = outlineArtifact.content as Record<string, unknown>;
  const chaptersList = content.chapters as Array<Record<string, unknown>> | undefined;

  if (!chaptersList) return [];

  return chaptersList.map((chapter, index) => ({
    index: index + 1,
    title: String(chapter.title || `第${index + 1}章`),
  }));
}, [artifacts]);

// 3. 替换硬编码的章节选择器（第 110-125 行）
<div>
  <label className="block text-xs text-[var(--text-muted)] mb-1">
    关联章节
  </label>
  <select
    className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
    value={chapterIndex}
    onChange={(e) => setChapterIndex(e.target.value)}
  >
    <option value="">不关联</option>
    {chapters.length > 0 ? (
      chapters.map((ch) => (
        <option key={ch.index} value={ch.index}>
          {ch.title}
        </option>
      ))
    ) : (
      // Fallback: 如果没有大纲，显示提示
      <>
        <option value="1">第一章</option>
        <option value="2">第二章</option>
        <option value="3">第三章</option>
        <option value="4">第四章</option>
      </>
    )}
  </select>
  {chapters.length === 0 && (
    <p className="text-xs text-[var(--text-muted)] mt-1">
      请先生成论文大纲以获取章节列表
    </p>
  )}
</div>
```

**测试验证:**
- [ ] 当有 thesis_outline artifact 时，显示实际章节
- [ ] 当无大纲时，显示默认 4 章作为 fallback
- [ ] 显示提示信息引导用户先生成大纲

---

### Fix P0-3: 添加文献按钮无功能

**问题位置:** `literature/page.tsx:121-124`

**Root Cause:**
- 按钮缺少 onClick 处理器

**修复方案:**
实现添加文献的功能或显示"即将推出"提示

**实施步骤:**

#### 方案 A: 实现 Add Literature Modal

```typescript
// 1. 添加 state
const [showAddModal, setShowAddModal] = useState(false);
const [newLit, setNewLit] = useState({
  title: "",
  authors: "",
  year: "",
  doi: "",
});

// 2. 实现添加功能
const handleAddLiterature = async () => {
  if (!newLit.title.trim()) return;

  try {
    // 调用 API 添加文献
    await addLiterature(workspaceId, {
      title: newLit.title,
      authors: newLit.authors.split(",").map((a) => a.trim()),
      year: newLit.year ? parseInt(newLit.year) : undefined,
      doi: newLit.doi || undefined,
    });

    // 刷新列表
    await fetchLiterature(workspaceId);

    // 关闭 modal 并重置
    setShowAddModal(false);
    setNewLit({ title: "", authors: "", year: "", doi: "" });
  } catch (error) {
    console.error("Failed to add literature:", error);
  }
};

// 3. 更新按钮
<button
  onClick={() => setShowAddModal(true)}
  className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-muted)] transition-colors"
>
  <Plus className="w-4 h-4" />
  添加文献
</button>

// 4. 添加 Modal 组件（参考 Create Workspace Modal）
```

#### 方案 B: 快速修复 - 显示"即将推出"

```typescript
<button
  onClick={() => toast.info("手动添加文献功能即将推出，请使用'从 Deep Research 导入'")}
  className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-muted)] transition-colors"
>
  <Plus className="w-4 h-4" />
  添加文献
</button>
```

**测试验证:**
- [ ] 点击按钮有响应
- [ ] 如果实现 modal，验证表单提交和验证
- [ ] 如果显示提示，验证提示信息友好

---

### Fix P0-4: 筛选按钮无功能

**问题位置:** `literature/page.tsx:176-179`

**Root Cause:**
- 筛选按钮缺少 onClick 处理器和筛选逻辑

**修复方案:**
实现筛选功能或显示"即将推出"提示

**实施步骤:**

#### 方案 A: 实现筛选功能

```typescript
// 1. 添加筛选 state
const [showFilters, setShowFilters] = useState(false);
const [filters, setFilters] = useState({
  yearFrom: "",
  yearTo: "",
  isCore: "",
});

// 2. 实现筛选逻辑
const filteredItems = useMemo(() => {
  let result = items;

  // 文本搜索
  if (searchQuery) {
    const query = searchQuery.toLowerCase();
    result = result.filter(
      (lit) =>
        lit.title.toLowerCase().includes(query) ||
        lit.authors.some((a) => a.toLowerCase().includes(query))
    );
  }

  // 年份筛选
  if (filters.yearFrom) {
    result = result.filter((lit) => lit.year >= parseInt(filters.yearFrom));
  }
  if (filters.yearTo) {
    result = result.filter((lit) => lit.year <= parseInt(filters.yearTo));
  }

  // 核心文献筛选
  if (filters.isCore === "true") {
    result = result.filter((lit) => lit.is_core);
  } else if (filters.isCore === "false") {
    result = result.filter((lit) => !lit.is_core);
  }

  return result;
}, [items, searchQuery, filters]);

// 3. 添加筛选面板（Dropdown）
<div className="relative">
  <button
    onClick={() => setShowFilters(!showFilters)}
    className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
  >
    <Filter className="w-4 h-4" />
    筛选
  </button>

  {showFilters && (
    <div className="absolute top-full mt-2 right-0 w-64 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg shadow-lg p-4 z-10">
      {/* Filter controls */}
      <div className="space-y-3">
        <div>
          <label className="text-xs text-[var(--text-muted)]">年份范围</label>
          <div className="flex gap-2 mt-1">
            <input
              type="number"
              placeholder="起始"
              value={filters.yearFrom}
              onChange={(e) => setFilters({ ...filters, yearFrom: e.target.value })}
              className="w-full px-2 py-1 text-sm bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded"
            />
            <input
              type="number"
              placeholder="结束"
              value={filters.yearTo}
              onChange={(e) => setFilters({ ...filters, yearTo: e.target.value })}
              className="w-full px-2 py-1 text-sm bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded"
            />
          </div>
        </div>

        <div>
          <label className="text-xs text-[var(--text-muted)]">文献类型</label>
          <select
            value={filters.isCore}
            onChange={(e) => setFilters({ ...filters, isCore: e.target.value })}
            className="w-full mt-1 px-2 py-1 text-sm bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded"
          >
            <option value="">全部</option>
            <option value="true">核心文献</option>
            <option value="false">非核心文献</option>
          </select>
        </div>

        <button
          onClick={() => setFilters({ yearFrom: "", yearTo: "", isCore: "" })}
          className="w-full text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          清除筛选
        </button>
      </div>
    </div>
  )}
</div>

// 4. 使用 filteredItems 替换 items.map()
```

#### 方案 B: 快速修复 - 隐藏或禁用按钮

```typescript
// 选项 1: 隐藏按钮（删除第 176-179 行）

// 选项 2: 禁用按钮并显示提示
<button
  disabled
  className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-muted)] cursor-not-allowed"
  title="筛选功能即将推出"
>
  <Filter className="w-4 h-4" />
  筛选
</button>
```

**测试验证:**
- [ ] 如果实现筛选，验证各项筛选条件正确
- [ ] 验证清除筛选功能
- [ ] 验证筛选结果与搜索条件匹配

---

### Fix P0-5: 积分系统提示处理

**问题位置:** `literature/page.tsx:146`

**Root Cause:**
- 显示"智能盘点（20积分）"但未解释积分系统
- 用户不知道积分从哪来、怎么用

**修复方案:**
添加 Tooltip 或说明文字，或者暂时移除积分显示

**实施步骤:**

#### 方案 A: 添加 Tooltip 说明

```typescript
// 1. 添加 Tooltip 组件（使用 Radix UI 或自定义）
import { Tooltip } from "@/components/ui/tooltip";

// 2. 更新按钮
<Tooltip
  content={
    <div className="max-w-xs">
      <p className="font-medium mb-1">智能盘点功能</p>
      <p className="text-sm">
        该功能使用 AI 自动分析并整理您的文献库，需要消耗 20 积分。
        积分可通过注册、每日签到等方式获得。
      </p>
    </div>
  }
>
  <button
    className={cn(
      "flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors",
      isOrganizing ? "bg-emerald-500 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-700"
    )}
    onClick={handleOrganize}
    disabled={isOrganizing}
  >
    <BookOpen className="w-4 h-4" />
    {isOrganizing ? "盘点中..." : "智能盘点（20积分）"}
  </button>
</Tooltip>
```

#### 方案 B: 暂时移除积分显示

```typescript
<button
  className={cn(
    "flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors",
    isOrganizing ? "bg-emerald-500 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-700"
  )}
  onClick={handleOrganize}
  disabled={isOrganizing}
>
  <BookOpen className="w-4 h-4" />
  {isOrganizing ? "盘点中..." : "智能盘点"}
</button>
```

**测试验证:**
- [ ] 如果添加 Tooltip，验证显示和内容
- [ ] 如果移除积分显示，确认按钮文案清晰

---

## Phase 2: P1 Issues (强烈建议修复)

### Fix P1-1: 语言混合

**问题位置:** `workspaces/[id]/page.tsx:23-29`

**Root Cause:**
- `workspaceTypeLabels` 使用英文，其他地方使用中文

**修复方案:**
统一为中文标签

**实施步骤:**

```typescript
// 在 workspaces/[id]/page.tsx 第 23-29 行
const workspaceTypeLabels: Record<string, string> = {
  sci: "学术论文",
  thesis: "学位论文",
  proposal: "研究计划",
  software_copyright: "软件著作权申请",
  patent: "专利申请",
};
```

**测试验证:**
- [ ] 所有 workspace 类型标签显示为中文
- [ ] 与其他 UI 文字风格一致

---

### Fix P1-12: Workspace 计数不准确

**问题位置:** `workspaces/page.tsx:189-190`

**Root Cause:**
- `paperCount` 和 `artifactCount` 硬编码为 0

**修复方案:**
从 API 或 workspace 对象获取真实数据

**实施步骤:**

```typescript
// 1. 检查 Workspace 类型定义，添加计数字段
interface Workspace {
  id: string;
  name: string;
  type: string;
  discipline?: string;
  description?: string;
  created_at: string;
  paper_count?: number;      // 添加
  artifact_count?: number;   // 添加
}

// 2. 在 workspaces/page.tsx 中更新 WorkspaceCard 调用
<WorkspaceCard
  id={workspace.id}
  name={workspace.name}
  type={workspace.type as "sci" | "thesis" | "proposal" | "software_copyright" | "patent"}
  discipline={workspace.discipline}
  paperCount={workspace.paper_count ?? 0}
  artifactCount={workspace.artifact_count ?? 0}
  createdAt={workspace.created_at.split("T")[0]}
/>

// 3. 如果 API 不返回计数，可以在前端计算
// 在 useWorkspaceStore 中添加计算逻辑
```

**测试验证:**
- [ ] Workspace 卡片显示真实的计数
- [ ] 计数与实际 artifacts 数量一致

---

### Fix P1-5: Step 禁用状态提示

**问题位置:** `thesis-writing/page.tsx:296-302`

**Root Cause:**
- Step 2 禁用时只有 opacity 变化，没有说明

**修复方案:**
添加 Tooltip 说明"请先生成大纲"

**实施步骤:**

```typescript
// 在 thesis-writing/page.tsx 第 294-306 行
<button
  onClick={() => setStep(2)}
  disabled={!outline}
  title={!outline ? "请先生成大纲" : undefined}
  className={cn(
    "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
    currentStep === 2
      ? "bg-purple-600 text-white"
      : "bg-[var(--bg-surface)] text-[var(--text-secondary)]",
    !outline && "opacity-50 cursor-not-allowed"
  )}
>
  Step 2: 全文写作
</button>
```

**或使用更友好的视觉提示:**

```typescript
<div className="flex items-center gap-2">
  <button
    onClick={() => setStep(2)}
    disabled={!outline}
    title={!outline ? "请先生成大纲" : undefined}
    className={cn(
      "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
      currentStep === 2
        ? "bg-purple-600 text-white"
        : "bg-[var(--bg-surface)] text-[var(--text-secondary)]",
      !outline && "opacity-50 cursor-not-allowed"
    )}
  >
    Step 2: 全文写作
  </button>
  {!outline && (
    <span className="text-xs text-[var(--text-muted)]">
      需要先完成 Step 1
    </span>
  )}
</div>
```

**测试验证:**
- [ ] 鼠标悬停在禁用按钮上显示提示
- [ ] 或显示文字提示说明原因

---

## Implementation Order

**推荐修复顺序：**

1. **P0-1** - 导出功能按钮（快速修复：暂时移除或显示"即将推出"）
2. **P0-5** - 积分系统提示（快速修复：移除积分显示）
3. **P0-3** - 添加文献按钮（快速修复：显示"即将推出"）
4. **P0-4** - 筛选按钮（快速修复：禁用或隐藏）
5. **P0-2** - 图表生成章节关联（需要实现逻辑）
6. **P1-1** - 语言混合（简单替换）
7. **P1-5** - Step 禁用状态提示（添加 Tooltip）
8. **P1-12** - Workspace 计数（需要 API 支持）

**时间估算：**
- 快速修复（P0-1, P0-5, P0-3, P0-4, P1-1, P1-5）：1-2 小时
- 逻辑修复（P0-2）：2-3 小时
- API 集成（P1-12）：需要后端支持

---

## Testing Strategy

**每个修复后需验证：**
1. 修复的功能正常工作
2. 没有引入新的 bug
3. UI 显示正确
4. 用户交互友好

**回归测试：**
- 运行现有的测试套件
- 手动测试相关页面
- 检查控制台无错误

---

## Notes

1. 本计划优先处理 P0 阻断上线的问题
2. 对于需要复杂实现的功能，推荐先采用快速修复方案
3. 长期方案可以在后续迭代中实现
4. 建议每个修复都创建独立的 PR 以便于审查和回滚
