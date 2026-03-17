# LangGraph 全工作区实现 — Agent 交接文档

**日期**: 2026-03-17
**目标**: 两个 Agent 并行完成 4 个工作区的 LangGraph 子图实现 + 架构重构
**设计规格**: `docs/superpowers/specs/2026-03-17-pure-langgraph-all-workspaces-design.md`
**修改指南**: `docs/architecture/workspace-ai-modification-playbook.md`

---

## 任务拆分

| Agent | 工作区 | 功能数 | 图模块 |
|-------|--------|--------|--------|
| **Agent A** | SCI (3) + Patent (2) | 5 | 5 个图 + 共享基础设施 + 架构重构 |
| **Agent B** | Proposal (2) + Software Copyright (2) | 4 | 4 个图 + 测试更新 + Playbook 更新 |

**Agent A 额外负责**: 创建 `workspace_lead_agent.py`、`_shared/utils.py`、重构 `workspace_feature_handler.py` 和 `base.py`
**Agent B 额外负责**: 删除旧 handler 文件、更新烟测/E2E 测试、更新 playbook

---

## 执行顺序约束

```
Agent A (先启动):
  Step A1: 创建 workspace_lead_agent.py + _shared/utils.py  ← Agent B 依赖这一步
  Step A2: 实现 SCI 3 个图 + 单元测试
  Step A3: 实现 Patent 2 个图 + 单元测试
  Step A4: 重构 workspace_feature_handler.py (所有工作区走 LangGraph)
  Step A5: 重构 base.py (deep_research 路径)
  Step A6: 运行测试矩阵

Agent B (在 A1 完成后启动，或同时启动但图文件中先用临时 import):
  Step B1: 实现 Proposal 2 个图 + 单元测试
  Step B2: 实现 Software Copyright 2 个图 + 单元测试
  Step B3: 删除 5 个 handler 文件
  Step B4: 清理 runtime.py
  Step B5: 更新烟测/E2E 测试
  Step B6: 更新 playbook
  Step B7: 运行完整测试矩阵
```

**并行安全说明**: Agent A 和 Agent B 修改的文件集合不重叠（除了各自新建的图文件）。唯一的依赖是 Agent B 的图需要从 `workspace_lead_agent.py` 导入 `register_feature_graph`，这个文件由 Agent A 在 Step A1 创建。如果 Agent B 先启动，可以先创建图文件，import 行写好但暂时不运行注册（测试时 mock）。

---

## 参考案例：Thesis 工作区

**Thesis 是唯一已完成 LangGraph 实现的工作区，是你的实现蓝本。**

### 关键参考文件

| 用途 | 文件路径 |
|------|---------|
| 图注册装饰器 | `backend/src/agents/thesis_lead_agent.py` |
| 最简单的图（194行） | `backend/src/agents/graphs/thesis/literature_management.py` |
| 最复杂的图（540行） | `backend/src/agents/graphs/thesis/deep_research.py` |
| 多步推理图 | `backend/src/agents/graphs/thesis/opening_research.py` |
| Service 层调用模式 | `backend/src/workspace_features/services/thesis_feature_service.py` |
| 图单元测试模式 | `backend/tests/agents/graphs/thesis/test_literature_management.py` |
| Handler 结果包装 | `backend/src/task/handlers/workspace_feature_handler.py` → `_try_langgraph_execution()` |

### 图函数签名模板

每个图函数必须遵循此签名：

```python
from src.agents.thesis_lead_agent import register_feature_graph
# 迁移后改为:
# from src.agents.workspace_lead_agent import register_feature_graph

@register_feature_graph("feature_id")  # 或 register_feature_graph("feature_id", workspace_type="sci")
async def feature_name_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    ...
```

### initial_state 结构

```python
{
    "messages": [SystemMessage(content=system_prompt)],
    "workspace_id": str,
    "workspace_type": str,         # "sci", "proposal", "patent", "software_copyright"
    "discipline": str,
    "knowledge_context": str | None,  # 用户记忆文本（XML 格式）
}
```

### 图返回值必须包含的字段

```python
{
    "generation_mode": "llm" | "partial_llm" | "template_fallback",
    "generated_at": str,  # ISO datetime
    # ... 业务数据字段 ...
}
```

