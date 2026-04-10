# Deployment Runbook

更新时间：2026-04-10

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

### 2.2 启动默认链路

```bash
./start.sh
```

默认会启动：

1. Gateway：`http://localhost:8001`
2. Worker：后台长任务执行进程
3. Frontend：`http://localhost:3000`

可选调试：

```bash
./start.sh --langgraph
```

这只用于调试 lead-agent graph，不是主链路依赖。

### 2.3 常用命令

```bash
./start.sh --status
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

### 3.1 启动

```bash
cd "$REPO_ROOT"
cp backend/.env.example backend/.env
cat > .env <<EOF
WENJIN_PROJECT_DIR=$REPO_ROOT
ADMIN_PASSWORD=change-this-admin-password
GRAFANA_PASSWORD=change-this-grafana-password
EOF
docker compose up -d --build
```

### 3.2 编排顺序

`docker-compose.yml` 的主链依赖如下：

1. `postgres` + `redis`
2. `migrate`
3. `gateway` + `worker`
4. `frontend`
5. `nginx`

监控组件：

- `prometheus`
- `grafana`

可选调试 profile：

- `langgraph`：仅用于 graph 调试，不是主链路依赖

### 3.3 健康检查

```bash
curl -f http://localhost:2026/health
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
