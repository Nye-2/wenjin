# AcademiaGPT-V2 生产架构优化执行总计划（方案 B 终版）

## 1. 文档信息

- 日期：2026-03-16
- 版本：v1.1（Final Handoff）
- 适用范围：`AcademiaGPT-V2`（frontend + backend + task + deployment）
- 目标读者：项目负责人、ClaudeCode 执行工程师、测试与运维
- 决策状态：已锁定方案 B（不换技术栈，做分层纯化 + 生产硬化）
- 文档用途：生产前一次到位的执行蓝图（可直接按 Phase/PR 落地）

---

## 2. 决策锁定（执行期间不可回摆）

1. 不更换技术栈，保持 FastAPI + Celery + PostgreSQL + Redis + Next.js。
2. 不做大爆炸重构，采用增量迁移，保证每个阶段可发布、可回滚。
3. 合同先行：先统一 contract/错误 envelope/权限边界，再迁移逻辑。
4. 安全优先：owner isolation 与鉴权一致性先于功能扩展。
5. 生产优先：每阶段必须有可执行验证命令和门禁。
6. 兼容策略锁定：`/api/thesis/*` 保留一个发布周期并标记 deprecated，期间新能力统一走 feature execute 主路径。

---

## 3. 现状核查与问题清单（已对照代码）

### 3.1 现有可复用基础

1. 主链路雏形已形成：`router -> task -> handler -> service`。
2. `workspace_features` registry/runtime/contracts 已具备扩展基础。
3. 前端多数 feature 页面已接入 execute + task polling。
4. 后端测试基础存在，已覆盖 features/task/router 的关键子集。

### 3.2 必须收敛问题（本规划 P0/P1）

1. API 面重复：`academic` 与 `papers/artifacts` 并存，能力边界漂移风险高。
2. 权限边界不一致：`papers/artifacts/academic` 路由未统一使用 `get_current_user + owner isolation`。
3. Router 过重：`features` 路由承载积分、文献阈值、任务提交与异常补偿编排逻辑。
4. 任务进度高频写库：`ProgressTracker.update()` 每次进度更新都会写 DB，规模化下写放大明显。
5. 任务终态存在重复写路径风险：`mark_task_completed` 与 `progress.complete/fail` 双路径更新。
6. 限流中间件已实现但未挂载到 app。
7. 启动入口不一致：`src.gateway.main:app` 在脚本和 Dockerfile 仍被引用，但实际入口为 `src.gateway.app:app`。
8. 前端 API base 并行命名：`NEXT_PUBLIC_API_URL` 与 `NEXT_PUBLIC_BACKEND_BASE_URL` 并存，部署易错。
9. 模型列表配置双轨：`gateway/routers/models.py` 硬编码列表与 `config/llm_config.py` 动态配置源并存。
10. 生产路径存在 placeholder/stub 可触达风险（task fallback/academic upload TODO）。

---

## 4. 目标架构（To-Be，保持现有栈）

### 4.1 分层职责

1. `gateway/contracts`（新增）
- 统一 API DTO、错误模型、分页与任务状态模型。

2. `gateway/routers`
- 仅负责 HTTP 适配（鉴权入口、参数绑定、调用 handler、返回 contract）。
- 禁止承载业务编排（扣费、阈值、补偿、任务策略）。

3. `application/handlers`（新增）
- 请求级编排层：资格校验、积分扣费、任务提交、失败补偿、异常映射。

4. `workspace_features/*` 与 `services/*`
- 保留业务实现；handler 只 orchestrate，不重写 feature 业务逻辑。

5. `integration/upstream`（新增）
- 对外 HTTP 调用统一治理（超时、重试、错误映射、日志埋点）。

6. `task/*`
- 保留异步主链路，补充幂等、并发控制、进度持久化策略优化。

7. `observability`
- 贯通 correlation id、rate limit、结构化日志与关键指标。

### 4.2 目录增量规划

1. 新增：`backend/src/application/handlers/`
2. 新增：`backend/src/gateway/contracts/`
3. 新增：`backend/src/integration/upstream/`
4. 可选新增：`backend/src/gateway/access_control.py`（集中 owner 校验工具）

---

## 5. 兼容与退役策略（发布策略锁定）

