# AcademiaGPT v2 架构优化设计文档

**日期**: 2026-03-09
**策略**: 先深后广 - 渐进式管道融合（方案A）
**目标**: 以 deer-flow 核心 Agent 架构为骨架，融合学术中间件，提升原有功能能力上限

---

## 1. 设计概述

### 1.1 背景

AcademiaGPT v2 是 AcademiaGPT v1（Vue 3 + CrewAI 多Agent学术写作平台）与 deer-flow（LangGraph Lead Agent 通用框架）的融合重构体。当前状态：

- **已完成**: Lead Agent 基础架构、5层学术中间件、8个Skills定义、790+测试、Next.js前端
- **缺失**: deer-flow 的 6 个关键中间件、子Agent并行系统、持久Memory、MCP集成、配置驱动
- **退化**: v1 的 10 个工作流模块在 v2 中降级为 SKILL.md 定义，执行框架不完善

### 1.2 优化策略

**渐进式管道融合** - 4 个阶段：

1. **Phase 1**: 管道基础设施（deer-flow 骨架 + 学术中间件融合 = 16层管道）
2. **Phase 2**: Agent 执行引擎（子Agent并行 + Memory + 配置驱动）
3. **Phase 3**: 核心学术功能重写（Deep Research / Framework / Full Paper）
4. **Phase 4**: 工具生态（MCP集成 + 动态工具加载 + 沙箱）

**前端策略**: 后端优先，前端只做必要的API适配，全面升级放在下一轮。

---

## 2. 统一 ThreadState 设计

### 2.1 融合状态模型

```python
class AcademicThreadState(AgentState):
    """Unified state: deer-flow base + academic extensions"""

    # === deer-flow 基础字段 ===
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]

    # === 学术扩展字段 ===
    workspace_id: NotRequired[str | None]
    workspace_config: NotRequired[dict | None]
    literature_context: NotRequired[str | None]
    knowledge_context: NotRequired[str | None]
    discipline_norms: NotRequired[str | None]
    cited_papers: Annotated[list[str], merge_cited]
    academic_artifacts: NotRequired[list[dict] | None]
    current_skill: NotRequired[str | None]
```

### 2.2 设计要点

- 继承 `AgentState`（LangGraph标准协议）
- 学术字段用 `NotRequired`，基础Chat无学术上下文时不加载
- `cited_papers` 自定义 reducer 去重合并
- `workspace_config` 是 JSONB dict，灵活适配 paper_type

---

## 3. 16 层中间件管道设计

### 3.1 完整管道（严格执行顺序）

```
┌─ 基础设施层 ─────────────────────────────────────────────┐
│  1. ThreadDataMiddleware      → 创建线程目录              │
│  2. UploadsMiddleware         → 追踪上传文件              │
│  3. SandboxMiddleware         → 获取沙箱实例              │
├─ 修复层 ────────────────────────────────────────────────┤
│  4. DanglingToolCallMiddleware → 修补缺失ToolMessage      │
├─ 上下文管理层 ──────────────────────────────────────────┤
│  5. SummarizationMiddleware   → Token超限自动摘要压缩     │
│  6. MemoryMiddleware          → 异步Memory更新            │
├─ 学术上下文层 ──────────────────────────────────────────┤
│  7. WorkspaceContextMiddleware → 加载workspace配置        │
│  8. LiteratureContextMiddleware → ToC文献导航注入         │
│  9. KnowledgeContextMiddleware → 加载知识库artifacts      │
│ 10. DisciplineContextMiddleware → 注入学科写作规范        │
├─ 交互层 ────────────────────────────────────────────────┤
│ 11. TodoListMiddleware        → Plan模式任务追踪          │
│ 12. ViewImageMiddleware       → Vision模型图片注入        │
│ 13. SubagentLimitMiddleware   → 子Agent并发限制(2-4)      │
├─ 后处理层 ──────────────────────────────────────────────┤
│ 14. TitleMiddleware           → 自动生成线程标题          │
│ 15. CitationContextMiddleware → 引用追踪(after_model)     │
│ 16. ClarificationMiddleware   → 拦截ask_clarification     │
└──────────────────────────────────────────────────────────┘
```

### 3.2 层序设计理由

| 层 | 位置理由 |
|----|---------|
| 基础设施层(1-3) | 最先执行，确保目录/文件/沙箱准备就绪 |
| 修复层(4) | 在注入上下文前修补消息完整性 |
| 上下文管理层(5-6) | 处理"对话历史"维度，在学术上下文之前 |
| 学术上下文层(7-10) | 处理"领域知识"维度，在摘要之后避免被压缩 |
| 交互层(11-13) | 与Agent执行直接相关的控制 |
| 后处理层(14-16) | 模型输出后的处理，ClarificationMiddleware必须最后 |