图返回值会被 `_try_langgraph_execution()` 包装为标准 payload：
```python
{
    "success": True,
    "feature_id": str,
    "feature_name": str,
    "workspace_type": str,
    "handler_key": str,
    "generation_mode": str,
    "message": str,
    "data": <图返回值>,
    "artifacts": [{"id": str, "type": str, "title": str}],
    "refresh_targets": ["artifacts"],
}
```

### LLM 调用模式

```python
from src.models.factory import create_chat_model

model = create_chat_model("default", temperature=0.3)
response = await model.ainvoke(prompt_text)
content = response.content if hasattr(response, "content") else str(response)
# 然后用 JSON 解析
```

### JSON 解析模式

```python
def _parse_json_response(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
```

### 记忆注入模式

```python
memory_context = initial_state.get("knowledge_context") or ""
mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""
prompt = f"...你的提示词...\n{mem_text}"
```

### 降级策略模式（关键！）

每个图必须：
1. 在 LLM 调用外层 try/except
2. 失败时调用 service 层的 template_fallback 或自己构建模板
3. 在结果中标记 `generation_mode`

```python
try:
    model = create_chat_model("default", temperature=0.3)
    response = await model.ainvoke(prompt)
    parsed = _parse_json_response(response.content)
    if parsed:
        generation_mode = "llm"
        # 使用 parsed 数据
    else:
        generation_mode = "template_fallback"
        # 使用模板数据
except Exception:
    generation_mode = "template_fallback"
    # 使用模板数据
```

---

## Agent A 详细任务

### A1: 创建 `workspace_lead_agent.py`

**文件**: `backend/src/agents/workspace_lead_agent.py`

从 `thesis_lead_agent.py` 提取通用逻辑，关键变化：

1. `_FEATURE_GRAPH_REGISTRY` 支持复合键 `{workspace_type}.{feature_id}`
2. `_ensure_graphs_loaded(workspace_type)` 按工作区懒加载
3. `execute_feature_graph(workspace_type, feature_id, payload, *, user_id)` 替代 `execute_thesis_feature_graph()`
4. 图查找顺序: `"{workspace_type}.{feature_id}"` → `"{feature_id}"`（向后兼容 thesis）

**必须保证**: `thesis_lead_agent.py` 仍然可用 — 添加重新导出：
```python
# thesis_lead_agent.py (修改后)
from src.agents.workspace_lead_agent import register_feature_graph, execute_feature_graph

# 向后兼容 alias
execute_thesis_feature_graph = lambda feature_id, payload, **kw: execute_feature_graph("thesis", feature_id, payload, **kw)
_FEATURE_GRAPH_REGISTRY = ...  # 从 workspace_lead_agent 导入
```

### A2: SCI 工作区 — 3 个图

#### `backend/src/agents/graphs/sci/__init__.py`
```python
"""SCI workspace LangGraph sub-graphs."""
```

#### `backend/src/agents/graphs/sci/literature_search.py`

**Registry 定义参考** (`registry.py`):
```python
workspace_type="sci", id="literature_search", handler_key="sci.literature_search"
stages: search → filter
```

**Handler 参数提取** (来自 `handlers/sci.py`):
```python
query = context.params.get("query") or context.params.get("keywords") or context.workspace_description or context.workspace_name or "研究主题"
discipline = context.params.get("discipline") or context.workspace_discipline
preferred_model = context.params.get("model_id")  # optional str
```

**Service 函数调用**:
```python
from src.workspace_features.services import build_literature_search_payload

result = await build_literature_search_payload(
    workspace_id=workspace_id,
    query=query,
    discipline=discipline,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "query": str,
    "discipline": str,
    "papers": [{"title", "authors", "year", "venue", "abstract", "relevance"}],
    "top_hits": [{"title": str, "reason": str}],
    "filters": {"year_range": {"min": int, "max": int}, "sources": [str], "quartiles": [str]},
    "summary": str,
    "search_strategy": "llm_synthesis" | "template_fallback",
    "generated_at": str,
    "model_id": str | None,
    "existing_literature_count": int,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.LITERATURE_SEARCH_RESULTS` (`"literature_search_results"`)
- Title: `"{workspace_name} - Literature Search"`

