# Code Review 报告 - AcademiaGPT-V2

**日期**: 2026-03-10  
**审查范围**: Backend + Frontend  
**审查目标**: Bug 检测、优化建议、代码规范

---

## 🔴 严重问题 (Critical)

### 1. 安全问题: CORS 配置过于宽松
**文件**: `backend/src/gateway/app.py:45-51`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 危险: 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**问题**: `allow_origins=["*"]` 配合 `allow_credentials=True` 在生产环境中是严重的安全风险。应配置具体的域名白名单。

**修复建议**:
```python
allow_origins=settings.cors_origins,  # 从配置读取白名单
```

---

### 2. 安全问题: JWT Secret Key 默认值
**文件**: `backend/src/config/app_config.py:13-16`
```python
secret_key: str = Field(
    default="change-me-in-production",
    ...
)
```
**问题**: 默认 JWT secret key 是硬编码值，如果生产环境未正确配置，攻击者可伪造任意令牌。

**修复建议**:
- 移除默认值，强制要求配置
- 启动时检查是否使用了默认值并发出警告

---

### 3. Bug: Sandbox 执行器 os 模块错误
**文件**: `backend/src/sandbox/executor.py:250`
```python
def _create_safe_os_module(self) -> Any:
    """Create a restricted version of the os module."""
    class SafeOS:
        environ = os.environ  # 允许读取环境变量
        path = os  # ❌ Bug: 应该是 os.path
```
**问题**: `path = os` 写错了，应该是 `path = os.path`，导致暴露更多 os 模块功能。

**修复建议**:
```python
path = os.path  # 修正
```

---

### 4. 并发问题: threading.Lock 与 asyncio 混用
**文件**: `backend/src/subagents/executor.py:36-46`
```python
# Global thread pools
_scheduler_pool = ThreadPoolExecutor(max_workers=3, ...)
_execution_pool = ThreadPoolExecutor(max_workers=3, ...)

# Background task tracking
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()  # 与 asyncio 混用
```
**问题**: 使用 `threading.Lock()` 与 `asyncio` 混合使用可能导致死锁。当线程池执行器中的任务尝试与 asyncio 事件循环交互时可能出现问题。

**修复建议**:
```python
_background_tasks_lock = asyncio.Lock()  # 使用 asyncio.Lock
```

---

### 5. 资源泄漏: Redis 锁逻辑错误
**文件**: `backend/src/academic/cache/redis_client.py:106-117`
```python
@asynccontextmanager
async def workspace_lock(self, workspace_id: str, timeout: int = None):
    key = self._workspace_lock_key(workspace_id)
    acquired = await self.client.set(key, "locked", nx=True, ex=timeout)
    try:
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for workspace {workspace_id}")
        yield
    finally:
        await self.client.delete(key)  # ❌ 即使获取锁失败也会删除
```
**问题**: 如果获取锁失败，`finally` 块仍会尝试删除不存在的锁，可能导致误删其他进程的锁。

**修复建议**:
```python
@asynccontextmanager
async def workspace_lock(self, workspace_id: str, timeout: int = None):
    key = self._workspace_lock_key(workspace_id)
    acquired = await self.client.set(key, "locked", nx=True, ex=timeout)
    if not acquired:
        raise RuntimeError(f"Could not acquire lock for workspace {workspace_id}")
    try:
        yield
    finally:
        await self.client.delete(key)  # 只有获取成功才删除
```

---

## 🟡 中等问题 (Medium)

### 1. 认证缺失: API 路由使用硬编码用户
**文件**: `backend/src/gateway/routers/academic.py:137-143`
```python
async def get_current_user_id() -> str:
    """Get current user ID from request context."""
    return "default-user"  # 硬编码返回默认用户
```
**问题**: 所有 API 端点使用硬编码的 `default-user`，认证中间件未实现，任何人都可以访问所有用户的 workspace。

---

### 2. 内存问题: Chat 线程存储在内存中
**文件**: `backend/src/gateway/routers/chat.py:63-65`
```python
# Simple in-memory store for threads
_threads_store: dict[str, dict] = {}
```
**问题**: 所有对话线程存储在内存中，服务重启会丢失所有数据，且内存使用无限制增长。

---

### 3. SQL 注入风险: 特殊字符未转义
**文件**: `backend/src/academic/services/paper_service.py:182-186`
```python
search_condition = or_(
    Paper.title.ilike(f"%{query}%"),  # 直接插入用户输入
    Paper.abstract.ilike(f"%{query}%"),
)
```
**问题**: 未对用户输入进行转义，特殊字符如 `%` 和 `_` 可能导致意外匹配。

**修复建议**:
```python
from sqlalchemy import func
escaped_query = query.replace("%", "\\%").replace("_", "\\_")
search_condition = or_(
    Paper.title.ilike(f"%{escaped_query}%", escape="\\"),
    ...
)
```

---

### 4. 错误处理: 宽泛的异常捕获
**文件**: `backend/src/gateway/routers/chat.py:220-225`
```python
except Exception:
    # Fallback to simple model call if agent fails
    response = await model.ainvoke([...])
```
**问题**: 捕获所有异常但未记录日志，导致调试困难。

---

### 5. 类型不一致: SubagentResult 有两个定义
**文件**: 
- `backend/src/subagents/executor.py:33`
- `backend/src/subagents/models.py:74`

**问题**: 两个同名类有不同的字段，可能导致混淆和运行时错误。

---

### 6. 未完成的功能: PDF 上传处理
**文件**: `backend/src/gateway/routers/academic.py:300-311`
```python
@router.post("/papers/upload")
async def upload_paper(...):
    # TODO: Implement PDF processing and extraction
    return {"success": True, "filename": file.filename, ...}
```
**问题**: 端点只返回文件信息但不处理，功能未实现。

