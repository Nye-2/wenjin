# Environment Variables

更新时间: 2026-04-10

配置基线以 `backend/.env.example` 与 `frontend/.env.example` 为准。

约定:

- `backend/.env` 是本地后端运行时配置，需从 `backend/.env.example` 复制生成，默认不提交。
- `frontend/.env.local` 仅在需要覆盖前端 API 地址时才创建，默认不提交。
- 根目录 `.env` 用于 `docker compose` 的镜像源、构建参数等仓库级配置。
  - `WENJIN_PROJECT_DIR`：宿主机仓库绝对路径（用于 Docker-in-Docker 的 LaTeX 编译路径映射）。
  - `ADMIN_PASSWORD`：`bootstrap-admin` 的初始管理员密码，compose 必填。
  - `GRAFANA_PASSWORD`：Grafana 管理员密码，compose 必填。

## 1. Backend (`backend/.env`)

### 1.1 必填（至少满足可启动）

| 变量 | 说明 | 示例 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async 连接串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/wenjin` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `change-me-...` |
| `LLM_GEN_MODELS` | 文本生成模型列表(JSON) | `[ {...} ]` |
| `LLM_TOOL_MODELS` | 工具调用模型列表(JSON) | `[ {...} ]` |
| `LLM_UTILITY_MODELS` | 轻量模型列表(JSON) | `[ {...} ]` |

### 1.2 常用可选

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
| `GUANLAN_DB_AUTO_CREATE` | 仅限临时环境的 metadata 建表开关 |
| `GUANLAN_EXTENSIONS_CONFIG_PATH` | 自定义 `extensions_config.json` 路径 |
| `GUANLAN_TEXLIVE_IMAGE` | 覆盖 LaTeX Docker 镜像 |
| `GUANLAN_TEXLIVE_IMAGE_TAR` | 覆盖本地 TeXLive 镜像 tar 包路径 |
| `TEXLIVE_IMAGE_NAME` | `scripts/ensure_texlive_image.sh` 和 `scripts/package_texlive_image.sh` 的镜像名覆盖（优先级高于 `GUANLAN_TEXLIVE_IMAGE`） |
| `TEXLIVE_IMAGE_TAR` | 上述脚本的 tar 路径覆盖（优先级高于 `GUANLAN_TEXLIVE_IMAGE_TAR`） |
| `TEXLIVE_BASE_IMAGE` | 上述脚本构建 TeXLive 镜像时的 `BASE_IMAGE`（默认 `docker.m.daocloud.io/library/ubuntu:22.04`） |
| `TEXLIVE_APT_MIRROR` | 上述脚本构建 TeXLive 镜像时的 apt 源覆盖（可留空） |
| `WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS` | LaTeX 编译容器超时（秒，默认 300，范围 30-1800） |

### 1.3 SMTP 与验证码

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

## 2. Frontend (`frontend/.env.local`, 可选)

| 变量 | 说明 | 默认 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Gateway API 基路径 | 开发环境默认 `http://localhost:8001/api`，生产默认 `/api` |

## 3. 配置建议

1. 开发环境先保证 `DATABASE_URL`、`REDIS_URL`、LLM 模型配置可用，再调业务。
2. 生产环境必须替换 `JWT_SECRET_KEY`，不要使用默认值。
3. SMTP 联调时优先验证服务端连通性，再验证前端交互。
4. 若部署在反向代理后，确认真实客户端 IP 会正确透传；否则限流会退化为按代理 IP 计数。
5. `docker compose` 部署前必须在仓库根 `.env` 或 shell 环境中显式提供 `ADMIN_PASSWORD` 和 `GRAFANA_PASSWORD`。
