# Workspace Template System Design

**Date:** 2026-03-31
**Status:** Approved
**Goal:** Add template import support so users can upload school/journal/fund templates that influence the entire writing pipeline — from outline design to final compilation.

## Core Principles

- **No template = LLM 自由生成**，模板是可选的增强，不是必需的前置条件
- **对话式引入**：LLM 在定稿阶段主动提醒用户上传模板，而不是独立的设置页面
- **全链路影响**：模板规范注入到大纲设计、正文撰写、编译导出等所有写作类 feature
- **软著/专利用系统内置模板**（后续提供），thesis/sci/proposal 支持用户上传

## 1. Template Classification

| Workspace Type | 模板来源 | 文件类型 |
|---|---|---|
| thesis | 用户上传 | .docx, .tex, .txt, .md |
| sci | 用户上传 | .tex, .cls, .sty, .docx, .txt |
| proposal | 用户上传 | .docx, .txt, .md |
| software_copyright | 系统内置 | builtin (后续提供) |
| patent | 系统内置 | builtin (后续提供) |

## 2. Data Model

```python
class WorkspaceTemplate(Base):
    __tablename__ = "workspace_templates"

    id: UUID (primary)
    workspace_id: str (FK → workspaces.id)

    name: str                        # "清华大学硕士论文模板"
    category: str                    # "thesis" | "sci" | "proposal" | "copyright" | "patent"
    source_type: str                 # "docx" | "latex" | "text" | "markdown" | "builtin"
    source_file_path: str | None     # 原始上传文件路径（内置模板为 None）

    # Parsed structured spec
    structure: JSONB                 # 章节结构
    format_spec: JSONB               # 排版规范
    content_guidelines: JSONB        # 内容要求
    latex_preamble: str | None       # LaTeX 前导区

    is_active: bool = True           # 同一 workspace 只有一个激活模板
    is_builtin: bool = False
    created_at, updated_at: timestamps
```

### structure format
```json
{
  "chapters": [
    { "title": "绪论", "level": 1, "required": true, "description": "研究背景、目的、意义", "suggested_word_count": "3000-5000" },
    { "title": "文献综述", "level": 1, "required": true, "description": "相关理论和研究综述" }
  ]
}
```

### format_spec format
```json
{
  "page_size": "A4",
  "margins": { "top": "2.5cm", "bottom": "2.5cm", "left": "3cm", "right": "2cm" },
  "font_body": "宋体 小四",
  "font_heading": "黑体",
  "line_spacing": 1.5,
  "bibliography_style": "gbt7714"
}
```

## 3. User Flow

```
用户在 chat 中推进写作 (大纲设计/论文撰写 skill)
    ↓
LLM 检测到用户进入定稿阶段（有初步大纲或草稿）
    ↓
LLM 主动询问：
  "你有学校/期刊的论文模板吗？上传后我会按模板的结构和格式来写。
   没有的话我会自由生成，你随时可以补充模板。"
    ↓
[用户选择上传] → 拖拽/选择文件 → kind="template"
    ↓
后端解析模板文件 → 提取 structure + format_spec + content_guidelines
    ↓
存储为 WorkspaceTemplate，标记 is_active=true
    ↓
后续写作类 feature 自动参考模板规范
```

## 4. Template Upload Entry Point

**不是独立页面**。模板上传通过 chat 附件系统，增加一种新的 upload kind：

```
现有 kind: "transient" | "literature" | "workspace_context"
新增 kind: "template"
```

**上传处理**：
1. 接收文件，验证类型（.docx/.tex/.txt/.md）
2. 保存到 `.wenjin/workspace_uploads/{workspace_id}/templates/`
3. 调用 LLM 解析模板内容 → 提取结构化规范
4. 创建 WorkspaceTemplate 记录
5. 将旧的 active template 标记为 is_active=false
6. 返回解析结果给用户确认

**LLM 解析 prompt**（用于从任意格式的模板文件提取结构化规范）：
```
从以下模板文件中提取论文写作规范。返回 JSON：
{
  "name": "模板名称",
  "structure": { "chapters": [...] },
  "format_spec": { ... },
  "content_guidelines": { ... }
}

模板内容：
{file_content}
```

## 5. Template Influence on Writing Pipeline

### 注入方式

通过 `WorkspaceContextMiddleware` 加载 workspace 的 active template，注入到 ThreadState 的 `template_context` 字段。在 `apply_prompt_template` 中追加到 system prompt。

### 各环节影响

| Feature | 无模板行为 | 有模板行为 |
|---|---|---|
| framework-designer (大纲设计) | LLM 自由设计章节结构 | 按 template.structure 的章节列表生成大纲 |
| fullpaper-writer (论文撰写) | LLM 自由写作 | 每章按 template.content_guidelines 的要求写 |
| figure-designer (图表设计) | 自由设计 | 参考 template.format_spec 的图表格式要求 |
| doc-compiler (编译导出) | 使用默认 THESIS_TEMPLATE_ZH | 使用 template.latex_preamble（如有），否则将 format_spec 应用到默认模板 |
| peer-reviewer (同行评审) | 通用学术评审 | 检查是否符合模板规定的必需章节和格式 |

### System prompt 注入格式

```
## 写作模板规范

当前工作区已配置写作模板：{template.name}

### 章节结构要求
{formatted structure}

### 排版格式要求
{formatted format_spec}

### 内容要求
{formatted content_guidelines}

请严格按照以上模板规范生成内容。如果用户的需求与模板规范冲突，优先询问用户。
```

## 6. API Endpoints

```
POST   /api/workspaces/{workspace_id}/templates/upload   — 上传并解析模板
GET    /api/workspaces/{workspace_id}/templates           — 列出 workspace 的模板
GET    /api/workspaces/{workspace_id}/templates/active     — 获取当前激活模板
PUT    /api/workspaces/{workspace_id}/templates/{id}/activate — 切换激活模板
DELETE /api/workspaces/{workspace_id}/templates/{id}       — 删除模板
```

## 7. Frontend Changes

- **Upload component**：chat 附件上传增加 `kind="template"` 选项
- **WorkspaceInspector**：在"成果"tab 或新增"模板"tab 显示当前模板信息
- **Template badge**：workspace dashboard header 显示当前模板名称（如有）

## 8. Files to Create/Modify

### Backend
| File | Change |
|---|---|
| `backend/src/database/models/workspace_template.py` | **新建** — ORM model |
| `backend/src/database/models/__init__.py` | 导出 WorkspaceTemplate |
| `backend/src/services/template_service.py` | **新建** — CRUD + 解析逻辑 |
| `backend/src/gateway/routers/templates.py` | **新建** — API endpoints |
| `backend/src/gateway/app.py` | 注册 templates router |
| `backend/src/gateway/routers/uploads.py` | 增加 kind="template" 处理 |
| `backend/src/agents/middlewares/workspace_context.py` | 加载 active template |
| `backend/src/agents/lead_agent/agent.py` | 注入 template_context 到 prompt |
| `backend/src/agents/thread_state.py` | 增加 template_context 字段 |
| `backend/src/workspace_features/services/thesis_feature_service.py` | 编译时使用模板 |
| Alembic migration | 新建 workspace_templates 表 |

### Frontend
| File | Change |
|---|---|
| `frontend/lib/api/types.ts` | 增加 WorkspaceTemplate 类型 |
| `frontend/lib/api/workspace.ts` | 增加模板 API 函数 |
| `frontend/stores/workspace.ts` | 增加 template 状态 |
| Chat attachment UI | 增加"上传为模板"选项 |
