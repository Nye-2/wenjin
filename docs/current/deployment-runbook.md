# Deployment Runbook

更新时间：2026-06-13

本手册覆盖两条标准链路：

- 本地开发链路：`./start.sh` + 可选单独命令
- 容器化链路：`docker compose`

## 1. 前置依赖

### 1.1 本地开发

- `uv`（或至少可用的 `python3`）
- `node` + `npm`
- `psql`（用于 PostgreSQL / pgvector 连通性检查）
- `docker`（可选但推荐；用于 DB/Redis/TeXLive 等兜底）

### 1.2 Docker Compose

- Docker Engine
- Docker Compose v2

## 2. 本地开发 Runbook

### 2.1 初始化

```bash
export REPO_ROOT=/path/to/your/wenjin/repo
cd "$REPO_ROOT"
cp backend/.env.example backend/.env
# 只有在需要覆盖前端 API 地址时才创建 frontend/.env.local
# cp frontend/.env.example frontend/.env.local
./start.sh --init
```

`--init` 会执行：

- 依赖检查
- PostgreSQL / pgvector 检查与必要兜底
- Redis 检查与必要兜底
- backend 依赖安装与 migration bootstrap
- frontend 依赖安装

`--init` 不常驻启动 DataService；真实运行时由 `./start.sh` 或 `./start.sh --dataservice` 启动。

### 2.2 启动默认链路

```bash
./start.sh
```

默认会启动：

1. DataService：`http://localhost:8080`
2. bootstrap-admin：幂等创建/升级管理员并 seed 模型目录、skills、agent templates、capabilities
3. Worker：后台长任务执行进程
4. Gateway：`http://localhost:8001`
5. Frontend：`http://localhost:3000`

可选调试：

```bash
./start.sh --langgraph
```

这只用于调试 lead-agent graph，不是主链路依赖。

### 2.3 常用命令

```bash
./start.sh --status
./start.sh --logs dataservice
./start.sh --logs backend
./start.sh --logs worker
./start.sh --logs frontend
./start.sh --stop
```

### 2.4 本地兜底容器

当宿主机 PostgreSQL/Redis 不可用时，脚本会自动拉起：

- PostgreSQL (pgvector)：`wenjin-local-postgres`（默认 `55432`）
- Redis：`wenjin-local-redis`（默认 `56379`）

可通过环境变量覆盖端口：

- `LOCAL_PGVECTOR_PORT`
- `LOCAL_REDIS_PORT`

## 3. Docker Compose Runbook

### 3.1 预构建镜像启动

```bash
cd "$REPO_ROOT"
cp backend/.env.example backend/.env
cat > .env <<EOF
WENJIN_PROJECT_DIR=$REPO_ROOT
BACKEND_GATEWAY_IMAGE=junze0514/wenjin-backend:latest
LANGGRAPH_IMAGE=junze0514/wenjin-langgraph:latest
FRONTEND_IMAGE=junze0514/wenjin-frontend:latest
TEXLIVE_IMAGE_NAME=junze0514/wenjin-texlive:2024
DOCKER_GID=0
ADMIN_PASSWORD=change-this-admin-password
GRAFANA_PASSWORD=change-this-grafana-password
EOF
docker compose up -d
```

默认 `docker-compose.yml` 使用预构建镜像，不执行本地 app build。这样部署启动不再依赖 `node:24-alpine` / `python:3.13-slim` 等 base image 的远端 metadata 请求。

`DOCKER_GID=0` 是 Docker Desktop 默认值，因为 `/var/run/docker.sock` 在容器内通常是 `root:root`。Linux 服务器如 socket 属于 `docker` 组，应改成宿主机 docker 组 id：

```bash
getent group docker | cut -d: -f3
```

### 3.2 本地构建启动

只有需要重建应用镜像时才走本地构建 override：