**图设计**: 4 阶段管道
1. 参数提取 + 数据库文献加载 (通过 `LiteratureService`)
2. 并行 LLM：关键词扩展 + 文献推荐 + 趋势分析
3. 相关性排序 + 去重
4. 结构化输出

**输出语言**: 英文

---

#### `backend/src/agents/graphs/sci/paper_analysis.py`

**Registry**: `workspace_type="sci", id="paper_analysis", handler_key="sci.paper_analysis"`

**Handler 参数提取**:
```python
paper_id = context.params.get("paper_id")  # optional str
paper_title = context.params.get("paper_title") or context.workspace_name
paper_abstract = context.params.get("paper_abstract") or context.workspace_description
preferred_model = context.params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_paper_analysis_payload

result = await build_paper_analysis_payload(
    workspace_id=workspace_id,
    paper_id=paper_id,
    paper_title=paper_title,
    paper_abstract=paper_abstract,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "paper_id": str | None,
    "paper_title": str,
    "analysis_mode": "llm" | "template_fallback",
    "sections": {
        "methodology": {"title": str, "content": str, "key_points": [str]},
        "experiments": {"title": str, "content": str, "key_points": [str]},
        "conclusions": {"title": str, "content": str, "key_points": [str]},
        "innovations": {"title": str, "content": str, "key_points": [str]},
    },
    "summary": str,
    "quality_assessment": {"methodology_rigor": str, "experiment_completeness": str, "contribution_level": str},
    "recommendations": [str],
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.PAPER_ANALYSIS` (`"paper_analysis"`)
- Title: `"{workspace_name} - Paper Analysis"`

**图设计**: 4 阶段
1. 论文数据加载（从 paper_id 或 abstract）
2. 并行 LLM 分析（方法论 + 实验 + 创新点 + 结论）
3. 质量评估
4. 综合建议 + 结构化输出

**输出语言**: 英文

---

#### `backend/src/agents/graphs/sci/writing.py`

**Registry**: `workspace_type="sci", id="writing", handler_key="sci.writing"`

**Handler 参数提取**:
```python
paper_title = context.params.get("paper_title") or context.workspace_name
section_type = context.params.get("section_type", "introduction")  # 8 种: abstract, introduction, related_work, methodology, experiments, results, discussion, conclusion
target_words = context.params.get("target_words")  # optional int, 默认 800
context_artifact_ids = context.params.get("context_artifact_ids")  # optional list[str]
preferred_model = context.params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_sci_writing_payload

result = await build_sci_writing_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    workspace_description=workspace_description,
    paper_title=paper_title,
    section_type=section_type,
    target_words=target_words,
    context_artifact_ids=context_artifact_ids,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "section_type": str,
    "section_title": str,
    "content": str,
    "outline": [str],
    "references": [str],
    "word_count": int,
    "writing_mode": "llm" | "template_fallback",
    "output_language": "en",
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.PAPER_DRAFT` (`"paper_draft"`)
- Title: `"{workspace_name} - {section_type}"`

**图设计**: 4 阶段
1. 上下文工件加载
2. 章节规划
3. LLM 生成
4. 学术语言润色 + 参考文献整合

**输出语言**: 英文

---

### A3: Patent 工作区 — 2 个图

#### `backend/src/agents/graphs/patent/__init__.py`
```python
"""Patent workspace LangGraph sub-graphs."""
```

#### `backend/src/agents/graphs/patent/patent_outline.py`

**Registry**: `workspace_type="patent", id="patent_outline", handler_key="patent.patent_outline"`

**Handler 参数提取**:
```python
innovation_description = params.get("innovation_description") or context.workspace_description or context.workspace_name
technical_field = params.get("technical_field", "")
application_scenario = params.get("application_scenario", "")
implementation_method = params.get("implementation_method", "")
preferred_model = params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_patent_outline_payload

result = await build_patent_outline_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    workspace_description=workspace_description,
    innovation_description=innovation_description,
    technical_field=technical_field,
    application_scenario=application_scenario,
    implementation_method=implementation_method,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "innovation_description": str,
    "technical_field": str,
    "sections": [{"id": str, "title": str, "content": str, "source": str, "hints": [str]}],
    "claims_draft": {
        "independent_claims": [{"id": str, "type": str, "content": str, "source": str}],
        "dependent_claims": [{"id": str, "type": str, "content": str, "source": str}],
        "hints": [str],
    },
    "evidence_points_needed": [str],
    "generation_mode": "llm" | "template_fallback",
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.PATENT_OUTLINE` (`"patent_outline"`)
- Title: `"{workspace_name} - 专利说明书框架"`