### 3.3 条件启用

- 基础设施层: 始终启用
- 学术层: 仅当 `workspace_id` 存在时
- 沙箱层: 仅当 config.sandbox 启用时
- Memory层: 仅当 config.memory.enabled 时

---

## 4. 子 Agent 并行执行系统

### 4.1 架构

```
Lead Agent (主线程)
    │
    ├── task("scout", params)  ─→ SubagentExecutor
    │                              │
    │   ┌──────────────────────────┘
    │   ├── _scheduler_pool (3 workers) → 任务编排
    │   ├── _execution_pool (3 workers) → 实际执行
    │   ├── Timeout: 15min per subagent
    │   └── SSE Events: task_started → task_running → task_completed
    │
    └── 异步轮询 (5s intervals) → 收集结果
```

### 4.2 学术子 Agent 类型

```yaml
subagents:
  enabled: true
  max_concurrent: 4
  types:
    # 研究类
    scout:        { tools: [semantic_scholar, web_search, read_file], max_turns: 10, timeout: 300 }
    gap_miner:    { tools: [read_file, web_search], max_turns: 8 }
    trend_spotter: { tools: [semantic_scholar, web_search], max_turns: 8 }
    synthesizer:  { tools: [read_file], max_turns: 6 }
    # 写作类
    writer:       { tools: [read_file, write_file, semantic_scholar], max_turns: 15, timeout: 600 }
    reviewer:     { tools: [read_file], max_turns: 8 }
    librarian:    { tools: [semantic_scholar, read_file], max_turns: 10 }
    # 通用类
    analyst:      { tools: [read_file, bash], max_turns: 10 }
    general:      { disallowed: [task], max_turns: 15 }
```

---

## 5. 持久化 Memory 系统

### 5.1 学术 Memory 结构

```json
{
  "version": "1.0",
  "user": {
    "researchContext": { "summary": "研究方向和领域...", "updatedAt": "..." },
    "writingPreferences": { "summary": "写作风格偏好...", "updatedAt": "..." },
    "toolPreferences": { "summary": "模型和工具偏好...", "updatedAt": "..." }
  },
  "history": {
    "recentWorkspaces": { "summary": "最近工作空间...", "updatedAt": "..." },
    "completedResearch": { "summary": "已完成研究...", "updatedAt": "..." }
  },
  "facts": [
    { "content": "用户学科: 计算机科学-NLP", "category": "knowledge", "confidence": 0.95 },
    { "content": "偏好先Deep Research再Framework", "category": "behavior", "confidence": 0.8 }
  ]
}
```

### 5.2 学术 Memory 注入点

- **Skill 执行前**: 注入研究领域、写作偏好
- **文献检索时**: 注入关注方向和既往研究
- **写作生成时**: 注入风格偏好和学科规范
- **新工作空间创建**: 基于历史推荐 paper_type

---

## 6. 配置驱动架构

### 6.1 统一 config.yaml

```yaml
models:
  - name: deepseek-v3
    use: langchain_openai:ChatOpenAI
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    tags: [generation, default]
  # ... more models

tools:
  - name: semantic_scholar_search
    use: src.academic.tools.semantic_scholar:search_tool
    group: academic_search

subagents:
  enabled: true
  max_concurrent: 4
  types: { ... }

memory:
  enabled: true
  injection_enabled: true
  storage_path: "backend/.academiagpt/memory.json"

skills:
  path: "backend/skills"

sandbox:
  use: src.sandbox.local:LocalSandboxProvider

middlewares:
  summarization: { enabled: true, trigger: "tokens:80000" }
  academic: { workspace_context: true, literature_context: true, ... }
```

### 6.2 核心价值

- 新增模型/工具/子Agent: 改 config.yaml，无需改代码
- 功能开关: 配置切换，不删代码
- 环境适配: `$ENV_VAR` 自动解析
- 动态反射加载: `use: package.module:variable` 模式

---

## 7. 核心学术功能重写

### 7.1 Deep Research（子Agent并行化）

```
Phase 1 (并行): Scout ×2 + Trend Spotter     → papers[], trends[]
Phase 2 (依赖1): Gap Miner                    → gaps[]
Phase 3 (依赖2): Synthesizer                  → ideas[]
Phase 4 (并行): Novelty Check + Feasibility    → qualified_ideas[]
Phase 5 (依赖4): Lead Agent 精炼输出           → Context Hub artifacts
```

