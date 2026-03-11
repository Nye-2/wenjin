# Workspace 认证统一方案设计文档

> 创建日期: 2026-03-11
> 状态: 已批准
> 作者: Claude + 用户

## 1. 问题分析

### 1.1 当前问题

在添加 workspace 功能模块时遇到创建 workspace 报错，根本原因是：

1. **认证与用户ID传递不一致**
   - 后端: `workspaces.py` 将 `user_id` 改为 Query 参数，需要前端显式传递
   - 前端: 从 `localStorage` 读取用户ID，失败时 fallback 到 `'test-user-001'`
   - 问题: 与认证系统脱节，不够安全

2. **Features 模块认证缺失**
   - `features.py` 硬编码 `user_id="system"`
   - 没有使用认证中间件获取真实用户

3. **前后端状态不一致**
   - 前端可能使用 fallback 用户ID
   - 后端期望真实的认证用户

### 1.2 根本原因

系统已有完善的 JWT 认证机制（`get_current_user` 依赖），但 workspace API 没有使用它，而是通过 Query 参数传递 `user_id`，导致：
- 安全风险：用户可能伪造其他人的 user_id
- 代码冗余：前后端都需要管理 user_id
- 不一致：与其他使用认证的 API 不统一

## 2. 解决方案

### 2.1 核心原则

**所有 workspace 相关操作都必须通过认证中间件获取当前用户，不再接受客户端传递的 `user_id` 参数。**

### 2.2 方案选择

采用**方案1：使用认证中间件统一获取用户ID**

**优点**：
- ✅ 更安全：防止用户伪造身份
- ✅ 更简洁：代码量减少，逻辑更清晰
- ✅ 更一致：统一使用认证系统
- ✅ 易维护：未来添加新功能无需考虑 user_id 传递

**缺点**：
- ❌ 需要前端始终传递认证 token（已通过 axios interceptor 实现）
- ❌ 所有 workspace 操作都需要认证（符合业务需求）

## 3. 架构变更

### 3.1 变更范围

```
后端 API 层 (backend/src/gateway/routers/)
├── workspaces.py - 所有端点添加认证依赖
├── features.py - 功能执行端点添加认证依赖
└── 移除 user_id Query 参数

前端 API 层 (frontend/lib/)
└── api.ts
    ├── 删除 getCurrentUserId() 函数
    ├── 移除手动传递 user_id 的代码
    └── 依赖 axios interceptor 自动添加 Authorization header
```

### 3.2 数据流

```
前端请求
  ↓
axios interceptor (自动添加 Authorization header)
  ↓
后端 FastAPI 中间件
  ↓
get_current_user 依赖 (验证 JWT)
  ↓
提取 user_id
  ↓
业务逻辑
```

## 4. 详细实现

### 4.1 后端修改

#### 文件：`backend/src/gateway/routers/workspaces.py`

**修改1：导入认证依赖**
```python
from src.gateway.routers.auth import get_current_user
from src.database import User
```

**修改2：create_workspace 端点**
```python
@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),  # 替换 user_id Query 参数
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Create a new workspace."""
    try:
        workspace = await workspace_service.create(
            user_id=str(current_user.id),  # 从认证用户获取
            name=request.name,
            type=request.type,
            discipline=request.discipline,
            description=request.description,
            config=request.config,
        )
        return workspace_to_response(workspace)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
```

**修改3：list_workspaces 端点**
```python
@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),  # 替换 user_id Query 参数
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """List workspaces for current user."""
    workspaces = await workspace_service.list_by_user(str(current_user.id))
    return [workspace_to_response(w) for w in workspaces]
```

**其他端点**：
- `get_workspace`、`update_workspace`、`delete_workspace` 保持不变（通过 workspace_id 访问）

#### 文件：`backend/src/gateway/routers/features.py`

**修改1：导入认证依赖**
```python
from src.gateway.routers.auth import get_current_user
from src.database import User
```

