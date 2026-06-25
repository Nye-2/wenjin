# Deployment Runbook

更新时间：2026-06-25

本手册只覆盖 Docker Compose 标准链路。旧的本地一键守护脚本、根目录隐藏 env 模板和分散 compose 片段已移除，避免项目存在多套启动事实源。

## 1. 前置依赖

- Docker Engine
- Docker Compose v2
- 可访问宿主机 `/var/run/docker.sock`，用于 workspace sandbox 与 LaTeX 编译容器

## 2. 配置文件

本地运行只需要一个不提交的环境文件：

- 根目录 `.env`：后端运行时、前端开发态、模型 seed、Compose 镜像、部署密码、Docker socket group、项目绝对路径等全部配置，从根目录 `.env.example` 复制。

```bash
cd "$REPO_ROOT"
cp .env.example .env
```

部署前至少修改根目录 `.env`：

- `WENJIN_PROJECT_DIR`：宿主机仓库绝对路径，例如 `/Users/ze/wenjin`
- `ADMIN_PASSWORD`：初始管理员密码
- `GRAFANA_PASSWORD`：Grafana 管理员密码
- `DATASERVICE_INTERNAL_TOKEN`：Gateway/worker/DataService 内部调用令牌
- `JWT_SECRET_KEY`：Gateway JWT 签名密钥
- `MODEL_SECRET_KEY` 或 `MODEL_SECRET_KEY_FILE`：DataService 模型 API Key 加密主密钥
- `DOCKER_GID`：容器访问 Docker socket 的 group id；Docker Desktop 通常为 `0`，Linux 服务器使用 `getent group docker | cut -d: -f3`

生产部署还必须检查 SMTP、外部模型 seed、镜像源等配置。模型 API Key 推荐通过管理员后台写入 DataService；如果通过 `.env` seed/bootstrap 写入，也必须保证 `.env` 不提交到 Git。

## 3. 标准启动

默认 `docker-compose.yml` 使用预构建镜像，不执行本地 app build：

```bash
docker compose up -d
```

默认入口：

- Nginx: `http://localhost:2026`
- Frontend container: `http://localhost:3000`
- Grafana: `http://localhost:3001`

## 4. 本地构建

只有需要重建 backend/frontend/langgraph 镜像时才使用 local-build override：

```bash
cp deploy/env/compose.local-build-cn.example .env
# 编辑 .env 中的 WENJIN_PROJECT_DIR、ADMIN_PASSWORD、GRAFANA_PASSWORD、
# DATASERVICE_INTERNAL_TOKEN、DOCKER_GID 等部署值。
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
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

TeXLive 镜像维护脚本只用于镜像构建/打包，不是项目启动入口：

```bash
scripts/package_texlive_image.sh
scripts/push-texlive.sh junze0514
```

## 5. 编排顺序

`docker-compose.yml` 的主链依赖如下：

1. `postgres` + `redis`
2. `migrate`
3. `dataservice`
4. `bootstrap-admin`
5. `worker` + `memory-worker`
6. `gateway`
7. `frontend`
8. `nginx`

监控组件：

- `prometheus`
- `grafana`

可选调试 profile：

- `langgraph`：仅用于 graph 调试，不是主链路依赖

```bash
docker compose --profile langgraph up -d langgraph
docker compose exec langgraph curl -f http://localhost:2024/info
```

## 6. 健康检查

```bash
docker compose ps
curl -f http://localhost:2026/livez
curl -f http://localhost:2026/readyz
docker compose exec gateway curl -f http://localhost:8001/readyz
docker compose exec frontend wget -qO- http://localhost:3000 >/dev/null
```

如果 gateway 长期 unhealthy，优先看模型目录和 DataService：

```bash
curl -i http://localhost:2026/api/models?purpose=chat
docker compose logs -f gateway dataservice
```

## 7. 常用运维命令

```bash
docker compose logs -f gateway
docker compose logs -f worker
docker compose logs -f dataservice
docker compose logs -f migrate
docker compose logs -f nginx
docker compose restart gateway worker dataservice
docker compose down
```

升级到新镜像：

```bash
docker compose pull
docker compose up -d
docker compose ps
```

重建本地镜像：

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build gateway worker dataservice frontend
```

## 8. Runtime Ports

- `2026`：Nginx 统一入口
- `3001`：Grafana
- `3000`：Frontend container
- `8001`：Gateway container
- `8080`：DataService container
- `2024`：LangGraph 调试入口，仅 profile 启用

## 9. Metrics and Dashboard

关键指标入口：

- Gateway: `http://localhost:2026/metrics`（Nginx 入口）
- Gateway direct: `http://localhost:8001/metrics`
- Worker: `http://localhost:9153/metrics`（容器内）
- Grafana: `http://localhost:3001`

核心 run 链路指标：

- `run_dispatch_total{result}`：run 分发结果
- `run_wait_seconds{outcome}`：wait/join 耗时分布
- `run_wait_polls{outcome}`：wait 轮询次数分布

快速校验：

```bash
curl -s http://localhost:2026/metrics | rg "run_dispatch_total|run_wait_seconds_bucket|run_wait_polls_bucket"
```

## 10. Run 链路压测

仓库内置压测脚本：`scripts/run_pressure.py`。

先决条件：

1. `gateway`、`worker`、`redis`、`postgres` 均健康。
2. 提供鉴权（`--token` 或 `--email + --password`）。

示例：

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