1. `thesis` 兼容面：`/api/thesis/*` 保留一个发布周期（最短 30 天）并返回 deprecation 信号。
2. `academic` 兼容面：进入退役清单，不再新增能力，仅做兼容与安全加固。
3. 新能力入口：统一走 `/api/workspaces/{workspace_id}/features/{feature_id}/execute`。
4. 退役时间下限：`/api/thesis/*` 和高风险 `academic` 写接口最早在 `2026-05-01` 后进入下线窗口（若一个完整发布周期未满则顺延）。
5. 退役前门禁：必须满足“调用量接近 0 + 前端已切换 + 回归全绿 + 回滚包就绪”。

---

## 6. 分阶段实施总览（Phase 0-8）

## Phase 0：架构冻结与执行基线（3 天）

### 目标

1. 冻结目标架构与边界定义。
2. 输出 API 生命周期地图（保留/弃用/下线）。

### 任务

1. 输出 `ADR`：分层边界、禁止项、迁移顺序。
2. 输出 API Surface Map（逐路由标注 owner、鉴权、状态）。
3. 标记 `academic` 与 `thesis` 兼容状态（deprecated）。
4. 建立架构守卫测试（防 router 回流业务编排）。

### 交付与门禁

1. 交付：`docs/architecture/adr-platform-boundaries.md`。
2. 交付：`docs/architecture/api-surface-map.md`。
3. 门禁：守卫测试接入 CI 且通过。

---

## Phase 1：安全与合同统一（1 周，P0）

### 目标

1. 全部 mutating API 统一鉴权与 owner isolation。
2. 统一 401/403/404 行为和错误 envelope。

### 核心任务

1. `papers/artifacts/academic` 路由统一接入 `get_current_user`。
2. 与 workspace 强绑定的读写操作统一 owner 校验。
3. 清理异常返回形态，统一由全局错误处理器输出 envelope。
4. 兼容路由补充 deprecation header 和文档提示。

### 门禁

1. 越权访问回归全绿（401/403/404 覆盖）。
2. 既有主路径回归全绿（features/tasks/auth）。

---

## Phase 2：Router 瘦身与应用编排层落地（1.5 周，P1）

### 目标

1. Router 回归 HTTP 适配层。
2. feature 执行编排迁移至 `application/handlers`。

### 核心任务

1. 新增 `feature_execution_handler` 承载积分、文献阈值、任务提交、补偿。
2. `features` router 只做参数绑定与 response mapping。
3. 统一 deep_research / thesis_generation / workspace_feature 入口策略。

### 门禁

1. 行为一致性测试通过（与旧逻辑一致）。
2. `features` 路由复杂度显著下降（函数职责单一）。

---

## Phase 3：任务系统一致性与可靠性（1.5 周，P0/P1）

### 目标

1. 保障幂等，避免重复扣费与重复排队。
2. 优化进度写入策略，降低 DB 写放大。

### 核心任务

1. 引入 `Idempotency-Key`（提交任务链路）。
2. 落地每用户并发上限与优先级策略。
3. `ProgressTracker` 改造为 Redis 高频 + DB 阶段性/终态写。
4. 清理终态双写路径，统一单路径收敛。

### 门禁

1. 幂等测试通过：同 key 不重复扣费、不重复排队。
2. 并发压测下任务状态一致，DB 写放大可控。

---

## Phase 4：Upstream 统一调用层（1 周，P1）

### 目标

1. 所有外部 HTTP 调用统一治理。
2. 统一超时、重试、错误映射与日志埋点。

### 核心任务

1. 新增 `integration/upstream/service_client.py`。
2. 迁移 `academic/literature/external/*` 到统一客户端模式。
3. 上游异常模型统一化。

### 门禁

1. 不再散落裸 `httpx.AsyncClient` 的重复治理代码。
2. upstream contract tests 全绿。

---

## Phase 5：部署与配置一致性（4 天，P0）

### 目标

1. 启动入口统一。
2. 前端 API base 配置单一来源。

### 核心任务

1. 统一入口为 `src.gateway.app:app`（`start.sh`/Dockerfile/文档）。
2. 收敛前端 API 环境变量命名（单一规范）。
3. 补齐 docker-compose 全链路 smoke test。