**图设计**: 4 阶段
1. 创新点提取 + 技术领域分类
2. 并行 LLM 生成 5 个说明书章节
3. 权利要求书草拟
4. 证据点清单 + 结构化输出

**输出语言**: 中文

---

#### `backend/src/agents/graphs/patent/prior_art_search.py`

**Registry**: `workspace_type="patent", id="prior_art_search", handler_key="patent.prior_art_search"`

**Handler 参数提取**:
```python
keywords = _normalize_list(params.get("keywords"))  # list[str], 最多 5 个
ipc_codes = _normalize_list(params.get("ipc_codes"))
time_range = str(params.get("time_range") or "近5年").strip()
preferred_model = params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_prior_art_search_payload

result = await build_prior_art_search_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    workspace_description=workspace_description,
    keywords=keywords,
    ipc_codes=ipc_codes,
    time_range=time_range,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "keywords": [str],
    "ipc_codes": [str],
    "time_range": str,
    "search_scope": {"keywords": [str], "ipc_codes": [str], "time_range": str, "suggested_databases": [str]},
    "comparison_table": [{"id": str, "title": str, "patent_number": str, ...}],
    "novelty_risks": [{"id": str, "level": str, "description": str, ...}],
    "avoidance_suggestions": [{"id": str, "category": str, "content": str}],
    "next_steps": [str],
    "generation_mode": "llm" | "template_fallback",
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.PRIOR_ART_REPORT` (`"prior_art_report"`)
- Title: `"{workspace_name} - 现有技术分析"`

**图设计**: 4 阶段
1. 检索策略构建
2. 并行 LLM 分析（对比 + 风险评估）
3. 规避建议
4. 后续步骤 + 结构化输出

**输出语言**: 中文

---

### A4: 重构 `workspace_feature_handler.py`

**文件**: `backend/src/task/handlers/workspace_feature_handler.py`

关键变更：

1. **`execute_workspace_feature()`** — 移除 `if workspace_type == "thesis"` 分支，所有 workspace_type 统一调用 `workspace_lead_agent.execute_feature_graph(workspace_type, feature_id, ...)`

2. **`_try_langgraph_execution()`** — 修改为调用 `workspace_lead_agent.execute_feature_graph()` 而非 `execute_thesis_feature_graph()`；移除 `None` 返回（失败直接抛异常）

3. **`_build_langgraph_artifact_drafts()`** — 扩展支持所有工作区：
   - SCI: `literature_search` → `LITERATURE_SEARCH_RESULTS`, `paper_analysis` → `PAPER_ANALYSIS`, `writing` → `PAPER_DRAFT`
   - Patent: `patent_outline` → `PATENT_OUTLINE`, `prior_art_search` → `PRIOR_ART_REPORT`
   - Proposal: `proposal_outline` → `PROPOSAL`, `background_research` → `BACKGROUND_RESEARCH`
   - Software Copyright: `copyright_materials` → `COPYRIGHT_MATERIALS`, `technical_description` → `TECHNICAL_DESCRIPTION`

4. **`_ensure_graphs_loaded()`** — 删除（移到 workspace_lead_agent）

5. **`execute_thesis_generation()`** — 保留，但 `_THESIS_WRITING_LANGGRAPH_ACTIONS` 的路由改为调用 `workspace_lead_agent.execute_feature_graph("thesis", "thesis_writing", ...)`

### A5: 重构 `base.py`

**文件**: `backend/src/task/tasks/base.py`

`deep_research` 分支（第 214-238 行）改为：
```python
if task_type == "deep_research" and str(payload.get("workspace_type", "")).lower() == "thesis":
    from src.agents.workspace_lead_agent import execute_feature_graph
    result = await execute_feature_graph("thesis", "deep_research", payload, user_id=...)
    _schedule_memory_extraction(payload, result)
    return result
```
移除 skill handler fallback。

---

## Agent B 详细任务

### B1: Proposal 工作区 — 2 个图

