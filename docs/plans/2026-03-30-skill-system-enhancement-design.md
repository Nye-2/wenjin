# Skill System Enhancement Design

**Date:** 2026-03-30
**Status:** Approved
**Goal:** Unify the skill data source (backend API driven), ensure every feature has a skill with guidance_prompt, and add new quality-enhancing skills that leverage existing backend capabilities.

## Core Architecture

```
Feature (执行层)                    Skill (交互层)
├── 定义在 registry.py              ├── 定义在 chat_skill_catalog.py
├── 执行引擎 + stages               ├── guidance_prompt (LLM 引导)
├── 参数 schema                     ├── follow_up_skills (推荐下一步)
├── agent / handler_key             ├── UI 元数据 (icon, color, name)
└── credit_cost                     └── 映射 → feature_id + defaults
```

**Key Principle:** Skill = Feature 的对话入口。每个 Feature 至少有一个 Skill。Skill 不执行任何逻辑，只负责引导和路由。

## 1. Enhanced Skill Data Model

```python
@dataclass(frozen=True, slots=True)
class WorkspaceChatSkillDefinition:
    id: str                                      # "deep-research"
    name: str                                    # "深度调研"
    description: str                             # 功能描述
    feature_id: str                              # 关联的 feature
    defaults: tuple[tuple[str, Any], ...] = ()   # 默认参数
    icon: str = "search"                         # lucide icon 名
    color: str = "navy"                          # 色调 (navy/teal/cyan/brass/slate)
    guidance_prompt: str = ""                    # LLM 引导 prompt
    follow_up_skills: tuple[str, ...] = ()       # 推荐后续 skill id

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "featureId": self.feature_id,
            "icon": self.icon,
            "color": self.color,
            "guidancePrompt": self.guidance_prompt,
            "followUpSkills": list(self.follow_up_skills),
        }
```

## 2. Complete Skill Registry

### Thesis Skills (7)

| Skill ID | Name | Feature | Icon | Color | Guidance |
|---|---|---|---|---|---|
| deep-research | 深度调研 | deep_research | search | navy | 引导明确调研主题、关键词、已知文献 |
| literature-manager | 文献管理 | literature_management | book-open | teal | 询问整理范围和分类方式 |
| literature-reviewer | 开题调研 | opening_research | file-text | cyan | 了解研究方向和导师要求 |
| framework-designer | 大纲设计 | thesis_writing (outline) | list | navy | 确认论文题目和研究内容 |
| fullpaper-writer | 论文撰写 | thesis_writing (write) | pen | teal | 确认写全文还是单章节 |
| figure-designer | 图表设计 | figure_generation | image | brass | 询问概念和图表类型 |
| doc-compiler | 编译导出 | compile_export | package | slate | 确认编译范围和格式 |

### SCI Skills (7)

| Skill ID | Name | Feature | Icon | Color | Guidance |
|---|---|---|---|---|---|
| deep-research | 文献检索 | literature_search | search | navy | 引导检索主题和范围 |
| paper-analyst | 论文分析 | paper_analysis | microscope | cyan | 询问论文和分析重点 |
| section-writer | 章节写作 | writing | pen | teal | 询问章节主题和要求 |
| literature-reviewer | 文献综述 | literature_review | book-open | cyan | 了解综述主题和范围 |
| framework-designer | 框架大纲 | framework_outline | list | navy | 询问创新点和章节预期 |
| peer-reviewer | 同行评审 | peer_review | shield-check | brass | 确认要评审的内容 |
| journal-recommender | 期刊推荐 | journal_recommend | compass | teal | 了解主题和目标影响因子 |

### Proposal Skills (3)

| Skill ID | Name | Feature | Icon | Color |
|---|---|---|---|---|
| proposal-writer | 计划书撰写 | proposal_outline | file-text | navy |
| background-scout | 背景调研 | background_research | search | teal |
| experiment-designer | 实验设计 | experiment_design | flask-conical | cyan |

### Software Copyright Skills (2)

| Skill ID | Name | Feature | Icon | Color |
|---|---|---|---|---|
| copyright-writer | 著作权材料 | copyright_materials | file-text | navy |
| tech-doc-writer | 技术文档 | technical_description | code | teal |

### Patent Skills (2)

| Skill ID | Name | Feature | Icon | Color |
|---|---|---|---|---|
| patent-drafter | 专利撰写 | patent_outline | lightbulb | navy |
| prior-art-scout | 现有技术检索 | prior_art_search | search | brass |

## 3. New Skill API

```
GET /api/workspaces/{workspace_id}/skills
```

**Implementation:** New router `backend/src/gateway/routers/skills.py`

Returns all skills for the workspace type with full UI metadata. Frontend no longer maintains any skill definitions.

## 4. guidance_prompt Integration

In `apply_prompt_template` (agent.py), when `selected_skill` is set:

```python
# Current:
"The user selected `{selected_skill}` for this turn."

# New:
skill_def = get_skill_by_id(workspace_type, selected_skill)
if skill_def and skill_def.guidance_prompt:
    prompt += f"\nThe user selected `{selected_skill}` for this turn."
    prompt += f"\n引导要求：{skill_def.guidance_prompt}"
```

## 5. Frontend Cleanup

**Delete:** `frontend/lib/workspace-chat-skills.ts`

**Simplify:** `frontend/lib/workspace-feature-routes.ts`
- Remove `workspaceFeatureSkillMap` hardcoded mapping
- `getWorkspaceFeatureChatRoute` no longer resolves skill — only passes feature param

**Simplify:** `frontend/lib/workspace-chat-entry.ts`
- Remove `featureEntryInstructions` (migrated to backend guidance_prompt)

**Add:** Skills data in features store
- `fetchSkills(workspaceId)` calls new API
- SkillSelector component reads from store

**Modify:** `frontend/app/(workbench)/workspaces/[id]/layout.tsx`
- Call `fetchSkills` alongside `fetchFeatures`

## 6. Files to Modify

### Backend
| File | Change |
|---|---|
| `backend/src/agents/lead_agent/chat_skill_catalog.py` | Enhanced dataclass, complete skill definitions with guidance_prompts |
| `backend/src/gateway/routers/skills.py` | **New file** — Skills API endpoint |
| `backend/src/agents/lead_agent/agent.py` | Inject guidance_prompt into system prompt |
| `backend/src/gateway/app.py` or router registration | Register new skills router |

### Frontend
| File | Change |
|---|---|
| `frontend/lib/workspace-chat-skills.ts` | **Delete** |
| `frontend/lib/workspace-feature-routes.ts` | Remove skill mapping, simplify |
| `frontend/lib/workspace-chat-entry.ts` | Remove featureEntryInstructions |
| `frontend/stores/features.ts` | Add skills state + fetchSkills |
| `frontend/app/(workbench)/workspaces/[id]/layout.tsx` | Fetch skills on mount |
| `frontend/lib/api/index.ts` or similar | Add skills API call |
| Chat SkillSelector component | Read from store instead of import |