### 门禁

1. 一套命令可稳定拉起并访问前后端与任务链路。
2. 部署文档与实际脚本一致。

---

## Phase 6：可观测与风控闭环（1 周，P1）

### 目标

1. 问题可定位、可告警、可追踪。
2. 限流真实生效。

### 核心任务

1. app 挂载 rate limiting middleware。
2. correlation id 贯穿日志上下文。
3. 替换关键生产路径 `print` 为结构化 logging。
4. 输出核心指标（成功率、失败率、队列深度、耗时分位）。

### 门禁

1. 故障演练可触发告警。
2. request/task/workspace 可被日志关联。

---

## Phase 7：前端执行链路收敛（1 周，P1）

### 目标

1. 统一 feature task 执行抽象。
2. 统一 warning/failed/cancelled 状态体验。

### 核心任务

1. 抽象 `useFeatureTaskRunner`（execute + poll + refresh + error handling）。
2. 统一 refresh_targets 刷新策略。
3. 统一 API 调用层风格（避免 fetch/axios 并行漂移）。

### 门禁

1. `npx tsc --noEmit` + `npm run build` 全绿。
2. 所有 feature 页面冒烟通过。

---

## Phase 8：生产闸门与收尾（4 天，P0）

### 目标

1. 关闭高风险兼容路径。
2. 生产仅暴露稳定能力。

### 核心任务

1. 生产关闭 placeholder/stub 路径。
2. `academic` 高风险写路径下线或只读化。
3. 输出最终上线 checklist、回滚包、runbook。

### 门禁

1. 生产配置审计通过。
2. 所有 P0/P1 验收项通过。

---

## 7. 依赖关系与并行策略

1. 强依赖顺序：`Phase 0 -> 1 -> 2 -> 3 -> 5 -> 8`。
2. 并行窗口：`Phase 4` 可在 `Phase 2` 后并行推进；`Phase 6` 与 `Phase 7` 可并行。
3. 上线前最小闭环：`Phase 1 + 3 + 5 + 8` 必须完成。

---

## 8. Phase 1 执行级任务分解（文件级，ClaudeCode 可直接开工）

## 8.1 文件清单（Phase 1）

### Create

1. `backend/src/gateway/access_control.py`（统一 owner isolation helper）
2. `backend/src/gateway/contracts/error.py`（统一错误 contract，可先轻量）
3. `backend/tests/gateway/routers/test_access_control_matrix.py`（新增权限矩阵测试）

### Modify

1. `backend/src/gateway/routers/papers.py`
2. `backend/src/gateway/routers/artifacts.py`
3. `backend/src/gateway/routers/academic.py`
4. `backend/src/gateway/middleware/error_handler.py`
5. `backend/src/gateway/app.py`（兼容路由 deprecation 标注点，如需要）

### Test Modify

1. `backend/tests/gateway/routers/test_papers.py`
2. `backend/tests/gateway/routers/test_artifacts.py`
3. `backend/tests/gateway/middleware/test_error_handler.py`

## 8.2 任务分解（TDD 顺序）

### Task P1-1：固化权限矩阵与错误矩阵

- [ ] 编写权限矩阵文档（路由 -> 认证要求 -> owner 策略 -> 预期错误码）。
- [ ] 先写失败测试：匿名访问、跨用户访问、无资源访问。
- [ ] 运行测试确认失败（预期 401/403/404 不一致）。
- [ ] 更新 router 依赖与 owner 校验 helper。
- [ ] 再跑测试确认通过。

### Task P1-2：统一错误 envelope

- [ ] 编写失败测试：同类错误在不同 router 返回 shape 不一致。
- [ ] 调整异常抛出点，统一走全局 handler 输出：
  - `{"error": {"code": "...", "message": "..."}}`
- [ ] 更新历史测试断言。

### Task P1-3：兼容路由退役信号

- [ ] 为 `academic` 和 `thesis` 兼容路径增加 deprecation 标识（响应头或文档）。
- [ ] 增加兼容测试，确保兼容仍可用但可识别为 deprecated。