#### `backend/src/agents/graphs/proposal/__init__.py`
```python
"""Proposal workspace LangGraph sub-graphs."""
```

#### `backend/src/agents/graphs/proposal/proposal_outline.py`

**Registry**: `workspace_type="proposal", id="proposal_outline", handler_key="proposal.proposal_outline"`

**Handler 参数提取**:
```python
topic = context.params.get("topic", context.workspace_name)
proposal_type = str(context.params.get("proposal_type", "other"))
period_months = context.params.get("period_months")  # optional int
preferred_model = context.params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_proposal_outline_payload

result = await build_proposal_outline_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    topic=topic,
    proposal_type=proposal_type,
    period_months=period_months,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "topic": str,
    "proposal_type": str,
    "proposal_type_label": str,
    "period_months": int,
    "sections": [{"id": str, "title": str, "content": str, "source": "llm" | "template"}],
    "milestones": [{"phase": str, "time": str, "deliverable": str}],
    "risks": [{"type": str, "description": str, "mitigation": str}],
    "generation_mode": "llm" | "template_fallback",
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.PROPOSAL` (`"proposal"`)
- Title: `"{workspace_name} - 申报书大纲"`

**图设计**: 4 阶段
1. 参数规范化（proposal_type 别名映射、周期校验）
2. 并行 LLM 生成 5 个主要章节
3. 里程碑规划 + 风险分析
4. 章节衔接检查 + 结构化输出

**输出语言**: 中文

---

#### `backend/src/agents/graphs/proposal/background_research.py`

**Registry**: `workspace_type="proposal", id="background_research", handler_key="proposal.background_research"`

**Handler 参数提取**:
```python
keywords = str(context.params.get("keywords") or context.workspace_name).strip()
industry_scope = str(context.params.get("industry_scope") or "").strip()
time_range = str(context.params.get("time_range") or "近5年").strip()
preferred_model = context.params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_background_research_payload

result = await build_background_research_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    keywords=keywords,
    industry_scope=industry_scope,
    time_range=time_range,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "keywords": str,
    "industry_scope": str,
    "time_range": str,
    "sections": [{"id": str, "title": str, "content": str, "source": "llm" | "template"}],
    "references": [{"title": str, "authors": str, "year": str, "venue": str}] | None,
    "generation_mode": "llm" | "template_fallback",
    "model_id": str | None,
    "generation_error": str | None,
}
```

**Artifact 映射**:
- Type: `ArtifactType.BACKGROUND_RESEARCH` (`"background_research"`)
- Title: `"{workspace_name} - 背景调研报告"`

**图设计**: 4 阶段
1. 关键词扩展 + 调研范围界定
2. 并行 LLM 生成 3 个调研章节
3. 参考文献补充 + 交叉验证
4. 综合调研报告输出

**输出语言**: 中文

---

### B2: Software Copyright 工作区 — 2 个图

#### `backend/src/agents/graphs/software_copyright/__init__.py`
```python
"""Software copyright workspace LangGraph sub-graphs."""
```

#### `backend/src/agents/graphs/software_copyright/copyright_materials.py`

**Registry**: `workspace_type="software_copyright", id="copyright_materials", handler_key="software_copyright.copyright_materials"`

**重要**: 这个功能**没有**独立的 service 函数。业务逻辑直接在 handler (`handlers/software_copyright.py`) 中的 `_build_required_materials()` 函数。你需要将这段逻辑迁移到图中。

**Handler 参数提取**:
```python
software_name = params.get("software_name") or context.workspace_name or "待确认软件名称"
version = params.get("version") or params.get("software_version") or "V1.0"
applicant_name = params.get("applicant_name") or "待确认申请主体"
completion_date = params.get("completion_date") or "待确认开发完成日期"
highlights = _normalize_list(params.get("highlights"))
target_platforms = _normalize_list(params.get("target_platforms"))
source_modules = _normalize_list(params.get("source_modules"))
```

**业务逻辑** (`_build_required_materials()`): 生成 5 项材料清单（确定性，无 LLM 调用）：
1. 软件著作权登记申请表
2. 源程序连续页
3. 软件说明书/操作手册
4. 主体与权属证明材料
5. 软件功能亮点归纳

