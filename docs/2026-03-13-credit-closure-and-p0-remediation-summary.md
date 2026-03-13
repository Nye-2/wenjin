# 2026-03-13 积分闭环与 Thesis Workspace P0 修复总结

## 1. 文档目的

本文档用于归档截至 **2026-03-13** 的以下内容：

1. 本阶段已经完成的关键改动（含此前轮次与本轮修复）。
2. 已修复项的影响范围与行为变化。
3. 当前残余问题清单（按优先级）。
4. 下一步可直接执行的工程建议。

---

## 2. 已完成工作总览

### 2.1 积分消费闭环与绕过封堵（此前轮次已完成）

1. `thesis.literature_management` 从占位改为真实执行逻辑。  
   - 新增可执行 payload 构建：`build_literature_management_payload`（统计、质量检查、建议动作）。
   - handler 已走统一 `workspace_feature` 执行链并落库 artifact。

2. 前端文献管理页接入可计费执行入口。  
   - 页面按钮已调用 `executeWorkspaceFeature("literature_management")`，并轮询任务状态后刷新文献与产物。

3. 阻断通过 `/api/tasks` 直接提交可计费 task type 的绕过路径。  
   - 对 `workspace_feature / deep_research / thesis_generation / literature_search` 在 `/api/tasks/` 直接提交时返回错误，要求走 feature execute 入口做计费。

4. 旧接口 `/api/thesis/generate` 纳入计费。  
   - 提交前扣费（`feature_id=thesis_writing`, `action=write_all`）。
   - 积分不足返回 `402`。
   - 排队失败退款，并将 `credit_transaction_id` / `credit_cost` 写入任务 payload。
   - 任务入队成功后回写 `task_id` 到交易记录。

---

### 2.2 Thesis Workspace 执行闭环增强（此前轮次已完成）

1. `figure_generation`：支持 provider 未就绪时降级产出（源码/提示词 artifact），后续可升级渲染。
2. `compile_export`：从 workspace artifacts + literature 组装 LaTeX，尝试真实编译，失败也保留可复用草稿与日志。
3. `opening_research`：模板优先、LLM 可选生成，统一输出结构化报告 artifact。

---

### 2.3 本轮 P0 修复（本次完成）

#### P0-1：修复 `literature_management` 与 `opening_research` 状态串扰

问题：  
`literature_management` 之前产出类型使用 `literature_review`，而 `opening_research` 状态判定也把 `literature_review` 算作开题调研产物，导致文献盘点可能误把开题模块标记为完成。

修复：

1. 新增独立 artifact 类型：`literature_inventory`。  
   - 文件：`backend/src/artifacts/types.py`
2. `thesis.literature_management` 改为落库 `literature_inventory`。  
   - 文件：`backend/src/workspace_features/handlers/thesis.py`
3. `opening_research` dashboard 判定增加 `created_by_skill == "thesis.opening_research"` 过滤。  
   - 文件：`backend/src/services/dashboard_service.py`

结果：  
模块边界恢复隔离，文献盘点不会再误触发开题完成状态。

#### P0-2：修复 `compile_export` 失败也显示 completed 的语义错误

问题：  
此前 dashboard 只要检测到 `thesis.compile_export` 生成的 `paper_draft` 即标记 `completed`，无法区分“编译成功”与“仅有草稿且编译失败”。

修复：

1. `compile_export` 状态判定改为：
   - 有运行任务：`in_progress`
   - 最近编译 `compile_status=success`：`completed`
   - 最近编译失败：`in_progress`（并通过 summary 暴露失败状态）
2. `summary` 增加：
   - `compile_status`
   - `last_compile_success`
3. 前端模块卡片文案同步：
   - 失败场景显示“最近编译失败”。

结果：  
编译模块状态语义与实际执行结果一致，降低“假完成”误导。

---

## 3. 验证结果

本轮已执行并通过以下验证：

1. `PYTHONPATH=. uv run pytest backend/tests/task/test_thesis_handlers.py backend/tests/services/test_dashboard_service.py backend/tests/artifacts/test_types.py -q`  
   - 结果：`13 passed`