## 8.3 Phase 1 验证命令

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/gateway/routers/test_papers.py -v
PYTHONPATH=. uv run pytest tests/gateway/routers/test_artifacts.py -v
PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -v
PYTHONPATH=. uv run pytest tests/gateway/middleware/test_error_handler.py -v
PYTHONPATH=. uv run pytest tests/gateway/routers/test_access_control_matrix.py -v
PYTHONPATH=. uv run ruff check src tests
PYTHONPATH=. uv run mypy src
```

## 8.4 Phase 1 DoD

1. 所有 mutating API 已统一鉴权。
2. workspace 相关数据不可跨 owner 访问。
3. 401/403/404 行为一致且错误 contract 一致。
4. 兼容路径已可识别 deprecated。

---

## 9. Phase 2 执行级任务分解（文件级，ClaudeCode 可直接开工）

## 9.1 文件清单（Phase 2）

### Create

1. `backend/src/application/handlers/feature_execution_handler.py`
2. `backend/src/application/handlers/__init__.py`
3. `backend/tests/application/handlers/test_feature_execution_handler.py`

### Modify

1. `backend/src/gateway/routers/features.py`
2. `backend/src/gateway/routers/tasks.py`（如需注入幂等/并发上下文）
3. `backend/src/thesis/api.py`（仅在需要统一入口策略时做适配，不强制）

### Test Modify

1. `backend/tests/gateway/routers/test_features.py`
2. `backend/tests/task/test_workspace_feature_handler.py`

## 9.2 任务分解（TDD 顺序）

### Task P2-1：抽离 feature 编排 handler

- [ ] 写失败测试：`feature_execution_handler` 输入输出 contract。
- [ ] 最小实现 handler：
  - 校验 workspace owner
  - 处理文献阈值（thesis_writing）
  - 执行积分扣费与失败补偿
  - 提交 task 并返回统一响应
- [ ] 测试通过后再接入 router。

### Task P2-2：router 瘦身

- [ ] 写失败测试：router 仅做参数绑定，不直接编排扣费/阈值/补偿。
- [ ] 修改 `features.py`：
  - endpoint 中仅保留 request parsing + handler call + response mapping
  - 移除业务编排细节
- [ ] 跑回归测试确认行为不变。

### Task P2-3：统一执行入口策略

- [ ] 补齐 `deep_research/thesis_generation/workspace_feature` 一致性测试。
- [ ] 保证兼容路由仍可用，并明确新入口优先。

## 9.3 Phase 2 验证命令

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/application/handlers/test_feature_execution_handler.py -v
PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -v
PYTHONPATH=. uv run pytest tests/task/test_workspace_feature_handler.py -v
PYTHONPATH=. uv run pytest tests/task/test_service.py tests/task/test_store.py -v
PYTHONPATH=. uv run ruff check src tests
PYTHONPATH=. uv run mypy src
```

## 9.4 Phase 2 DoD

1. `features` router 不再直接包含业务编排代码。
2. handler 单测与 router contract 测试全绿。
3. 行为与旧逻辑保持兼容（含 warning/insufficient credits/queue fail refund）。

---

## 10. 全局测试与质量门禁（所有 Phase 通用）

## 10.1 静态质量

1. Backend：`PYTHONPATH=. uv run ruff check src tests`
2. Backend：`PYTHONPATH=. uv run mypy src`
3. Frontend：`npx tsc --noEmit`
4. Frontend：`npm run build`

## 10.2 自动化测试矩阵

1. Router：鉴权/越权/错误映射/兼容路由 contract。
2. Task：幂等、并发、重试、取消、失败补偿。
3. Feature：handler 输出 contract、artifact 落地。
4. Integration：workspace 全流程 + task 全流程。

## 10.3 可靠性验证

1. 幂等压测：同一 `Idempotency-Key` 不重复扣费与排队。
2. Redis/DB 波动演练：任务状态保持一致。
3. 上游超时/限流故障注入：错误映射和重试符合预期。

---

## 11. 部署一致性与发布门禁

## 11.1 启动与配置统一（必须完成）

1. 修正脚本与 Dockerfile 入口：统一到 `src.gateway.app:app`。
2. 收敛前端 API 环境变量单一规范（推荐保留 `NEXT_PUBLIC_BACKEND_BASE_URL`）。
3. 更新 README 与 deployment 文档，删除过时入口示例。