**图设计**: 4 阶段
1. 软件信息收集（参数提取）
2. 材料清单生成（基础 + LLM 增强建议）
3. 完整性检查 + 缺失项提示
4. 结构化输出

**Artifact 映射**:
- Type: `ArtifactType.COPYRIGHT_MATERIALS` (`"copyright_materials"`)
- Title: `"{software_name} 软著申请材料清单"`

**Artifact 内容结构** (参照现有 handler 第 160-190 行):
```python
{
    "schema_version": "v1",
    "output_language": "zh",
    "document_type": "copyright_materials",
    "workspace": {"id": str, "name": str, "type": str, "discipline": str},
    "software_profile": {"software_name": str, "version": str, "applicant_name": str, ...},
    "required_materials": [{"id": str, "title": str, "status": str, "required_fields": [str], ...}],
    "review_checklist": [str],
    "next_actions": [str],
}
```

**输出语言**: 中文

---

#### `backend/src/agents/graphs/software_copyright/technical_description.py`

**Registry**: `workspace_type="software_copyright", id="technical_description", handler_key="software_copyright.technical_description"`

**Handler 参数提取**:
```python
software_name = params.get("software_name") or context.workspace_name or "待确认软件"
version = params.get("version") or params.get("software_version") or "V1.0"
core_modules = _normalize_list(params.get("core_modules"))
deployment_architecture = params.get("deployment_architecture") or "B/S架构"
database_middleware = _normalize_list(params.get("database_middleware"))
interface_protocols = _normalize_list(params.get("interface_protocols"))
highlights = _normalize_list(params.get("highlights"))
preferred_model = params.get("model_id")
```

**Service 函数**:
```python
from src.workspace_features.services import build_technical_description_payload

result = await build_technical_description_payload(
    workspace_id=workspace_id,
    workspace_name=workspace_name,
    workspace_description=workspace_description,
    software_name=software_name,
    version=version,
    core_modules=core_modules,
    deployment_architecture=deployment_architecture,
    database_middleware=database_middleware,
    interface_protocols=interface_protocols,
    highlights=highlights,
    preferred_model=preferred_model,
)
```

**Service 返回结构**:
```python
{
    "software_profile": {...},
    "sections": {
        "system_overview": {"title": str, "content": str, "source": str},
        "module_design": {"title": str, "content": str, "modules": [str], "source": str},
        "data_flow": {"title": str, "content": str, "source": str},
        "deployment_architecture": {"title": str, "content": str, "source": str},
        "security_and_permissions": {"title": str, "content": str, "source": str},
        "operation_steps": {"title": str, "content": str, "steps": [str], "source": str},
    },
    "generation_mode": "llm" | "template_fallback",
    "model_id": str | None,
    "generation_error": str | None,
    "upgrade": {"auto_upgrade": bool, "can_regenerate_with_llm": bool, "last_error": str | None},
}
```

**Artifact 映射**:
- Type: `ArtifactType.TECHNICAL_DESCRIPTION` (`"technical_description"`)
- Title: `"{workspace_name} - 技术说明书"`

**图设计**: 4 阶段
1. 现有工件加载（COPYRIGHT_MATERIALS → 提取默认值）
2. 并行 LLM 生成 6 个技术章节
3. 技术一致性验证
4. 格式规范化 + 结构化输出

**输出语言**: 中文

---

### B3: 删除 Handler 文件

删除以下 5 个文件：
```
backend/src/workspace_features/handlers/thesis.py
backend/src/workspace_features/handlers/sci.py
backend/src/workspace_features/handlers/proposal.py
backend/src/workspace_features/handlers/patent.py
backend/src/workspace_features/handlers/software_copyright.py
```

**注意**: `handlers/__init__.py` 如果存在，检查是否有导出需要清理。

### B4: 清理 `runtime.py`

**文件**: `backend/src/workspace_features/runtime.py`

移除:
- `register_feature_handler()` 装饰器和 `_HANDLERS` 字典
- `WorkspaceFeatureExecutionContext` 类
- `execute_registered_feature()` 函数
- `_execute_placeholder()` 和 `_missing_handler_mode()`

保留: 任何被 service 层或其他模块引用的工具函数。

**清理 `__init__.py`**: `backend/src/workspace_features/__init__.py` 中移除 `execute_registered_feature`、`get_workspace_feature` 等 handler 相关导出。

