# Environment Variables

更新时间: 2026-06-25

配置基线以仓库根目录 `.env.example` 为准。

约定:

- 根目录 `.env` 是本地和 Compose 的唯一环境配置入口，需从 `.env.example` 复制生成，默认不提交。
- Backend、Frontend、LangGraph 和 Docker Compose 都从根目录 `.env` 读取配置；不再维护 `backend/.env` 或 `frontend/.env.local`。
- `deploy/env/compose.prebuilt.example` 与 `deploy/env/compose.local-build-cn.example` 只保留作镜像源/构建变量参考，需要时把其中变量合并到根目录 `.env`。
  - `WENJIN_PROJECT_DIR`：宿主机仓库绝对路径（用于 Docker-in-Docker 的 LaTeX 编译路径映射）。
  - `ADMIN_PASSWORD`：`bootstrap-admin` 的初始管理员密码，compose 必填。
  - `DATASERVICE_INTERNAL_TOKEN`：Gateway/worker/DataService 内部调用令牌，compose 必填。
  - `GRAFANA_PASSWORD`：Grafana 管理员密码，compose 必填。
  - `DOCKER_GID`：容器访问宿主机 `/var/run/docker.sock` 的 group id；Docker Desktop 通常为 `0`，Linux 服务器按宿主机 docker 组设置。
  - `PYTHON_IMAGE` / `NODE_IMAGE`：本地构建 backend/frontend 时的 base image；网络不稳定环境建议使用 `deploy/env/compose.local-build-cn.example` 中的镜像源。
  - `BACKEND_GATEWAY_IMAGE` / `FRONTEND_IMAGE` / `LANGGRAPH_IMAGE`：预构建部署时使用的应用镜像。

## 1. Root `.env`

### 1.1 必填（至少满足可启动）

