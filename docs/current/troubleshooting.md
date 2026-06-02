# Troubleshooting

更新时间：2026-06-02

以下命令默认你已经设置：

```bash
export REPO_ROOT=/path/to/your/wenjin/repo
cd "$REPO_ROOT"
```

## 1. `./start.sh` 启动后功能任务一直 pending

高频原因：

- worker 没有启动
- Redis 不可用
- DataService 不可用，或模型目录没有 enabled default 模型
- `backend/.env` 缺少 `MODEL_SECRET_KEY`

排查：

```bash
./start.sh --status
./start.sh --logs worker
./start.sh --logs backend
```

Compose 场景补充：

- worker 健康检查已改为探测 `http://127.0.0.1:9153/metrics`（容器内），不再依赖 Celery inspect ping。
- 若 `gateway` 因 `depends_on: worker:service_healthy` 未启动，先检查：
  ```bash
  docker compose ps worker gateway
  docker compose logs -f worker
  docker compose exec worker curl -fsS http://127.0.0.1:9153/metrics >/dev/null
  ```

修复：

1. 确认状态页里 `Worker` 为运行中。
2. 检查 `backend/.env` 的 `REDIS_URL`、`DATASERVICE_INTERNAL_TOKEN`、`MODEL_SECRET_KEY` 和数据库连接。
3. 进入管理员后台确认模型管理里至少有一个 enabled default LLM 模型，且该模型绑定了可用 API URL/API Key。
4. 单独重启 worker：`./start.sh --worker`。

## 2. Compose 启动后 API 不可用

快速检查：

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f gateway
docker compose logs -f worker
```

高频问题：

- `migrate` 失败导致主服务不启动
- `backend/.env` 未配置或配置与 compose 网络不匹配
- `gateway` 健康检查未通过

修复建议：

1. 先修复 `migrate` 报错，再重启：`docker compose up -d migrate gateway worker frontend nginx`
2. 确认容器内 DB 地址是 `postgres:5432`，Redis 地址是 `redis:6379`

## 3. 浏览器提示 `Failed to fetch`

常见原因：

- Gateway 未启动或 `/readyz` 不健康
- `NEXT_PUBLIC_API_URL` 配错
- 反向代理没有正确转发 `/api`

排查：

```bash
curl -i http://localhost:8001/readyz
curl -i http://localhost:2026/livez
curl -i http://localhost:2026/readyz
curl -i http://localhost:2026/api/auth/me
```

补充：

- 如果没有创建 `frontend/.env.local`，开发环境默认请求 `http://localhost:8001/api`
- 如果走 Nginx，前端通常通过同源 `/api` 访问

## 4. SSE 不流动或前端长时间无更新

检查项：

1. 代理层是否关闭了 SSE 缓冲
2. Gateway 日志中是否有流式异常
3. Worker 是否正常发布任务进度 / workspace events

排查：

```bash
./start.sh --logs backend
./start.sh --logs worker
docker compose logs -f nginx
```

补充：

- 当前 Nginx 已显式转发 `GET /metrics` 到 gateway；默认可直接使用 `http://localhost:2026/metrics`。
- 如反代配置尚未更新，仍可用 `http://localhost:8001/metrics` 直连网关。

新增（2026-04-15）：

- `runs/stream` 创建后会先下发 `run_queued` 事件，前端应立即看到流式已建立。
- runs 运行链路已收敛为 worker-only：`CELERY_ENABLED=true` 与 `REDIS_ENABLED=true` 任一缺失都会直接返回 503，不再回退 gateway 进程内执行。
- Gateway 启用了事件循环阻塞 watchdog：
  - `GATEWAY_EVENT_LOOP_WATCHDOG_ENABLED`
  - `GATEWAY_EVENT_LOOP_WATCHDOG_INTERVAL_SECONDS`
  - `GATEWAY_EVENT_LOOP_WATCHDOG_LAG_THRESHOLD_SECONDS`
  - `GATEWAY_EVENT_LOOP_WATCHDOG_MAX_BREACHES`
- 当主事件循环连续严重阻塞时，Gateway 会主动退出进程，依赖 `restart: unless-stopped` 自动拉起，实现自愈。
- 可直接用压测脚本复现实例并量化流式链路：
  ```bash
  python scripts/run_pressure.py \
    --base-url http://localhost:2026 \
    --token "$WENJIN_ACCESS_TOKEN" \
    --mode stream \
    --runs 8 \
    --concurrency 4
  ```
  然后对齐同一时间窗的 Grafana `Run Dispatch/s By Result` 与 `Run Wait Duration P95 By Outcome`。