## 11.2 smoke test 命令

```bash
cd /home/cjz/AcademiaGPT-V2
docker compose up -d --build
curl -f http://localhost:2026/health
curl -f http://localhost:2026/api/health
```

---

## 12. PR 切分与执行节奏（建议 10 PR）

1. PR-1：Phase 0 文档与架构守卫测试。
2. PR-2：Phase 1 权限与错误合同统一（papers/artifacts/academic）。
3. PR-3：Phase 2 application handler 落地。
4. PR-4：Phase 3 幂等与并发治理。
5. PR-5：Phase 3 进度写入策略优化与终态一致性。
6. PR-6：Phase 4 upstream 统一 client。
7. PR-7：Phase 5 启动入口与配置一致化。
8. PR-8：Phase 6 可观测性 + 限流接入。
9. PR-9：Phase 7 前端 task runner 抽象迁移。
10. PR-10：Phase 8 收尾与生产闸门。

### 合并规则

1. P0 PR 必须在所有门禁全绿后合并。
2. 不允许跨 Phase 混改。
3. 每个 PR 必须附：变更范围、影响评估、验证证据、回滚方案。

---

## 13. 回滚与风险控制

## 13.1 回滚策略

1. 代码回滚：镜像版本化，支持按 PR 粒度回退。
2. 配置回滚：新路径/中间件/幂等/placeholder 通过开关可降级。
3. 数据回滚：迁移采用可回退策略，禁止不可逆一次性操作。

## 13.2 推荐开关（落地时实现）

1. `ENABLE_RATE_LIMIT_MIDDLEWARE`
2. `ENABLE_FEATURE_HANDLER_V2`
3. `ENABLE_TASK_IDEMPOTENCY`
4. `ENABLE_ACADEMIC_WRITE_ROUTES`

## 13.3 高风险项与缓解

1. 路由收敛引发前端兼容风险
- 缓解：compat layer + contract snapshot + 灰度切换。

2. 并发治理影响吞吐
- 缓解：先压测后调参，分层限流。

3. upstream 统一后行为变化
- 缓解：迁移前后对照测试，逐源切换。

4. 观测接入增加日志噪音
- 缓解：日志分级 + 采样 + 告警分级。

---

## 14. ClaudeCode 交接执行模板（可复制到每个 PR 描述）

## 14.1 PR 基础信息

1. 目标 Phase：
2. 目标任务：
3. 影响范围：
4. 风险级别（P0/P1/P2）：

## 14.2 变更清单

1. Create：
2. Modify：
3. Delete：
4. 数据迁移：有/无

## 14.3 验证证据

1. 静态检查命令与结果。
2. 单测/集成测试命令与结果。
3. 手工冒烟步骤与结果。

## 14.4 回滚说明

1. 回滚触发条件。
2. 回滚命令或配置。
3. 回滚后验证步骤。

## 14.5 发布检查

1. 是否新增/修改兼容策略。
2. 是否新增/修改开关。
3. 是否更新文档。

---

## 15. 最终验收定义（Definition of Done）

满足以下全部条件，判定“可生产交付”：

1. 所有 mutating API 统一鉴权 + owner isolation。
2. Router 层不再承载业务编排。
3. Feature 执行具备幂等保证，重复请求不重复扣费。
4. 任务状态一致性通过并发与故障注入测试。
5. 启动入口、脚本、文档一致，`docker compose` 全链路可用。
6. 限流、trace、日志、指标可用并可告警。
7. 生产不可触达 placeholder/stub 路径。
8. 前端 feature 页面统一任务执行抽象并通过回归。

---

## 16. 文档终审结论（本轮已完成）

本次对文档进行了完整 review，并确认以下事项无冲突后锁版：

1. 路径一致性：文档中的关键目录与仓库现状匹配。
2. 阶段依赖：顺序与并行关系明确，未出现循环依赖。
3. 门禁可执行性：均给出具体命令，且命令与项目工具链一致。
4. 兼容策略：`/api/thesis/*` 与 `academic` 退役策略明确且可操作。
5. 交接完整度：包含 Phase 级目标、文件级拆解、测试门禁、PR 模板、回滚策略。

结论：该文档可作为 ClaudeCode 的直接执行蓝图投入实施。