| 变量 | 说明 | 示例 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async 连接串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/wenjin` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `change-me-...` |
| `DATASERVICE_INTERNAL_TOKEN` | Gateway/worker/DataService 内部调用令牌 | `change-me-...` |
| `MODEL_SECRET_KEY` 或 `MODEL_SECRET_KEY_FILE` | DataService 模型 API Key 加密主密钥 | `base64:...` |

### 1.2 模型目录与计费配置

- 模型目录、模型 API Key、默认模型、默认 headers、模型用量定价策略由 DataService 持久化，并通过管理员后台维护。
- `MODEL_SECRET_KEY` 用于加密 `model_catalog_entries.encrypted_api_key`，生产必须是强随机 32-byte key。推荐格式为 `base64:<urlsafe-base64-32-byte>`；也可以用 `MODEL_SECRET_KEY_FILE` 挂载密钥文件。
- `LLM_MODELS` / `LLM_IMAGE_MODELS` 现在只作为首次 seed/bootstrap 输入和测试夹具，不是生产运行时模型发现事实源。
- 首次 bootstrap 会先创建默认 pricing policies；env model seed 如果没有显式 `pricing_policy_id`，会写入 `default-model-usage`，使模型目录落库后仍满足 enabled model 必须绑定 enabled `model_usage` policy 的写入约束。
- `LLM_DEFAULT_MODEL` 只影响 env seed/test helper 的默认项；生产运行时默认模型来自 DataService 中 `is_default=true` 的 enabled model。
- Gateway 启动时会 best-effort 预热本进程模型缓存；worker 启动和每次 chat/execution 任务开始前会从 DataService 刷新 runtime model cache，管理员后台修改会影响后续任务。runtime cache 必须携带模型绑定的 `pricing_policy_id`，用于不同模型的积分换算。

### 1.3 常用可选

| 变量 | 说明 |
|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | 语义学术检索 API key |
| `LAYOUT_PARSING_ENABLED`/`LAYOUT_PARSING_API_URL`/`LAYOUT_PARSING_TOKEN` | 上传文件预处理中间件（PDF/图片）开关与凭证 |
| `LAYOUT_PARSING_TIMEOUT_SECONDS` | 预处理 API 请求超时（秒） |
| `LAYOUT_PARSING_USE_DOC_ORIENTATION_CLASSIFY` | 是否启用文档方向分类 |
| `LAYOUT_PARSING_USE_DOC_UNWARPING` | 是否启用文档去扭曲 |
| `LAYOUT_PARSING_USE_CHART_RECOGNITION` | 是否启用图表识别 |
| `PROMETHEUS_ENABLED` | 启用 Prometheus 指标 |
| `PROMETHEUS_WORKER_PORT` | Celery worker Prometheus 指标端口（compose 默认 `9153`；若修改需同步更新 `monitoring/prometheus.yml`） |
| `PROMETHEUS_MULTIPROC_DIR` | Celery worker Prometheus 多进程指标目录 |
| `SENTRY_ENABLED`/`SENTRY_DSN` | 启用 Sentry 错误上报 |
| `ENVIRONMENT`/`DEBUG`/`LOG_LEVEL` | 运行环境与日志等级 |
| `REDIS_RATE_LIMIT_REQUESTS`/`REDIS_RATE_LIMIT_WINDOW` | API 限流窗口，当前默认 `120` 次 / `60` 秒 |
| `REDIS_STREAM_SOCKET_TIMEOUT_SECONDS` | Redis stream/pubsub 读超时（秒），默认 `30`，应大于 SSE block 间隔 |
| `CELERY_WORKER_POOL` | Celery worker 池类型，建议 `solo`（避免 asyncio + prefork loop 绑定问题；`solo` 模式下运行时会自动把并发收敛为 `1`） |
| `RUNTIME_DISCONNECT_CANCEL_GRACE_SECONDS` | SSE 断开后取消 run 前的宽限时间（秒，默认 `1.5`），用于降低临界断连导致的误中断 |
| `GUANLAN_DB_AUTO_CREATE` | 仅限临时环境的 metadata 建表开关 |
| `GUANLAN_EXTENSIONS_CONFIG_PATH` | 自定义 `extensions_config.json` 路径 |
| `GUANLAN_TEXLIVE_IMAGE` | 覆盖 LaTeX Docker 镜像 |
| `GUANLAN_TEXLIVE_IMAGE_TAR` | 覆盖本地 TeXLive 镜像 tar 包路径 |
| `TEXLIVE_IMAGE_NAME` | `scripts/ensure_texlive_image.sh` 和 `scripts/package_texlive_image.sh` 的镜像名覆盖（优先级高于 `GUANLAN_TEXLIVE_IMAGE`） |
| `TEXLIVE_IMAGE_TAR` | 上述脚本的 tar 路径覆盖（优先级高于 `GUANLAN_TEXLIVE_IMAGE_TAR`） |
| `TEXLIVE_BASE_IMAGE` | 上述脚本构建 TeXLive 镜像时的 `BASE_IMAGE`（默认 `ubuntu:22.04`） |
| `TEXLIVE_APT_MIRROR` | 上述脚本构建 TeXLive 镜像时的 apt 源覆盖（可留空） |
| `WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS` | LaTeX 编译容器超时（秒，默认 300，范围 30-1800） |

### 1.4 SMTP 与验证码

| 变量 | 说明 | 建议 |
|---|---|---|
| `SMTP_ENABLED` | 是否启用真实 SMTP | 生产设为 `true` |
| `SMTP_HOST`/`SMTP_PORT` | SMTP 地址与端口 | 使用服务商提供值 |
| `SMTP_USERNAME`/`SMTP_PASSWORD` | 发件账号和授权码 | 使用授权码而不是登录密码 |
| `SMTP_USE_TLS` | 是否 TLS | 按服务商要求 |
| `SMTP_CODE_LENGTH` | 验证码长度 | 当前逻辑固定 6 位数字 |
| `SMTP_CODE_TTL` | 验证码有效期（秒） | 默认 600 |
| `SMTP_SEND_INTERVAL` | 重发间隔（秒） | 默认 60 |
| `SMTP_DAILY_LIMIT` | 日发送上限 | 默认 10 |

注意:

- 当 `SMTP_ENABLED=false` 时，系统进入开发模式，验证码不会真实发邮件，只会写入日志与 Redis。
- 验证码格式为 **6 位纯数字**。

## 2. Frontend variables

| 变量 | 说明 | 默认 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Gateway API 基路径 | 默认 `/api`；生产走 nginx 同源入口，前端开发态由 Next rewrite 代理 |
| `WENJIN_DEV_API_PROXY_TARGET` | 前端开发态 `/api/*` 代理目标 | 默认 `http://localhost:8001`；需要通过本机 Docker/Nginx 入口调试时可设为 `http://localhost:2026` |

前端开发命令会显式加载仓库根目录 `.env`，不需要也不应再创建 `frontend/.env.local`。

## 3. Docker Compose image variables

| 变量 | 说明 | 示例 |
|---|---|---|
| `PYTHON_IMAGE` | backend Dockerfile base image | `docker.m.daocloud.io/library/python:3.13-slim` |
| `NODE_IMAGE` | frontend Dockerfile base image | `docker.m.daocloud.io/library/node:24-alpine` |
| `PIP_INDEX_URL` | Python package index | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| `APT_MIRROR` | Debian package mirror for backend image | `https://mirrors.tuna.tsinghua.edu.cn/debian` |
| `APT_SECURITY_MIRROR` | Debian security package mirror for backend image | `https://mirrors.tuna.tsinghua.edu.cn/debian-security` |
| `NPM_REGISTRY` | npm primary registry | `https://registry.npmmirror.com` |
| `NPM_FALLBACK_REGISTRY` | npm fallback registry | `https://registry.npmjs.org` |
| `ALPINE_MIRROR` | Alpine package mirror for frontend image | `https://mirrors.tuna.tsinghua.edu.cn/alpine` |
| `BACKEND_GATEWAY_IMAGE` | prebuilt gateway/worker/migrate image | `junze0514/wenjin-backend:latest` |
| `FRONTEND_IMAGE` | prebuilt frontend image | `junze0514/wenjin-frontend:latest` |
| `LANGGRAPH_IMAGE` | prebuilt optional LangGraph image | `junze0514/wenjin-langgraph:latest` |
| `TEXLIVE_IMAGE_NAME` | prebuilt TeXLive image | `junze0514/wenjin-texlive:2024` |
| `DOCKER_GID` | group id used by gateway/worker/langgraph to access mounted Docker socket | `0` on Docker Desktop; Linux use `getent group docker | cut -d: -f3` |

## 4. 配置建议

1. 开发环境先保证 `DATABASE_URL`、`REDIS_URL`、`DATASERVICE_INTERNAL_TOKEN`、`MODEL_SECRET_KEY` 和至少一个 enabled default 模型可用，再调业务。
2. 生产环境必须替换 `JWT_SECRET_KEY`，不要使用默认值。
3. SMTP 联调时优先验证服务端连通性，再验证前端交互。
4. 若部署在反向代理后，确认真实客户端 IP 会正确透传；否则限流会退化为按代理 IP 计数。
5. `docker compose` 部署前必须在仓库根 `.env` 或 shell 环境中显式提供 `ADMIN_PASSWORD`、`GRAFANA_PASSWORD` 和 `DATASERVICE_INTERNAL_TOKEN`。
6. 管理员后台不会返回明文 API Key 或敏感 header；编辑模型时 API Key 留空表示保持原密钥不变，填写新值才会替换。
