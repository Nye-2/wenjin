# Capability/Skill 闭环设计

> 目标：让 wenjin 的 chat → right-panel execution 全链路打通，5 个 workspace type × 全部 capability 跑出真实结果。

## Context

当前 v2 chat pipeline 已能：
- 模型可靠调 `launch_feature` 工具（参考 deer-flow 的 MANDATORY pattern）
- 创建 execution row、dispatch Celery、graph 在右侧面板渲染
- Subagent 注册流程跑通

但有数据/实现层 gap：
- 只有 `thesis` 有 5 个 capability YAML seed；sci/proposal/patent/software_copyright 全空
- 5 个 subagent (`scholar_searcher`/`web_searcher`/`clusterer`/`critical_writer`/`outliner`) 全是 stub，返回 hardcoded 假数据
- `SemanticScholarClient` 已实现但未被 subagent 调用
- 25 个 skill 定义在 Python 代码里（`workspace_features/skills.py`），admin 改 prompt 必须改代码 + 重启
- Skill 和 capability 语义混乱（实际命名为 "skill" 的记录承担了 capability 的入口职责）

## Goal

一次性达到闭环：
- 5 workspace types × 完整 capability 集（~25 个 capability）
- 所有 capability 跑真实工作流，subagent 跑真实 LLM/API
- Skill 和 capability 在数据库里，prompt/参数可在运行时修改并立即生效（无需重启）
- 接口规范化，后续扩展（加 capability/skill/搜索源/subagent）零侵入

## Architecture

5 层结构：

```
Layer 1: Chat（左侧 MiMo）
  └─ 看到所有 capability + 所有 skill 的列表
  └─ 识别用户意图 → launch_feature(feature_id, params)

Layer 2: Capability（右侧 leader agent execution = 一次 LangGraph 流程）
  └─ DB 表 `capabilities`，graph_template 定义 phases/tasks
  └─ 每个 task 声明 subagent_type + skill_id

Layer 3: Subagent（执行单元，仅 2 种）
  ├─ searcher: 调外部 API（无 LLM）
  └─ react:    MiMo ReAct loop（加载 skill 的 prompt + tools）

Layer 4: Skill（subagent 能力包）
  └─ DB 表 `capability_skills`，全局平铺
  └─ 一个 skill 可被任意 capability 引用

Layer 5: Output → ResultCard → 8 Rooms
  └─ subagent 产出走 result_card preview
  └─ 用户接受后写入 library/documents/decisions/memory
```

## Data Model

### `capabilities` 表

```python
class Capability:
    id: str                # PK 1
    workspace_type: str    # PK 2 ("thesis" | "sci" | "proposal" | "patent" | "software_copyright")
    enabled: bool
    display_name: str
    description: str             # 注入 chat agent prompt 的简短说明
    intent_description: str      # 长描述，给 chat agent 看
    trigger_phrases: JSONB       # ["调研", "找文献", ...] 用于意图匹配
    required_decisions: JSONB    # 启动前可能追问的参数
    brief_schema: JSONB          # 最小输入 JSON schema
    graph_template: JSONB        # phases → tasks 结构（含 skill_id）
    result_card_template: str
    notes: str | None
```

### `capability_skills` 表

```python
class CapabilitySkill:
    id: str (PK)                 # 全局唯一
    enabled: bool
    display_name: str
    description: str
    subagent_type: str           # "searcher" | "react"
    prompt: Text                 # subagent 加载时作为 system prompt
    allowed_tools: JSONB         # tool 白名单（仅 react 用）
    resources: JSONB             # 引用的外部 MD 路径（运行时读入拼进 prompt）
    config: JSONB                # 额外参数（max_results、output_kind 等）
```

**就这两张表，无关联表、无 version、无时间戳。**

### 数据库迁移

需要一个 alembic migration：
- 删除现有 `capabilities` 表的 `version` 列、复合主键去 version、`created_at`/`updated_at` 字段
- 删除 `capability_active_versions` 表（如果存在）
- 新建 `capability_skills` 表
- 现有 5 个 thesis capability 数据迁移保留

### 加载流程

启动时 (bootstrap-admin)：

```python
async def bootstrap_seeds():
    # Skills 表空 → seed
    if not await db.scalar(select(CapabilitySkill).limit(1)):
        for yaml_path in glob("seed/skills/*.yaml"):
            db.add(CapabilitySkill(**parse_yaml(yaml_path)))
    
    # Capabilities 表空 → seed
    if not await db.scalar(select(Capability).limit(1)):
        for yaml_path in glob("seed/capabilities/*/*.yaml"):
            db.add(Capability(**parse_yaml(yaml_path)))
    
    await db.commit()
```