**修改2：get_workspace_features 端点**
```python
@router.get(
    "/workspaces/{workspace_id}/features",
    response_model=FeaturesResponse,
)
async def get_workspace_features(
    workspace_id: str,
    current_user: User = Depends(get_current_user),  # 添加认证
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> FeaturesResponse:
    """Get available features for a workspace."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 验证 workspace 所有权
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    workspace_type = workspace.type.value if hasattr(workspace.type, 'value') else str(workspace.type) if workspace.type else "thesis"
    features = WORKSPACE_FEATURES.get(workspace_type, [])
    return FeaturesResponse(features=features)
```

**修改3：execute_feature 端点**
```python
@router.post(
    "/workspaces/{workspace_id}/features/{feature_id}/execute",
    response_model=ExecuteResponse,
)
async def execute_feature(
    workspace_id: str,
    feature_id: str,
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),  # 添加认证
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> ExecuteResponse:
    """Execute a feature for a workspace."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 验证所有权
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    workspace_type = workspace.type.value if hasattr(workspace.type, 'value') else str(workspace.type) if workspace.type else "thesis"
    feature = _get_feature_by_id(workspace_type, feature_id)

    if not feature:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' not found for workspace type '{workspace_type}'",
        )

    task_id = await _create_and_start_task(
        workspace_id=workspace_id,
        feature=feature,
        params=request.params,
        background_tasks=background_tasks,
        user_id=str(current_user.id),  # 传递真实用户ID
    )

    logger.info(f"[Features] Started {feature_id} task {task_id} for workspace {workspace_id}")

    return ExecuteResponse(
        task_id=task_id,
        status="running",
        feature_id=feature_id,
        message=f"Started {feature.name}",
    )
```

**修改4：_create_and_start_task 函数签名**
```python
async def _create_and_start_task(
    workspace_id: str,
    feature: WorkspaceFeature,
    params: dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: str,  # 添加参数
) -> str:
    """Create task and start execution based on feature type."""
    import uuid

    # For thesis features, use thesis task system
    if feature.agent in ("thesis_writer", "librarian", "figure_planner"):
        from src.thesis.task_storage import create_thesis_task
        from src.thesis.workflow.runner import run_thesis_workflow

        paper_title = params.get("title", params.get("paper_title", "未命名论文"))

        task = create_thesis_task(
            workspace_id=workspace_id,
            paper_title=paper_title,
            message=f"Starting {feature.name}...",
        )

        workflow_request = {
            "workspace_id": workspace_id,
            "paper_title": paper_title,
            "discipline": params.get("discipline", "计算机科学"),
            "abstract_content": params.get("abstract", ""),
            "framework_json": params.get("framework", {}),
            "enable_search": feature.id in ("literature", "outline"),
            "enable_images": feature.id == "figure",
        }

        background_tasks.add_task(
            run_thesis_workflow,
            task.task_id,
            workflow_request,
        )

        return task.task_id

    # For other agents, use generic task system
    from src.task.service import TaskService
    from src.task.store import TaskStore
    from src.academic.cache.redis_client import redis_client

    task_id = await TaskService(TaskStore(redis_client, None)).submit_task(
        user_id=user_id,  # 使用真实用户ID
        task_type=f"feature:{feature.id}",
        payload={
            "workspace_id": workspace_id,
            "feature_id": feature.id,
            "agent": feature.agent,
            **params,
        },
    )

    return task_id
```

### 4.2 前端修改

#### 文件：`frontend/lib/api.ts`

**修改1：删除 getCurrentUserId 函数**
```typescript
// 删除第148-166行的 getCurrentUserId 函数
```

**修改2：简化 listWorkspaces 函数**
```typescript
export async function listWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  const response = await apiClient.get('/workspaces');
  return response.data;
}
```

**修改3：简化 createWorkspace 函数**
```typescript
export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  const response = await apiClient.post('/workspaces', data);
  return response.data;
}
```

**关键点**：
- axios interceptor 已在第20-30行自动添加 Authorization header
- 后端从 JWT token 中提取 user_id
- 前端代码大幅简化

## 5. 错误处理

### 5.1 HTTP 状态码

| 状态码 | 场景 | 错误信息 |
|--------|------|----------|
| 401 | 未提供认证 token | "Not authenticated" |
| 401 | Token 无效或过期 | "Invalid or expired token" |
| 403 | 访问其他用户的资源 | "Access denied" |
| 404 | Workspace 不存在 | "Workspace not found" |

