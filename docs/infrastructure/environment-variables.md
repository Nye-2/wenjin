# Environment Variables

更新时间: 2026-03-19

配置基线以 `backend/.env.example` 与 `frontend/.env.example` 为准。

## 1. Backend (`backend/.env`)

### 1.1 必填（至少满足可启动）

| 变量 | 说明 | 示例 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async 连接串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/academiagpt` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `change-me-...` |
| `LLM_GEN_MODELS` | 文本生成模型列表(JSON) | `[ {...} ]` |
| `LLM_TOOL_MODELS` | 工具调用模型列表(JSON) | `[ {...} ]` |
| `LLM_UTILITY_MODELS` | 轻量模型列表(JSON) | `[ {...} ]` |

### 1.2 常用可选

| 变量 | 说明 |
|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | 语义学术检索 API key |
| `PROMETHEUS_ENABLED` | 启用 Prometheus 指标 |
| `SENTRY_ENABLED`/`SENTRY_DSN` | 启用 Sentry 错误上报 |
| `ENVIRONMENT`/`DEBUG`/`LOG_LEVEL` | 运行环境与日志等级 |

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

## 2. Frontend (`frontend/.env.local`)

| 变量 | 说明 | 默认 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Gateway API 基路径 | `/api` |
| `NEXT_PUBLIC_LANGGRAPH_BASE_URL` | LangGraph 反向代理路径 | `/langgraph` |
| `NEXT_PUBLIC_BACKEND_BASE_URL` | 兼容变量 | `/api` |

## 3. 配置建议

1. 开发环境先保证 `DATABASE_URL`、`REDIS_URL`、LLM 模型配置可用，再调业务。
2. 生产环境必须替换 `JWT_SECRET_KEY`，不要使用默认值。
3. SMTP 联调时优先验证服务端连通性，再验证前端交互。
