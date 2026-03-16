# AcademiaGPT-V2 全量恢复设计文档（Phase 1 + Phase 2）

> **状态**: 已确认（用户于 2026-03-16 确认 C 方案）
> **范围**: Thesis 工作区核心闭环恢复 + 计费/任务治理收口

## 1. 背景与目标

当前 `AcademiaGPT-V2` 已具备统一的 feature 执行骨架，但仍存在“可跑通不等于可用”的断层：

1. `thesis_writing` 可提交任务，但章节写作仍以模板化内容为主，`write_all` 路径在章节沉淀方面不完整。
2. `figure_generation` 已接通前后端，但执行层 provider 未补齐，导致 `mermaid` 与 `kling` 场景大量降级。
3. Deep Research 产物与文献管理之间缺少前端入口闭环。
4. `/api/papers/upload` 仍为 TODO 空壳。
5. 计费与任务治理仍有分散配置、幂等缺失和队列失败状态语义不完整问题。

本设计目标是通过两阶段恢复，将系统从“功能骨架”提升为“可执行、可追踪、可治理”的稳定形态。

## 2. 范围定义

### 2.1 Phase 1（功能可用恢复）

1. 恢复 `thesis_writing` 的可用输出链路（大纲与章节 artifact 结构化、可回显）。
2. 恢复 `figure_generation` 的最小真实执行路径（优先 `mermaid`）。
3. 接通 Deep Research -> Literature 导入前端入口。
4. 实现 `/api/papers/upload` 最小可用能力（文件保存 + 元信息返回 + 可诊断失败）。

### 2.2 Phase 2（治理收口恢复）

1. 计费规则单一真源（policy centralized）。
2. `execute feature` 幂等保护（防重复扣费/重复任务）。
3. `TaskService.submit_task` 提交一致性修复（队列失败不留脏 pending）。
4. Dashboard 状态模型升级，补 `failed` 语义。

### 2.3 非目标

1. 不做新 workspace 类型与新 feature 扩展。
2. 不做大规模 UI 重设计，仅做闭环和状态一致性增强。
3. 不做内容质量深度优化（如长链路 prompt 工程重构）。

## 3. 现状问题归纳

### 3.1 Thesis 写作链路

- `generate_outline_only` 与 `write_single_chapter` 已能落 artifact，但内容来源偏模板化。
- `write_all` 走 LangGraph，`section_writer_node` 仅标记 writing，不完成章节正文沉淀。
- 前端写作页可触发任务与显示章节状态，但未稳定加载章节正文内容作为“可读/可编辑”主载体。

### 3.2 图表执行链路

- `thesis_feature_service.build_figure_payload` 已支持 `generated/degraded` 双分支。
- `DockerExecutionService.PROVIDER_MAP` 仅注册 `LATEX_COMPILE` 与 `PYTHON_PLOT`。
- 缺少 `MERMAID_DIAGRAM` provider 导致流程图路径不可真实执行。

### 3.3 治理链路

- `BILLABLE_TASK_TYPES` 与 `WORKFLOW_CREDIT_COSTS` 分散维护，规则漂移风险高。
- feature execute 缺幂等保护，可能重复扣费。
- `submit_task` 先写 DB 后投队列，投递失败时状态语义不完整。
- dashboard 失败态被挤压为 `in_progress`，语义不可信。

## 4. 目标架构

## 4.1 功能层（Phase 1）

统一链路保持：

`feature execute -> task dispatch -> handler/service -> artifact persist -> dashboard/frontend`

但补齐以下节点能力：

1. `thesis_writing_service` 统一封装 outline/chapter 生成逻辑（可融合文献与 Deep Research 上下文）。
2. Execution 层新增 `MermaidProvider` 并注册映射。
3. 文献页增加 Deep Research 导入触发，调用既有 store 能力。
4. `papers/upload` 实现最小文件持久化与元信息返回。

## 4.2 治理层（Phase 2）

1. 新增集中式 `feature_credit_policy`：
   - 提供 feature/action -> cost。
   - 提供 task_type 是否禁止直投判定。
2. feature execute 引入幂等窗口：
   - key = `user_id + workspace_id + feature_id + normalized_params_hash`。
3. `TaskService.submit_task` 补齐失败状态落库。
4. dashboard 与前端增加 `failed` 状态消费。

## 5. 组件设计

### 5.1 Thesis 写作恢复

1. 新增 service 层方法：
   - `build_outline_payload(...)`
   - `build_chapter_payload(...)`
2. `workspace_feature_handler` 中 `generate_outline_only/write_single_chapter` 迁移为调用 service，保留 artifact 落库语义不变。
3. `write_all` 路径在保持 workflow 的基础上，补充章节正文沉淀策略（至少保证最终可见产物）。
4. 前端 `thesis-writing` 页面：
   - 任务成功后从 artifact 列表解析章节正文。
   - 章节切换时可展示最近章节 markdown。

### 5.2 图表恢复

1. 创建 `src/execution/providers/mermaid.py`：
   - 输入 Mermaid 文本。
   - 输出 SVG 或 PNG 文件。