**提速**: 串行 ~10-15min → 并行 ~5-6min（约50%）

### 7.2 Framework Designer（Lead Agent + Memory 增强）

```
Memory注入 + Context Hub读取 + 文献导航 + 学科规范
→ Lead Agent 直接生成大纲（单步，不需子Agent）
→ framework_outline artifact（用户可编辑）
```

### 7.3 Full Paper Writer（Framework驱动 + 学术写作顺序）

**核心原则**: 遵循真实学术写作顺序，摘要最后写。

```
Phase 0: Enhanced Framework（在用户Framework基础上补充协调信息）
    → terminology_glossary, chapter_dependencies, citation_targets
    → 不覆盖用户编辑的framework

Phase 1 (串行): Methodology（全文基石）
Phase 2 (并行): Experiments + Related Work（互不依赖）
Phase 3 (依赖1+2): Introduction（需预告实验发现）
Phase 4 (依赖全部): Conclusion
Phase 5 (最后): Abstract（包含真实实验数据，如"精度提升X%"）
Phase 6: 连贯性审查 + 引用校验
```

**写作顺序 DAG**:
```
Methodology → Experiments ──┐
         └──→ Related Work ─┼──→ Introduction → Conclusion → Abstract
```

**连贯性保障机制**:

| 机制 | 说明 |
|------|------|
| Framework 驱动 | 用户编辑的大纲作为写作蓝图 |
| Enhanced Framework | 系统附加术语表/依赖关系（不修改用户内容） |
| prev_chapters 注入 | 依赖链章节收到前序章节原文 |
| terminology_glossary | 全局术语表，所有writer统一用词 |
| Phase 6 审查 | 专门的连贯性审查步骤 |

**提速**: 约30%（Phase 2 并行 + 学术正确的写作顺序）

---

## 8. 实施阶段规划

### Phase 1: 管道基础设施（预估工作量: 大）

1. 扩展 ThreadState → AcademicThreadState
2. 移植 deer-flow 缺失的 6 个中间件（ThreadData, Uploads, Sandbox, Dangling, Summarization, Memory 等）
3. 将现有 5 个学术中间件适配 AgentMiddleware 协议
4. 组装 16 层管道
5. 建立 config.yaml 配置系统 + Reflection 动态加载
6. 验证: 基础 Chat 功能正常，所有测试通过

### Phase 2: Agent 执行引擎（预估工作量: 大）

1. 移植 SubagentExecutor（ThreadPoolExecutor + 超时 + SSE）
2. 实现学术子Agent类型注册
3. 移植 Memory 系统并适配学术领域
4. Skill 执行器改造（SKILL.md → 调用 Subagent 链）
5. 验证: 子Agent可独立执行和并行

### Phase 3: 核心学术功能重写（预估工作量: 大）

1. Deep Research Skill 重写（子Agent并行化）
2. Framework Designer Skill 重写（Memory增强）
3. Full Paper Writer Skill 重写（学术顺序 + 分层并行）
4. Context Hub 集成增强（artifact 自动流转）
5. 验证: 端到端学术工作流完整运行

### Phase 4: 工具生态（预估工作量: 中）

1. MCP 集成框架移植
2. 学术 MCP 工具（arXiv, PubMed, DOI 解析器等）
3. 沙箱执行环境
4. 前端 API 适配
5. 验证: 工具可动态加载和执行

---

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 16层管道性能开销 | 学术中间件条件启用，无workspace_id时跳过 |
| 中间件迁移打破现有测试 | 渐进式迁移，每层完成后跑全量测试 |
| 子Agent并行增加复杂度 | SubagentLimitMiddleware 限流 + 超时保护 |
| Memory 存储膨胀 | max_facts 限制 + confidence 阈值过滤 |
| config.yaml 复杂度 | 分层配置 + sensible defaults |

---

## 10. 成功标准

- [ ] 16层中间件管道完整运行，基础Chat + 学术Chat 均正常
- [ ] 子Agent可并行执行，Deep Research 提速 ~50%
- [ ] Memory 系统跨会话记忆用户研究偏好
- [ ] config.yaml 统一配置，新增模型/工具无需改代码
- [ ] Full Paper 遵循学术写作顺序，摘要包含实验数据
- [ ] 所有现有测试继续通过 + 新增架构测试覆盖