运行时所有读写走 DB；YAML 仅用于首次 seed。Admin 改 prompt = 改 DB row → EventBus 广播 cache invalidate → 下次 execution 用新 prompt。

## Capability YAML Schema

```yaml
# seed/capabilities/{workspace_type}/{capability_id}.yaml
id: deep_research
workspace_type: thesis
enabled: true
display_name: 深度文献调研
description: 围绕主题做系统化文献检索和综述
intent_description: 用户希望对某个主题做学术性的深度文献调研
trigger_phrases:
  - 调研
  - 找文献
  - literature review

required_decisions:
  - key: topic_scope
    ask: "主题边界是？"
    type: string

brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string, description: 调研主题 }
    year_min: { type: integer, optional: true }

graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
            year_min: "{{year_min|default(2019)}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
                abstract: "{{item.abstract}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: write
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 文献综述"
                doc_kind: literature_review
                content: "{{output.markdown}}"

result_card_template: literature_review
notes: 适合开题阶段或选题探索
```

## Skill YAML Schema

```yaml
# seed/skills/{skill_id}.yaml
id: scholar-searcher
enabled: true
display_name: 学术文献检索员
description: 调用 Semantic Scholar 检索高质量论文

subagent_type: searcher

prompt: |
  (searcher 不调 LLM，但保留字段以便接口一致)

allowed_tools: []

resources: []

config:
  sources: [semantic_scholar]
  max_results: 30
  year_min: 2019
```

```yaml
# seed/skills/literature-reviewer.yaml
id: literature-reviewer
enabled: true
display_name: 文献综述写手
description: 把论文集合写成结构化综述

subagent_type: react

prompt: |
  你是学术综述写作专家。给定一组论文，按主题/方法/时间组织一篇综述。
  
  要求：
  - 800-1500 字
  - 引用论文用 [作者 年份] 格式
  - 标记研究空白和未来方向
  
  输出 Markdown 格式：
  # {{topic}} 文献综述
  
  ## 研究脉络
  ## 主流方法
  ## 关键论文
  ## 研究空白与未来方向

allowed_tools: []

resources: []

config:
  output_kind: document
  doc_kind: literature_review
  max_words: 1500
  user_template: |
    主题：{{topic}}
    论文列表（JSON）：
    {{papers|json}}
```

## Search Source Interface

```python
# src/services/search/base.py
class SearchSource(Protocol):
    name: str
    
    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]: ...

class SearchResult(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    doi: str | None
    url: str | None
    citations: int | None
    venue: str | None
    external_id: str
    source: str                    # 数据源 name
    raw: dict                      # 原始响应

# src/services/search/registry.py
SEARCH_SOURCES: dict[str, type[SearchSource]] = {
    "semantic_scholar": SemanticScholarSource,
}

def get_search_source(name: str) -> SearchSource: ...
```

未来加新源（arxiv/openalex/patent_cn）：写一个新 class 注册到 dict 即可。Subagent 代码不改。

## Subagent Implementation

### SearcherSubagent

```python
@subagent("searcher")
class SearcherSubagent(SubagentBase):
    async def run(self, ctx, skill):
        sources = skill.config.get("sources", ["semantic_scholar"])
        max_results = skill.config.get("max_results", 30)
        year_min = skill.config.get("year_min")
        
        query = ctx.inputs["query"]
        year_range = (year_min, datetime.now().year) if year_min else None
        
        all_results = []
        for src_name in sources:
            try:
                src = get_search_source(src_name)
                results = await src.search(query, year_range=year_range, limit=max_results)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Source {src_name} failed: {e}")
        
        deduped = dedupe_by_doi_or_title(all_results)
        
        return SubagentResult(
            outputs={"papers": [r.model_dump() for r in deduped]},
            token_usage={},
        )
```

### ReactSubagent

