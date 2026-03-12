# AcademiaGPT-V2 性能与基础设施改进建议

## 1. 文档目的

这份文档用于回答 4 个问题：

1. 当前架构除了功能闭环之外，性能上还可以怎么调整
2. 当前 middleware 是否过多
3. 基础设施是否需要增加
4. 后续架构改进应该按什么顺序做

这份文档基于当前代码库的实际状态，不做脱离现状的理想化设计。

## 2. 当前结论

当前系统的主要问题不是 “middleware 太多”，而是：

- 任务执行链路的状态写入过重
- 前端任务状态仍以轮询为主
- Redis / Celery / DB 的依赖关系不够明确
- 启动期仍承担了不该由应用实例承担的数据库 schema 初始化
- 监控、追踪、指标能力配置存在，但未真正接通

因此当前不建议先做：

- 大规模重构主干
- 增加更多应用层 middleware
- 引入 Kafka、微服务拆分等重型基础设施

当前真正值得做的是：

1. 降低任务状态更新链路的数据库压力
2. 把任务状态从轮询改为 SSE 优先
3. 把运行模式和基础设施依赖关系明确化
4. 补真正可用的 observability

## 3. 当前系统的性能风险点

### 3.1 Task Progress 写库过重

当前 `ProgressTracker.update()` 的行为是：

- 更新 Redis runtime state
- 同时更新 Postgres 中的 `task_record`
- 且每次 update 都会自己再开一个 DB session

相关文件：

- `backend/src/task/progress.py`
- `backend/src/task/store.py`

问题本质：

- 高频 progress update 被当成持久化事件处理
- 每个任务执行过程中会产生大量 DB commit
- 并发任务一多，数据库连接和事务开销会先成为瓶颈

当前又存在一个额外问题：

- `mark_task_completed(...)` 与 `progress.complete(...)` 都会落状态

也就是说完成阶段存在重复写。

### 3.2 前端任务状态仍靠轮询

当前前端在 workbench 内对 task status 的处理仍是：

- 每 2 秒调用一次 `/tasks/{task_id}`

相关文件：

- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

而后端其实已经具备：

- `/tasks/{task_id}/stream`

相关文件：

- `backend/src/task/sse.py`
- `backend/src/gateway/routers/tasks.py`

问题本质：

- 当前不是“真实时”，而是“高频轮询模拟实时”
- 活跃任务数一多，请求量会被直接放大
- 多个用户同时操作时，gateway 会承担很多低价值状态查询请求

### 3.3 Redis / Celery 在配置上像可选，在运行时却像强依赖

当前代码状态是：

- app startup 无条件连接 Redis
- task submit 无条件发送 Celery task
- task progress / SSE / status 也默认依赖 Redis

相关文件：

- `backend/src/gateway/app.py`
- `backend/src/task/service.py`
- `backend/src/task/tasks/base.py`
- `backend/src/academic/cache/redis_client.py`

但配置层又存在：

- `RedisSettings.enabled`
- `CelerySettings.enabled`

相关文件：

- `backend/src/config/app_config.py`

这会带来一个工程问题：

- 系统表面看起来支持“可选 Redis / Celery”
- 实际上运行路径默认要求它们可用

这会让部署、调试、故障处理都不清楚。

### 3.4 App 启动时仍在执行数据库 schema 初始化

当前 gateway 启动会调用：

- `init_db()`

而 `init_db()` 会：

- `CREATE EXTENSION`
- `Base.metadata.create_all()`

相关文件：

- `backend/src/gateway/app.py`
- `backend/src/database/session.py`

问题本质：

- 数据库 schema 生命周期和应用实例生命周期耦合
- 多实例启动时会引入额外延迟与潜在竞争
- 正式环境中不利于灰度、回滚和数据库变更审计

### 3.5 刷新策略仍偏粗粒度

当前 feature task 成功后，前端会根据 `refresh_targets` 重新请求：

- artifacts
- papers
- workspace

相关文件：

- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

虽然这已经比“按 featureId 写死刷新逻辑”好很多，但仍然存在一个性能问题：

- 一次 feature 只新增一个 artifact，也会重拉整个 artifacts 列表

而当前 artifact service 本身已经支持：

- `limit`
- `offset`

但 router 没有对外暴露完整分页控制。

相关文件：

- `backend/src/academic/services/artifact_service.py`
- `backend/src/gateway/routers/artifacts.py`

### 3.6 Observability 配置存在，但未真正接通

当前配置层已经有：

- Sentry
- Prometheus

但实际 app 中没有正式接入。

相关文件：

- `backend/src/config/app_config.py`

