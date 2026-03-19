# Deployment Runbook

更新时间: 2026-03-19

本手册覆盖两条标准链路:

- 本地开发链路: `./start.sh`
- 容器化链路: `docker compose`

## 1. Prerequisites

### 1.1 本地链路 (`./start.sh`) 依赖

- `uv`（或至少 `python3`）
- `node` + `npm`
- `psql`（用于数据库连通性与 pgvector 检查）
- `docker`（可选，但建议；用于 LangGraph 与 DB/Redis 兜底容器）

### 1.2 容器链路 (`docker compose`) 依赖

- Docker Engine
- Docker Compose v2

## 2. Local Runbook (`./start.sh`)

### 2.1 初始化

```bash
cd /home/cjz/AcademiaGPT-V2
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
./start.sh --init
```

`--init` 会执行:

- 依赖检查
- PostgreSQL/pgvector 检查与必要兜底
- Redis 检查与必要兜底
- 后端依赖安装 + migration bootstrap
- 前端依赖安装

### 2.2 启动全链路

```bash
./start.sh
```

默认行为:

1. 启动 Gateway（`http://localhost:8001`）
2. 尝试启动 LangGraph（`http://localhost:2024/info`）
3. 启动 Frontend（`http://localhost:3000`）

### 2.3 常用命令

```bash
./start.sh --status
./start.sh --logs backend
./start.sh --logs langgraph
./start.sh --logs frontend
./start.sh --stop
```

### 2.4 本地兜底容器

当宿主机 PostgreSQL/Redis 不可用时，脚本会自动拉起:

- PostgreSQL(pgvector): `academiagpt-local-postgres` (`55432`)
- Redis: `academiagpt-local-redis` (`56379`)

可通过环境变量覆盖端口:

- `LOCAL_PGVECTOR_PORT`
- `LOCAL_REDIS_PORT`

## 3. Docker Compose Runbook

### 3.1 启动

```bash
cd /home/cjz/AcademiaGPT-V2
cp backend/.env.example backend/.env
docker compose up -d --build
```

### 3.2 编排顺序

`docker-compose.yml` 使用以下依赖链:

1. `postgres` + `redis`
2. `migrate`（一次性执行 `src.database.migration_bootstrap`）
3. `gateway` + `langgraph`
4. `frontend`
5. `nginx`（对外端口 `2026`）

监控组件:

- `prometheus`
- `grafana`（默认 `3001`）

### 3.3 健康检查

```bash
curl -f http://localhost:2026/health
curl -f http://localhost:2026/langgraph/info
docker compose ps
docker compose exec gateway curl -f http://localhost:8001/health
docker compose exec langgraph curl -f http://localhost:2024/info
```

说明:

- `2026` 是 Nginx 对外入口。
- `gateway` 与 `langgraph` 在 compose 默认不直接暴露到宿主机，需要通过 `docker compose exec` 或 Nginx 转发检查。

## 4. Runtime Ports

- `2026`: Nginx 统一入口
- `3001`: Grafana
- `3000`: Frontend（本地 `start.sh`）
- `8001`: Gateway（本地 `start.sh`）
- `2024`: LangGraph（本地 `start.sh`）

## 5. Logs and Diagnostics

### 本地脚本日志

日志目录: `/home/cjz/AcademiaGPT-V2/logs`

- `backend.log`
- `langgraph.log`
- `frontend.log`

### Compose 日志

```bash
docker compose logs -f gateway
docker compose logs -f langgraph
docker compose logs -f migrate
docker compose logs -f nginx
```