### 5.2 前端错误处理

前端应该处理以下情况：
1. 401 错误 → 跳转到登录页
2. 403 错误 → 显示权限错误提示
3. 404 错误 → 显示资源不存在提示

## 6. 测试策略

### 6.1 后端测试

**测试用例**：
```python
# 1. 未认证用户无法创建 workspace
async def test_create_workspace_requires_auth(client):
    response = await client.post("/api/workspaces", json={...})
    assert response.status_code == 401

# 2. 认证用户可以创建 workspace
async def test_create_workspace_with_auth(client, auth_headers):
    response = await client.post(
        "/api/workspaces",
        json={"name": "Test", "type": "thesis"},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == current_user_id

# 3. 用户无法访问其他用户的 workspace features
async def test_access_other_user_workspace_forbidden(client, auth_headers):
    response = await client.get(
        "/api/workspaces/other-user-workspace-id/features",
        headers=auth_headers
    )
    assert response.status_code == 403
```

**运行测试**：
```bash
cd backend
uv run pytest tests/gateway/routers/test_workspaces.py -v
uv run pytest tests/gateway/routers/test_features.py -v
```

### 6.2 前端测试

**验证清单**：
- [ ] 未登录用户点击创建 workspace → 跳转到登录页
- [ ] 登录用户可以创建 workspace
- [ ] 创建的 workspace 属于当前用户
- [ ] 可以查看自己的 workspace 列表

### 6.3 集成测试

**测试流程**：
1. 启动后端服务
2. 启动前端服务
3. 登录用户
4. 创建 workspace
5. 查看 workspace 列表
6. 执行 feature
7. 验证所有操作都使用了正确的用户ID

## 7. 实施步骤

### 步骤1：后端修改
```bash
cd backend
# 修改 workspaces.py
# 修改 features.py
```

### 步骤2：后端测试
```bash
cd backend
uv run pytest tests/gateway/routers/test_workspaces.py -v
uv run pytest tests/gateway/routers/test_features.py -v
```

### 步骤3：前端修改
```bash
cd frontend
# 修改 api.ts
```

### 步骤4：前端验证
```bash
cd frontend
npm run build
```

### 步骤5：集成测试
```bash
# 启动后端
cd backend
uv run uvicorn src.gateway.app:app --reload --port 8001

# 启动前端（新终端）
cd frontend
npm run dev

# 手动测试完整流程
```

## 8. 验证清单

- [ ] 后端所有 workspace 相关测试通过
- [ ] 前端构建无错误
- [ ] 未登录用户无法创建 workspace（返回401）
- [ ] 登录用户可以创建 workspace
- [ ] 创建的 workspace 属于当前登录用户
- [ ] 用户无法访问其他用户的 workspace features
- [ ] Features 执行使用真实用户ID

## 9. 回滚计划

如果出现问题，恢复以下文件：
```bash
git checkout backend/src/gateway/routers/workspaces.py
git checkout backend/src/gateway/routers/features.py
git checkout frontend/lib/api.ts
```

## 10. 影响范围

### 10.1 破坏性变更

**后端 API 变更**：
- `POST /api/workspaces` - 移除 `user_id` Query 参数，改为从认证 token 获取
- `GET /api/workspaces` - 移除 `user_id` Query 参数，改为从认证 token 获取

**前端变更**：
- 移除 `getCurrentUserId()` 函数
- 简化 API 调用，不再手动传递 `user_id`

### 10.2 兼容性

- ✅ 向后兼容：认证机制保持不变
- ✅ 前端兼容：axios interceptor 已实现
- ⚠️ API 变更：需要同时部署前后端

## 11. 后续优化

完成本次修复后，可以考虑：

1. **扩展认证到其他模块**
   - 检查其他 API 是否也有类似问题
   - 统一使用认证中间件

2. **增强权限控制**
   - 实现基于角色的访问控制（RBAC）
   - 支持 workspace 共享功能

3. **改进错误提示**
   - 前端统一错误处理
   - 更友好的错误消息

## 12. 文档更新

实施完成后需要更新：
- [ ] README.md - 说明认证要求
- [ ] API 文档 - 更新参数说明
- [ ] 开发指南 - 添加认证最佳实践