```python
@subagent("react")
class ReactSubagent(SubagentBase):
    async def run(self, ctx, skill):
        # 1. 拼 system prompt
        system_prompt = skill.prompt
        for resource_path in skill.resources or []:
            content = read_resource_file(resource_path)
            system_prompt += f"\n\n## Reference: {resource_path}\n{content}"
        
        # 2. 渲染 user message
        user_message = render_template(
            skill.config.get("user_template", "{{inputs|json}}"),
            inputs=ctx.inputs,
        )
        
        # 3. 加载 tools（按白名单）
        tools = [get_tool(name) for name in (skill.allowed_tools or []) if get_tool(name)]
        
        # 4. ReAct loop
        model = create_chat_model("mimo-v2.5-pro")
        agent = create_react_agent(model, tools, prompt=system_prompt)
        result = await agent.ainvoke({"messages": [HumanMessage(user_message)]})
        final_text = result["messages"][-1].content
        
        # 5. 解析 outputs（按 skill.config.output_kind）
        output_kind = skill.config.get("output_kind", "text")
        if output_kind == "document":
            outputs = {"markdown": final_text}
        elif output_kind == "json":
            outputs = json.loads(final_text)
        else:
            outputs = {"text": final_text}
        
        return SubagentResult(outputs=outputs, token_usage=extract_usage(result))
```

## Leader Agent Prompt

Chat MiMo 的 system prompt 注入两份清单：

```
<available_capabilities>
  <capability id="deep_research" workspace_type="thesis" name="深度文献调研" 
              triggers="调研,找文献" desc="围绕主题做系统化文献检索"/>
  <capability id="paper_analysis" workspace_type="thesis" .../>
  ...
</available_capabilities>

<available_skills>
  <skill id="scholar-searcher" subagent_type="searcher" desc="Semantic Scholar 检索"/>
  <skill id="literature-reviewer" subagent_type="react" desc="文献综述写作"/>
  ...
</available_skills>
```

MiMo 自己决定调哪个 capability。Skill 列表是参考信息（让模型理解系统能力边界）。

## Capability/Skill 全量清单

### Skills（~9 个核心能力包）

| skill_id              | subagent_type | description                              |
|-----------------------|---------------|------------------------------------------|
| scholar-searcher      | searcher      | 调 Semantic Scholar 搜学术论文          |
| prior-art-searcher    | searcher      | 调专利数据库（接口预留）                |
| literature-reviewer   | react         | 论文集 → 结构化综述                      |
| paper-analyst         | react         | 单篇论文 → 方法/实验/结论拆解            |
| framework-designer    | react         | 选题 → 摘要+章节框架                     |
| section-writer        | react         | 大纲+证据 → 章节草稿                     |
| figure-designer       | react         | 概念/数据 → 图表说明 + Mermaid           |
| peer-reviewer         | react         | 论文草稿 → 审稿意见 + 修订动作           |
| journal-recommender   | react         | 论文画像 → 候选期刊推荐                  |

### Capabilities（25 个，5 workspace × 5 typical）

**thesis**（毕业论文）：
- `deep_research` — 深度调研
- `literature_management` — 文献管理（用 scholar-searcher 抓元数据）
- `opening_research` — 开题调研
- `outline_generate` — 大纲设计
- `section_write` — 章节撰写
- `section_revise` — 章节修订
- `figure_generate` — 图表设计

**sci**（SCI 论文）：
- `literature_search` — 文献检索
- `paper_analysis` — 论文分析
- `literature_review` — 文献综述
- `framework_outline` — 框架大纲
- `section_writing` — 章节写作
- `figure_generation` — 图表设计
- `peer_review` — 同行评审
- `journal_recommend` — 期刊推荐

**proposal**（申报书）：
- `proposal_outline` — 申报书大纲
- `background_research` — 背景调研
- `experiment_design` — 实验设计
- `figure_generation` — 图表设计

**patent**（专利）：
- `patent_outline` — 专利框架
- `prior_art_search` — 现有技术检索
- `figure_generation` — 图表设计

**software_copyright**（软著）：
- `copyright_materials` — 著作权材料生成
- `technical_description` — 技术说明书
- `figure_generation` — 图表设计

每个 capability 都有自己的 YAML seed，定义具体 graph_template（用哪些 skill、phases 怎么编排）。

## Cache & Invalidation

```python
class CapabilityResolver:
    _cache: dict[tuple[str, str], Capability] = {}
    async def resolve(self, id, workspace_type) -> Capability
    async def list_for_workspace_type(self, ws) -> list[Capability]
    async def _on_invalidate(self, event):
        self._cache.pop((event["id"], event["workspace_type"]), None)

class SkillResolver:
    _cache: dict[str, CapabilitySkill] = {}
    async def resolve(self, skill_id) -> CapabilitySkill
    async def list_all_enabled(self) -> list[CapabilitySkill]   # 注入 leader prompt
    async def _on_invalidate(self, event):
        self._cache.pop(event["skill_id"], None)
```