另外，当前 correlation id middleware 已经存在，但 correlation id 并没有真正进入日志上下文链。

相关文件：

- `backend/src/gateway/middleware/correlation.py`
- `backend/src/logging_config.py`

问题本质：

- 现在出了性能问题，只能靠日志和主观排查
- 缺少请求耗时、任务耗时、队列积压、错误率、Redis/DB 健康等可视指标

## 4. 当前 middleware 是否过多

结论：**不多，也不是当前瓶颈。**

当前真正挂到 app 上的横切层主要只有：

- CORS
- correlation id
- exception handlers

相关文件：

- `backend/src/gateway/app.py`
- `backend/src/gateway/middleware/error_handler.py`

还存在一个 rate limit middleware，但目前：

- 没有真正挂到 app
- 配置读取方式也不够规范

相关文件：

- `backend/src/gateway/middleware/rate_limit.py`

所以判断是：

- 当前问题不是 middleware 太多
- 而是 middleware/横切能力还不够“产品化”

### 4.1 当前建议保留的 middleware / 横切能力

- CORS
- correlation id
- centralized exception handlers

这些都合理，没必要删。

### 4.2 当前不建议继续在 app 内堆更多 middleware

当前不建议优先加更多应用层 middleware，例如：

- 复杂鉴权中间件重构
- 应用内限流层层叠加
- 各种统一包装器再套一层

因为真正的收益不在这里。

### 4.3 Rate Limit 的建议

建议二选一：

1. 如果短期只面向内测或低并发环境，先交给 Nginx / API Gateway / Cloudflare 等边缘层做限流
2. 如果确实要在应用内做限流，就把现有 `rate_limit.py` 正式接好，并统一配置来源

不要继续保留现在这种“代码里有，但实际上未启用且配置不统一”的状态。

## 5. 基础设施是否需要增加

结论：**需要，但应该是轻量、直接解决当前问题的基础设施，而不是大而全。**

### 5.1 现在就值得增加或正式启用的基础设施

#### A. Prometheus + Grafana

用途：

- API 请求量、延迟、错误率
- task 队列积压
- task 成功率、平均耗时、P95/P99
- Redis 延迟与错误率
- DB 连接池与慢查询

这是当前最值得补的基础设施。

#### B. Alembic migration job / release step

用途：

- 把 schema 变更从应用启动里拿出来
- 保证数据库升级路径可控

这是当前最有必要的工程基础设施改进之一。

#### C. 明确独立的 Celery worker 部署单元

当前异步任务已经依赖 Celery，后续应该正式承认它是独立执行层，而不是“隐藏在代码里”的依赖。

至少应明确：

- gateway 实例
- worker 实例
- redis
- postgres

之间的部署边界。

#### D. 健康检查与 readiness / liveness

当前只有简单健康检查。

建议补：

- liveness: 进程是否存活
- readiness: DB / Redis / worker broker 是否可用

这样后续无论是容器部署还是监控报警都更稳定。

### 5.2 后续可视负载再决定是否增加的基础设施

- PgBouncer
- 对象存储（用于 PDF / 导出文件 / 大体积中间产物）
- CDN / edge cache
- 更正式的日志聚合系统

这些都可以后续补，但不应早于前面那几项。

### 5.3 当前不建议引入的基础设施

- Kafka
- 微服务拆分
- Elasticsearch / OpenSearch 全家桶
- 更多 worker 编排层

理由很简单：

- 当前系统瓶颈还没复杂到需要这些
- 先把现有主干收稳，收益更高

## 6. 当前建议的架构改进原则

### 6.1 主干不推翻，只减重

当前系统不应该再做大改架构，而应该：

- 保留现在的 registry / runtime / handler 主线
- 去掉高频重复 IO
- 明确运行模式

### 6.2 高频状态走 Redis，关键状态落 Postgres

建议明确这条原则：

- Redis 用于 runtime state / progress / SSE
- Postgres 用于审计、查询、最终态、必要 checkpoint

不要再把每个 progress 百分比都当成数据库事件处理。

### 6.3 前端从轮询优先切到事件优先

建议把 task 状态获取改成：

1. 优先 SSE
2. SSE 失败时 fallback 到轮询

而不是继续以轮询为主。

### 6.4 配置和依赖关系要说真话

如果系统实际上要求：

- Redis 必需
- Celery 必需

那就明确写清楚，不要配置上继续保持“enabled=false 也好像能跑”的假象。

### 6.5 观测能力优先于更多抽象层

当前最缺的是：

- 看见系统
- 衡量系统
- 定位系统

而不是再新增一层抽象。

## 7. 推荐的改造顺序