2. `PYTHONPATH=. uv run pytest backend/tests/integration/test_task_flow.py backend/tests/gateway/routers/test_features.py backend/tests/thesis/test_api_routes.py backend/tests/gateway/routers/test_dashboard_center.py -q`  
   - 结果：`37 passed`

3. `npx tsc --noEmit`（frontend）  
   - 结果：通过

---

## 4. 已修复项影响评估

### 4.1 正向影响

1. 模块状态更可信：`opening_research` 与 `literature_management` 统计边界清晰。
2. 编译进度可解释：失败不再被误判为已完成。
3. 积分链路更完整：主要执行入口均已纳入扣费与失败退款闭环。

### 4.2 行为变化与兼容性影响

1. `/api/tasks/` 直投可计费 task type 已被阻断。  
   - 依赖该路径的外部调用方需改走 `/workspaces/{id}/features/{feature_id}/execute`。
2. 新增 artifact 类型 `literature_inventory`。  
   - 下游若做了按类型白名单渲染，需要补充该类型映射。
3. `compile_export` 卡片状态更严格。  
   - 对用户可见行为变化：失败后不再显示“已编译”。

---

## 5. 残余问题清单（截至 2026-03-13）

> 按优先级从高到低列出。

### P1（建议优先处理）

1. **计费策略尚未做到单一真源**  
   - 现状：`BILLABLE_TASK_TYPES`（tasks router）与 `WORKFLOW_CREDIT_COSTS`（credit service）分散维护，存在未来漂移风险。

2. **任务入库与队列提交非原子，可能遗留“假 pending”**  
   - 现状：`TaskService.submit_task` 先创建 DB 记录再 `send_task`；若投递失败，当前路径会退款，但可能留下 pending 任务记录。

3. **缺少 execute 幂等保护，存在重复扣费风险**  
   - 现状：快速重复点击 feature execute 可能多次提交并重复扣费。

4. **旧接口 `/api/thesis/generate` 仍保留，长期维护成本高**  
   - 现状：虽然已接入计费，但与 feature execute 双通道并存，策略/语义可能继续分叉。

### P2（建议随后处理）

1. **Dashboard 状态枚举仍无 `failed`**  
   - 目前通过 `in_progress + summary.compile_status=failed` 规避误判，但前后端状态语义仍不够完整。

2. **文献盘点质量指标中 `missing_title_count` 统计偏差**  
   - 由于标题有兜底值，缺失标题统计可能被低估。

3. **计费审计可观测性可继续加强**  
   - 建议统一输出 `workspace_id / feature_id / task_id / tx_id` 的可检索审计字段。

---

## 6. 下一步建议（可执行）

### 6.1 第一优先级（建议下一迭代立即落地）

1. **计费规则中心化**  
   - 目标：以 feature registry + credit policy 生成唯一计费/阻断规则，移除手写散点。
   - 验收：新增 feature 后，无需多处同步修改即可正确计费与阻断绕过。

2. **任务提交一致性治理**  
   - 目标：`send_task` 失败时，任务记录应可回滚或显式标记 `failed(queue_submit_failed)`。
   - 验收：不会再出现由队列投递失败导致的长期 pending 脏数据。

3. **execute 幂等键**  
   - 目标：同一用户在短时间内对同一 workspace/feature/params 重复提交只产生一次扣费。
   - 验收：并发点击与网络重试不产生重复账单。

### 6.2 第二优先级（后续迭代）

1. **统一状态模型升级**  
   - 在 dashboard / frontend module status 引入 `failed`，避免失败态被挤压进 `in_progress`。

2. **旧接口治理计划**  
   - 对 `/api/thesis/generate` 给出阶段性下线路线：兼容期、告警期、切换期。

3. **质量指标修正**  
   - 修复 literature inventory 的缺失字段统计口径（尤其 title/author/year）。

---

## 7. 当前结论

截至 2026-03-13，thesis workspace 与积分系统已从“可走通但存在关键语义误差”提升到“主链路可用且 P0 风险已消除”。  
下一阶段重点应从“补洞”转向“规则收敛与可扩展治理”（计费单一真源、提交一致性、幂等），以支撑后续批量 workspace 并行开发。