---

## 🟢 优化建议 (Optimization)

### 1. 数据库连接池配置
**文件**: `backend/src/database/session.py:17-23`
```python
engine = create_async_engine(
    settings.database_url,
    pool_size=5,      # 较小
    max_overflow=10,  # 最大 15 个连接
)
```
**建议**: 对于生产环境，考虑增加连接池大小或使用外部配置。

---

### 2. 缺少数据库索引
**文件**: `backend/src/academic/services/paper_service.py:152-189`
**问题**: `search()` 方法使用 `ILIKE '%query%'` 进行搜索，无法使用索引。

**建议**: 
- 添加 PostgreSQL 的 `pg_trgm` 扩展
- 或使用全文搜索（Elasticsearch/Meilisearch）

---

### 3. 代码重复: 错误处理模式
**建议**: 创建统一的装饰器或中间件处理常见异常。

---

### 4. Sandbox 输出未限制大小
**文件**: `backend/src/sandbox/executor.py:308-309`
```python
stdout_capture = io.StringIO()
```
**建议**: 添加输出大小限制，防止恶意代码消耗大量内存。

---

### 5. Subagent 并发数固定
**文件**: `backend/src/subagents/executor.py:37-38`
```python
_scheduler_pool = ThreadPoolExecutor(max_workers=3, ...)
_execution_pool = ThreadPoolExecutor(max_workers=3, ...)
```
**建议**: 通过配置文件调整，支持高并发场景。

---

### 6. RAG 结果缓存 TTL 固定
**文件**: `backend/src/academic/cache/redis_client.py:66-72`
**建议**: 根据查询类型使用不同的 TTL。

---

## 📝 规范问题 (Style)

| 问题 | 文件 | 建议 |
|------|------|------|
| 缺少类型注解 | `routers/academic.py:127` | `def orm_to_dict(obj) -> dict:` |
| datetime 用法不统一 | `chat.py` vs `events.py` | 统一使用 `datetime.now(UTC)` |
| 中英文注释混用 | `services/auth.py` | 统一使用一种语言 |
| 缺少 API 文档 | 多个路由 | 添加 `response_description` |
| print 代替 logger | `app.py:15-16` | 使用 `logger.info()` |
| 导入顺序不规范 | 多个文件 | 按 PEP 8 规范整理 |

---

## ✅ 亮点 (Highlights)

### 1. 良好的模块化架构
- **Sandbox 系统**: 设计清晰，支持多种 provider（Local、Docker）
- **Subagent 系统**: 使用 registry 模式，易于扩展
- **Middleware 系统**: 采用链式调用，职责分明

### 2. 完善的异常层次结构
**文件**: `backend/src/sandbox/exceptions.py`
- 自定义异常继承体系清晰
- 包含有用的上下文信息（sandbox_id、command、exit_code）

### 3. 使用 Pydantic Settings 进行配置管理
**文件**: `backend/src/config/app_config.py`
- 类型安全的配置
- 环境变量支持
- 分模块的配置类（JWTSettings、DatabaseSettings 等）

### 4. 良好的测试覆盖
- 71 个测试文件
- 1266 个测试函数
- 涵盖单元测试、集成测试、端到端测试

### 5. Dual-layer 并发限制器设计
**文件**: `backend/src/subagents/limiter.py`
- 同时限制全局和每线程的并发
- 使用 asyncio.Semaphore 实现无阻塞等待

### 6. SSE 事件流实现
**文件**: `backend/src/subagents/events.py`
- 支持 pub/sub 模式
- 处理背压
- 自动清理订阅者

---

## 📊 统计摘要

| 指标 | 数值 |
|------|------|
| 检查的 Python 文件数 | ~150+ |
| Sandbox 模块文件数 | 10 |
| Subagents 模块文件数 | 16 |
| API 路由文件数 | 8 |
| 测试文件数 | 71 |
| 测试函数总数 | 1,266 |
| 🔴 严重问题 | **5** |
| 🟡 中等问题 | **6** |
| 🟢 优化建议 | **6** |
| 📝 规范问题 | **6** |

### 覆盖率估算

| 模块 | 覆盖率 |
|------|--------|
| Sandbox 模块 | ~90% |
| Subagents 模块 | ~85% |
| API 层 | ~60% |
| Academic Services | ~70% |
| Agents/Middlewares | ~75% |

---

## 优先修复建议

| 优先级 | 问题 | 预计工时 |
|--------|------|----------|
| **立即** | CORS 配置、JWT secret、认证缺失 | 2-4h |
| **短期** | os 模块 bug、Redis 锁逻辑、类型冲突 | 4-6h |
| **中期** | 全文搜索、PDF 上传、datetime 统一 | 1-2天 |
| **长期** | 连接池配置、内存优化、API 文档 | 2-3天 |

---

## 附录：关键文件清单

### 需要立即修复的文件
1. `backend/src/gateway/app.py` - CORS 配置
2. `backend/src/config/app_config.py` - JWT secret
3. `backend/src/sandbox/executor.py` - os 模块 bug
4. `backend/src/subagents/executor.py` - 并发锁
5. `backend/src/academic/cache/redis_client.py` - 锁逻辑

### 需要完善的文件
1. `backend/src/gateway/routers/academic.py` - 认证 + PDF 上传
2. `backend/src/gateway/routers/chat.py` - 内存存储 + 日志
3. `backend/src/academic/services/paper_service.py` - 搜索优化

---

*报告生成时间: 2026-03-10 19:10*  
*审查工具: Claude Code ACP*