下面按优先级分为 `P0 / P1 / P2`。

## 7.1 P0：必须优先做

### P0-1. 重构 task progress 写入策略

目标：

- `progress.update()` 默认只写 Redis
- Postgres 只在关键状态变化时写
- 去掉 completed 阶段重复写

建议动作：

- 重构 `ProgressTracker`
- 重构 `TaskStore.mark_task_completed`
- 统一最终态持久化入口

预期收益：

- 大幅减少 DB commit 次数
- 降低 worker 执行中的 IO 压力

### P0-2. 前端接入 task SSE

目标：

- `ChatPanel` 对 task 状态改为 SSE 优先
- 轮询只做 fallback

建议动作：

- 封装 `streamTaskStatus(taskId, ...)`
- 改造 `ChatPanel.tsx` 中的轮询逻辑

预期收益：

- 显著减少状态查询请求
- 更接近实时体验

### P0-3. 去掉 app startup 中的 `create_all`

目标：

- 应用实例不再负责 schema 初始化
- schema 变更由 migration 流程承担

建议动作：

- `init_db()` 改为连接检查 / 轻量初始化
- schema 变更转到 Alembic 执行链

预期收益：

- 启动行为更稳定
- 多实例部署更合理

### P0-4. 明确运行模式

建议正式定义两种模式：

#### Mode A: dev-single-node

- Postgres 必需
- Redis 建议启用
- 可选本地同步 task executor 或本地 worker

#### Mode B: prod-distributed

- Postgres 必需
- Redis 必需
- Celery worker 必需
- gateway 不承担后台执行

不要继续保持“配置层可选、代码层强依赖”的状态。

## 7.2 P1：应尽快做

### P1-1. 接入 Prometheus metrics

建议至少覆盖：

- request count
- request latency
- request error rate
- task submitted count
- task running count
- task queue backlog
- task duration histogram
- Redis / DB health

### P1-2. 把 correlation id 真正接入日志上下文

当前只生成和回传了 header，但没有形成真正稳定的 trace chain。

建议：

- 给 logger 注入 correlation id
- 在 task / router / service 关键日志中统一输出

### P1-3. Artifact / papers 列表做分页或增量刷新

建议：

- artifacts router 暴露 `limit/offset`
- 前端知识区优先增量更新
- task result 后续可返回新增 artifact 引用，减少全列表重拉

### P1-4. 配置收敛

建议把以下配置做统一梳理：

- Redis
- Celery
- Task
- Rate limit

目标是做到：

- 唯一来源
- 每个配置项都有明确生效路径

## 7.3 P2：中期演进

### P2-1. Readiness / liveness / dependency health

建议加：

- `/health/live`
- `/health/ready`
- `/health/deps`

### P2-2. Worker 侧细化队列策略

等 feature 真正多起来以后，再做：

- queue 分级
- 长任务与短任务分队列
- 优先级策略细化

现在不需要过早设计复杂调度体系。

### P2-3. 对象存储化大文件与导出物

当 PDF、导出文件、截图、编译产物增多时，再把大体积内容迁到对象存储。

## 8. 推荐的实施顺序（给执行者）

如果让 Claude 或其他接手者执行，建议按下面顺序推进：

1. 改 `task progress` 链路，降低 DB 写频率
2. 改 `ChatPanel`，切到 task SSE
3. 把 `init_db/create_all` 从 app startup 中拿掉
4. 梳理 Redis/Celery/task 配置，明确定义运行模式
5. 接入 Prometheus metrics
6. 补 correlation id 到日志上下文
7. 补 artifacts/papers 分页与增量刷新
8. 最后再考虑 queue 细分、PgBouncer、对象存储

## 9. 是否需要继续做“大架构重构”

结论：**不需要。**

当前最合理的策略不是推翻，而是：

- 保留现有 feature registry / runtime / handler 主线
- 保留 task / Redis / Celery 的基本方向
- 对执行链路做减重
- 对基础设施依赖做显式化
- 对监控能力做正式化

换句话说，当前阶段最重要的不是 “换架构”，而是：

- 把现有架构的运行成本降下来
- 把可观测性补起来
- 把运行模式说清楚

## 10. 最后建议

如果只允许做一轮性能与基础设施改进，我建议优先拿下这 4 件事：

1. `progress` Redis-first，去掉高频 DB 写
2. 前端 task SSE 化，减少轮询
3. schema 初始化移出 app startup
4. Prometheus + readiness 正式接入

这 4 件事完成后，系统的：

- 吞吐
- 稳定性
- 部署可控性
- 故障排查效率

都会比现在明显更好。