```bash
cd "$REPO_ROOT"
cp backend/.env.example backend/.env
cp .env.docker-cn.example .env
# 编辑 .env 中的 ADMIN_PASSWORD、GRAFANA_PASSWORD、WENJIN_PROJECT_DIR
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

如镜像源偶发 HEAD/metadata 错误，可先预拉 base image 后重试：

```bash
docker pull "$NODE_IMAGE"
docker pull "$PYTHON_IMAGE"
scripts/docker-retry-build.sh
```

默认预构建镜像：

- `junze0514/wenjin-backend:latest`
- `junze0514/wenjin-frontend:latest`
- `junze0514/wenjin-langgraph:latest`
- `junze0514/wenjin-texlive:2024`

发布新预构建镜像：

```bash
docker login
scripts/docker-build-push-images.sh junze0514 "$(git rev-parse --short HEAD)"
```

### 3.3 编排顺序

`docker-compose.yml` 的主链依赖如下：

1. `postgres` + `redis`
2. `migrate`
3. `dataservice`
4. `bootstrap-admin`
5. `worker`
6. `gateway`
7. `frontend`
8. `nginx`

监控组件：

- `prometheus`
- `grafana`

可选调试 profile：

- `langgraph`：仅用于 graph 调试，不是主链路依赖

### 3.4 健康检查

```bash
curl -f http://localhost:2026/livez
curl -f http://localhost:2026/readyz
docker compose ps
docker compose exec gateway curl -f http://localhost:8001/readyz
docker compose exec frontend wget -qO- http://localhost:3000 >/dev/null
```

如需调试 profile：

```bash
docker compose --profile langgraph up -d langgraph
docker compose exec langgraph curl -f http://localhost:2024/info
```

## 4. Runtime Ports

- `2026`：Nginx 统一入口
- `3001`：Grafana
- `3000`：Frontend（本地）
- `8001`：Gateway（本地）
- `2024`：LangGraph 调试入口（仅可选）

## 5. Logs and Diagnostics

### 本地日志

日志目录：`$REPO_ROOT/logs`

- `backend.log`
- `worker.log`
- `frontend.log`
- `langgraph.log`（仅调试时）

### Compose 日志

```bash
docker compose logs -f gateway
docker compose logs -f worker
docker compose logs -f migrate
docker compose logs -f nginx
```

## 6. Metrics and Dashboard

关键指标入口：

- Gateway: `http://localhost:2026/metrics`（Nginx 入口）
- Gateway (direct): `http://localhost:8001/metrics`
- Worker: `http://localhost:9153/metrics`（容器内）
- Grafana: `http://localhost:3001`

核心 run 链路指标（已纳入 `Wenjin Overview` 面板）：

- `run_dispatch_total{result}`：run 分发结果（`success/conflict/queue_error/...`）
- `run_wait_seconds{outcome}`：wait/join 耗时分布
- `run_wait_polls{outcome}`：wait 轮询次数分布

快速校验：

```bash
curl -s http://localhost:2026/metrics | rg "run_dispatch_total|run_wait_seconds_bucket|run_wait_polls_bucket"
```

## 7. Run 链路压测

仓库内置压测脚本：`scripts/run_pressure.py`（标准库实现，无第三方依赖）。

先决条件：

1. `gateway/worker/redis/postgres` 均健康。
2. 提供鉴权（`--token` 或 `--email + --password`）。

示例（wait 路径）：

```bash
python scripts/run_pressure.py \
  --base-url http://localhost:2026 \
  --email your_user@example.com \
  --password 'your-password' \
  --runs 40 \
  --concurrency 8 \
  --mode wait \
  --output /tmp/wenjin-run-pressure-wait.json
```

示例（stream 路径）：

```bash
python scripts/run_pressure.py \
  --base-url http://localhost:2026 \
  --token "$WENJIN_ACCESS_TOKEN" \
  --runs 20 \
  --concurrency 4 \
  --mode stream \
  --output /tmp/wenjin-run-pressure-stream.json
```

输出包含：

- `success_rate`、`throughput_rps`
- 成功样本延迟分位（`p50/p90/p95/p99`）
- stream 模式 `ttfb_seconds` 分位
- 失败样本与错误分布（便于与 Grafana 时间窗对齐定位）

说明：

- Nginx 已为 `runs/wait` 配置长连接超时（`proxy_read_timeout=86400s`），长时模型调用不会在 60 秒被反代提前截断。
- Worker 默认建议 `CELERY_WORKER_POOL=solo`；当配置并发大于 `1` 时，启动阶段会自动收敛到 `1` 并打印提示日志，避免出现“看似并发、实际单线程”的误判。