### B5: 更新烟测/E2E 测试

**文件**: `backend/tests/workspace_features/test_five_workspace_smoke.py`
- 验证所有 5 个工作区通过 LangGraph 执行
- 移除任何 handler-specific 断言

**文件**: `backend/tests/workspace_features/test_workspace_e2e_matrix.py`
- 更新 E2E 矩阵

**文件**: `backend/tests/task/test_thesis_handlers.py`
- 删除此文件

**文件**: `backend/tests/task/test_workspace_feature_runtime.py`
- 移除 handler 相关测试

### B6: 更新 Playbook

**文件**: `docs/architecture/workspace-ai-modification-playbook.md`

需要修改的 sections:
- Section 1: 移除 "handler fallback chain"
- Section 2 Step 4: "fallback handler is used on failure" → "LangGraph sub-graph executes the feature"
- Section 4 Step 2: 移除或重写 "Handler Implementation (Fallback Path)"
- Section 4 Step 3: 移除 "Fallback to handler must remain functional"
- Section 5: 从测试矩阵中移除 `test_thesis_handlers.py`，添加新图测试
- Section 7: 移除 "Returning inconsistent payload schemas between LangGraph and fallback handlers"
- Section 9: 更新 Quick Decision Guide

---

## 单元测试编写指南

### 测试模板

参考 `tests/agents/graphs/thesis/test_literature_management.py` 的模式：

```python
"""Tests for {workspace_type}/{feature_id} LangGraph sub-graph."""

import pytest
from src.agents.graphs.{workspace_type}.{feature_module} import (
    # 导出的辅助函数（非 async 的纯函数）
    _helper_function_1,
    _helper_function_2,
)


class TestHelperFunction1:
    def test_empty_input(self):
        result = _helper_function_1([], "topic")
        assert result["key"]["count"] == 0

    def test_normal_input(self):
        data = [{"field": "value"}, ...]
        result = _helper_function_1(data, "topic")
        assert result["key"]["count"] == len(data)


class TestHelperFunction2:
    def test_valid_json(self):
        result = _helper_function_2('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fence(self):
        result = _helper_function_2('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_returns_none(self):
        result = _helper_function_2("not json")
        assert result is None
```

### 测试要点
1. 测试**辅助函数**（纯函数），不直接测试 async 图函数
2. 不 mock LLM — 测试输入解析、输出构建、降级逻辑
3. 确保覆盖：空输入、正常输入、edge case（如 JSON 解析失败）

---

## 非协商合约（必须遵守）

1. **Feature Result Payload**: `success`, `feature_id`, `feature_name`, `workspace_type`, `handler_key`, `message`, `artifacts`, `refresh_targets`, `data`
2. **Artifact 版本化**: 应用级锁 + DB 唯一约束 `(workspace_id, type, title, version)` — 不要破坏
3. **Knowledge Service 单源**: 只用 `src/services/knowledge_service.py`，不要创建副本
4. **记忆提取非阻塞**: async fire-and-forget，失败不影响功能完成
5. **前端合约不变**: `TaskFeedbackBanner`、`WorkspaceResultPanel`、`refresh_targets` 不变

---

## 完成后验证清单

Agent 完成后必须运行：

```bash
# 图单元测试
pytest -q tests/agents/graphs/thesis
pytest -q tests/agents/graphs/sci
pytest -q tests/agents/graphs/proposal
pytest -q tests/agents/graphs/software_copyright
pytest -q tests/agents/graphs/patent

# 分发和集成测试
pytest -q tests/task/test_workspace_feature_handler.py
pytest -q tests/task/test_langgraph_dispatch.py
pytest -q tests/task/test_workspace_feature_runtime.py
pytest -q tests/task/test_workspace_feature_registry.py

# 基础设施测试
pytest -q tests/academic/services/test_artifact_versioning.py
pytest -q tests/services/test_knowledge_service.py tests/services/test_memory_compaction.py
pytest -q tests/agents/middleware/test_memory.py

# 端到端测试
pytest -q tests/workspace_features/test_five_workspace_smoke.py tests/workspace_features/test_workspace_e2e_matrix.py
```

**所有测试必须通过。** 如果某个测试因删除 handler 而失败，需要更新测试（而不是跳过）。