Admin 修改后通过 EventBus 广播 `capability.updated` / `skill.updated` → 所有 worker 进程缓存失效。

## Admin API（后续扩展，本期不实现）

```
GET    /api/capabilities                  # 全列表
GET    /api/capabilities/{ws}/{id}        # 详情
PUT    /api/capabilities/{ws}/{id}        # 改字段（含 graph_template / prompt 描述）
POST   /api/capabilities/reload           # 全量重载（不常用）

GET    /api/skills
GET    /api/skills/{id}
PUT    /api/skills/{id}                   # 改 prompt / tools / config
POST   /api/skills/reload
```

本期只实现 DB 层 + Resolver。Admin UI 留给后续。

## Output → Workspace Rooms

复用现有 result_card 流程：

```
SubagentResult.outputs[]
  → ExecutionCommitService 准备 staging
  → ResultCard 推送到前端（带 checkbox，默认全选）
  → 用户点"全部接受"
  → ExecutionCommitService.commit() 写入对应 room:
      - kind=library_item   → reference_library
      - kind=document       → documents
      - kind=memory_fact    → memory
      - kind=decision       → decisions
      - kind=task           → tasks
```

此流程已存在，本期不改。

## Implementation Order

虽然用户选了 big-bang 一次到底，实施按依赖顺序分单元做（每个单元一个 task）：

1. **DB migration**：删 version/timestamp 列、建 `capability_skills` 表
2. **Skill loader**：`SkillResolver` + `SkillLoader.load_seeds_if_empty()`
3. **Search source 抽象**：`SearchSource` 接口 + `SemanticScholarSource` 实现 + registry
4. **SearcherSubagent**：替换 stub，调 search registry
5. **ReactSubagent**：替换 stubs（critical_writer/outliner/clusterer/web_searcher 改为统一 react），加载 skill prompt + tools
6. **Subagent registry 重构**：保留 2 种类型 `searcher`/`react`，删除其他类型
7. **Leader agent prompt 重写**：列出所有 capabilities + skills（替换 `_render_workspace_available_skills`）
8. **9 个 Skill YAML seed**：scholar-searcher / literature-reviewer / paper-analyst / framework-designer / section-writer / figure-designer / peer-reviewer / journal-recommender / prior-art-searcher
9. **25 个 Capability YAML seed**：分 5 workspace × 5-7 capability
10. **Bootstrap-admin 升级**：自动 seed capabilities + skills
11. **端到端测试**：浏览器实测每个 workspace type 至少一个 capability 跑通

## Non-Goals（本期不做）

- Admin UI（只做 DB + Resolver，留 PUT API 留待后续）
- 多源搜索的具体新源（仅 Semantic Scholar；arxiv/openalex/patent_cn 接口预留）
- 用户登录态以外的权限模型
- Capability/Skill 的 version 回滚机制
- 跨 workspace_type 复用 capability（每个 workspace_type 独立）

## Risks

1. **MiMo react agent 跑长任务可能不稳**：长 prompt + 多论文 JSON 注入 → token 接近上限。缓解：skill config 控制 `max_words`，分阶段 vs 单阶段。
2. **Semantic Scholar rate limit**：免费 tier 有 100 req/5min。缓解：`SEMANTIC_SCHOLAR_RATE_LIMIT_DELAY` 已配置；搜索结果缓存（后续）。
3. **YAML 重新 seed 时机**：bootstrap-admin 只在表空时 seed。手动重置必须先清表。可能踩坑。缓解：明确 doc，加 admin endpoint。
4. **Stub subagent 删除可能破坏其它代码**：`web_searcher`/`clusterer`/`outliner`/`critical_writer` 五个类被 capability YAML 引用，要么改 YAML 改 subagent_type，要么保留 stub 并加 deprecation。**决定：改 YAML，统一 subagent_type 为 `searcher`/`react`。删除旧 stub class。**

## Acceptance Criteria

- thesis workspace 用 chat "帮我调研 X" → 右侧 graph 渲染 → 真实 Semantic Scholar 论文进 library room → 真实综述 markdown 进 documents room
- sci workspace 用 chat "帮我分析这篇论文 X" → 真实分析结果进 documents
- 其它 3 个 workspace type 至少 1 个 capability 跑通
- Admin 直接 SQL `UPDATE capability_skills SET prompt='...' WHERE id='literature-reviewer'` → 下次 execution 用新 prompt
- 不重启服务、不重新 build 镜像，只改 DB row