2. 在 `DockerExecutionService.PROVIDER_MAP` 注册 `ExecutionType.MERMAID_DIAGRAM`。
3. 保持 `kling` 降级策略（如 provider 缺失）并显式返回升级元数据。

### 5.3 Deep Research 导入入口恢复

1. 在 literature 页面新增“从 Deep Research 导入”操作区。
2. 调用 `useLiteratureStore.importFromDeepResearch(workspaceId, paperIds)`。
3. 导入后刷新文献列表与计数。

### 5.4 Papers Upload 最小实现

1. 上传文件写入 workspace 目录（含时间戳防冲突）。
2. 返回 `filename/content_type/size/saved_path`。
3. 若后续抽取失败，返回结构化错误字段（不假成功）。

### 5.5 计费与任务治理恢复

1. 新建 policy 模块并替换散点规则读取。
2. feature execute 在扣费前执行幂等查询：
   - 命中 pending/running 任务直接返回现有 task。
3. `submit_task` 捕获队列异常后更新 task 记录为 `failed(queue_submit_failed)` 并抛错。
4. dashboard 返回模块级 `failed`，前端文案显示失败摘要。

## 6. 数据契约

### 6.1 framework_outline

```json
{
  "paper_title": "string",
  "outline": {
    "abstract": "string",
    "keywords": ["string"],
    "chapters": [
      {
        "title": "string",
        "position": "string",
        "targetWords": 2500,
        "keyPoints": ["string"],
        "sections": ["string"]
      }
    ]
  },
  "generation_mode": "llm|template_fallback",
  "source_context": {
    "literature_count": 0,
    "deep_research_artifact_ids": ["string"]
  },
  "schema_version": "v1"
}
```

### 6.2 thesis_chapter

```json
{
  "paper_title": "string",
  "chapter_index": 1,
  "chapter_title": "string",
  "target_words": 2500,
  "estimated_words": 1800,
  "markdown": "string",
  "references_used": ["string"],
  "generation_mode": "llm|template_fallback",
  "schema_version": "v1"
}
```

### 6.3 figure

```json
{
  "figure_type": "flowchart|data_visualization|concept_map",
  "strategy": "mermaid|python|kling",
  "status": "generated|degraded",
  "render_data": {
    "file_path": "string",
    "format": "svg|png|pdf"
  },
  "source_code": "string",
  "prompt": "string",
  "upgrade": {
    "auto_upgrade": true,
    "required_execution_type": "mermaid_diagram",
    "provider_ready": false,
    "last_error": "string"
  }
}
```

### 6.4 papers/upload 响应

```json
{
  "success": true,
  "paper_id": "string|null",
  "file": {
    "filename": "string",
    "content_type": "application/pdf",
    "size": 123456,
    "saved_path": "string"
  },
  "extract": {
    "status": "saved|parsed|failed",
    "metadata": {},
    "error": "string|null"
  }
}
```

## 7. 错误处理策略

1. Provider 不可用：返回 `degraded` artifact，记录 `upgrade.last_error`。
2. 写作生成失败：任务标记 failed，并保留阶段性 metadata（phase、chapter_index）。
3. 幂等命中：返回已存在 task，不重复扣费。
4. 队列提交失败：任务记录显式失败原因 + 上层退款。
5. 上传失败：返回结构化错误（HTTP 4xx/5xx），不返回 `success=true`。

## 8. 测试策略

### 8.1 后端

1. `workspace_feature_handler`：
   - outline/chapter artifact 结构完整性。
2. `execution/service`：
   - Mermaid provider 路径可执行。
3. `gateway/features`：
   - 幂等命中返回已有 task。
4. `task/service`：
   - 队列失败状态语义。
5. `services/dashboard`：
   - `failed` 状态输出。
6. `gateway/academic`：
   - `/papers/upload` 成功与失败路径。

### 8.2 前端

1. `thesis-writing`：章节正文可见与状态同步。
2. `literature`：Deep Research 导入入口可用。
3. TypeScript 检查 `npx tsc --noEmit` 通过。

## 9. 迁移与发布策略

1. 先上线 Phase 1（功能恢复）并验证核心闭环。
2. 再上线 Phase 2（治理收口），避免一次性高风险变更。
3. 每个阶段均采用小步提交 + 可回滚策略。

## 10. 验收标准（DoD）

1. `thesis_writing` 可稳定生成并回显 outline/chapter 内容。
2. `figure_generation` 的 `mermaid` 路径可真实产出文件。
3. 文献页可从 Deep Research 导入并更新统计。
4. `/papers/upload` 不再是 TODO 空壳。
5. execute 重复提交不重复扣费。
6. 队列失败不留下长期 pending 脏任务。
7. dashboard 模块状态可出现 `failed` 且前端正确展示。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 幂等误命中导致新任务无法创建 | 缩短窗口并严格比较 params hash |
| Mermaid 运行环境不完整 | provider health check + degraded fallback |
| 计费改造引入行为回归 | 双读比对日志后切换单源 |
| 状态枚举改动影响前端 | 先后端兼容输出，再前端切换 |