## 5. SMTP 已配置但收不到验证码

按顺序检查：

1. `SMTP_ENABLED=true`
2. `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` 是否可连通
3. backend 日志里是否出现 `发送邮件失败`
4. 是否触发频控或日限额

提示：

- 当 `SMTP_ENABLED=false` 时不会发送真实邮件，只会写日志和 Redis
- 验证码格式固定为 6 位数字

## 6. 功能执行后无结果刷新

检查任务结果中的 `refresh_targets`：

- `artifacts`：前端刷新成果列表
- `references`：前端刷新 Reference Library
- `workspace`：前端刷新 workspace 基础信息

相关代码：

- `frontend/stores/execution-store.ts`
- `frontend/hooks/useWorkspaceEventStream.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `backend/src/services/execution_commit_service.py`

## 7. `migrate` 报错：`value too long for type character varying(32)`

典型日志片段：

```text
UPDATE alembic_version SET version_num='022_rename_chat_credit_types_to_thread' ...
value too long for type character varying(32)
```

原因：

- 历史库里的 `alembic_version.version_num` 仍是 `varchar(32)`，但新 revision id 超过 32。

现状：

- 已在 `backend/alembic/env.py` 接入自动守护，迁移前会确保该列至少为 `varchar(191)`。

手动修复（旧镜像/旧代码场景）：

```sql
ALTER TABLE alembic_version
  ALTER COLUMN version_num TYPE VARCHAR(191);
```

然后重试：

```bash
docker compose up --build migrate
```

## 8. `nginx` 长期 `unhealthy`，日志出现 `gateway could not be resolved`

典型日志片段：

```text
gateway could not be resolved (2: Server failure)
GET /readyz ... 502 Bad Gateway
```

原因：

- `nginx.conf` 若使用变量式 `proxy_pass`（如 `set $gateway_upstream ...; proxy_pass $gateway_upstream/...`），会依赖运行时 DNS 解析；
- 在 Docker DNS 抖动时会周期性解析失败，导致健康检查长期 502。

现状：

- 已改为静态 upstream（`gateway_upstream`/`frontend_upstream`）转发，避免变量式动态解析。

排查与修复：

```bash
docker compose ps
docker compose logs -f nginx
docker exec wenjin-nginx nginx -t
docker compose up -d nginx
```

## 9. Gateway 反复卡住但容器还在运行

现象：

- `/livez` 正常，但 `/api/*` 偶发超时或无流式输出
- 前端出现 502 / 长时间 pending

优先检查：

```bash
docker compose logs -f gateway
curl -i http://localhost:2026/api/models?purpose=chat
curl -i http://localhost:2026/readyz
```

说明：

- Compose 与镜像 healthcheck 已改为探测 `GET /api/models?purpose=chat`（轻量 API 路径），避免仅依赖 `/readyz`。
- `/readyz` 仍用于依赖级健康判断（DB/Redis/Celery/MCP/Execution），并带单依赖超时保护。
- `task_backend` 就绪检查采用双探针：`inspect ping` 优先，失败时自动回退到 `worker:9153/metrics`；当 `inspect` 不可用但 metrics 可达时，`/readyz` 仍判定健康并在报告里给出 `warning`。
- run 元数据已持久化到 Redis，网关重启后 `run_id` 可被重新查询；但重启前处于 `pending/running` 的 run 会被标记为 `interrupted`，需要前端重新发起执行。
- runs 主执行默认在 Celery worker（`src.task.tasks.execute_run`）执行；如出现“run 一直 pending”，优先检查 `wenjin-worker` 日志与 `long_running` 队列消费状态。

### 9.1 Gateway health 一直 `starting`，`/api/models?purpose=chat` 返回 500

高频原因：

- `backend/.env` 或 Docker 环境缺少 `MODEL_SECRET_KEY` / `MODEL_SECRET_KEY_FILE`，DataService 无法解密模型 API Key。
- 管理员后台模型目录里没有 enabled default chat model。

排查：

```bash
curl -i http://localhost:2026/api/models?purpose=chat
docker compose logs -f gateway dataservice
rg -n "MODEL_SECRET_KEY" backend/.env .env
```

修复：

1. 为 `backend/.env` 和 Compose 运行环境配置同一个稳定的 `MODEL_SECRET_KEY`，重启 dataservice / gateway / worker。
2. 进入管理员后台确认至少一个 chat-capable model 处于 enabled + default，且测试配置为 healthy。
3. API Key 不应写入前端环境变量；只通过管理员后台或 DataService seed 写入，DataService 内部加密保存。

### 9.2 Admin dashboard overview 出现 token usage 异常

高频原因：

- dashboard summary 读取 execution token usage 时请求超过 DataService list API 上限。
- 大量历史 execution 需要全量统计，但 gateway facade 只做展示用采样汇总。

当前边界：

- admin overview token summary 只允许按 DataService 上限读取受控样本；不要把 list limit 调到超大值。
- 如果需要全量成本 / token 审计，应新增 DataService aggregate endpoint，再由 admin dashboard 调用。

## 10. Worker 反复重启，日志出现 `cannot unpack non-iterable ExceptionInfo object`

典型日志片段：

```text
Unrecoverable error: TypeError('cannot unpack non-iterable ExceptionInfo object')
...
billiard.exceptions.WorkerLostError: CancelledError()
```

原因：

- run 执行协程内若 `asyncio.CancelledError` 直接冒泡到 Celery，会触发 worker 主循环异常并重启；
- 重启期间会看到 run 流中断、前端无持续流式输出、偶发 502/超时。

现状（2026-04-15 起）：

- run worker 已把 `CancelledError` 收敛为 run `interrupted` 终态，不再向 Celery 主循环继续抛出；
- `pool=solo` 场景会自动将并发参数收敛到 `1` 并打印提示日志，减少调度误判。
- Gateway 对流式断开增加了取消宽限（`RUNTIME_DISCONNECT_CANCEL_GRACE_SECONDS`，默认 1.5 秒），降低“请求尾部断连导致误 cancel”的概率。

排查：

```bash
docker compose logs -f worker
docker compose logs --since=30m worker | rg "WorkerLostError|ExceptionInfo|CancelledError|Unrecoverable error"
```

若仍出现旧签名，执行：

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build gateway worker
```

## 11. `docker compose up --build` 拉取基础镜像失败

典型日志片段：

```text
failed to fetch oauth token: Post "https://auth.docker.io/token": read: connection reset by peer
load metadata for docker.io/library/node:24-alpine
load metadata for docker.io/library/python:3.13-slim
```

原因：

- 你正在走本地构建 override，构建阶段仍需要解析 Node/Python base image；
- 当前网络到 registry 或镜像源的 manifest metadata 请求不稳定，可能出现 token reset、HEAD 401/500 等错误。

修复：

```bash
docker compose up -d
```

默认 `docker-compose.yml` 使用预构建应用镜像，不再触发 frontend/backend base image 解析。确认 `.env` 中至少包含：

```bash
BACKEND_GATEWAY_IMAGE=junze0514/wenjin-backend:latest
LANGGRAPH_IMAGE=junze0514/wenjin-langgraph:latest
FRONTEND_IMAGE=junze0514/wenjin-frontend:latest
TEXLIVE_IMAGE_NAME=junze0514/wenjin-texlive:2024
REDIS_IMAGE=docker.m.daocloud.io/library/redis:8-alpine
NGINX_IMAGE=docker.m.daocloud.io/library/nginx:alpine
POSTGRES_IMAGE=docker.m.daocloud.io/pgvector/pgvector:pg16
GRAFANA_IMAGE=docker.m.daocloud.io/grafana/grafana:latest
PROMETHEUS_IMAGE=docker.m.daocloud.io/prom/prometheus:latest
```

如果确实需要本地构建，使用显式 local-build override，并在失败时先预拉 base image：

```bash
cp .env.docker-cn.example .env
docker pull "$NODE_IMAGE"
docker pull "$PYTHON_IMAGE"
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

## 12. `/readyz` 显示 `execution` 不健康，日志出现 Docker socket 权限错误

典型日志片段：

```text
permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

原因：

- gateway / worker 需要访问宿主机 Docker socket 来调度执行沙箱；
- Docker Desktop 场景下 `/var/run/docker.sock` 常见为 `root:root 660`，容器内用户若不在对应 group 中会被拒绝。

修复：

```bash
DOCKER_GID=0
docker compose up -d gateway worker
curl -fsS http://localhost:2026/readyz
```

Linux 服务器如 Docker socket group 不是 `0`，使用宿主机实际 gid：

```bash
stat -c '%g' /var/run/docker.sock
```

然后写入 `.env`：

```bash
DOCKER_GID=<上一步输出>
```
