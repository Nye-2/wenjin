# Skill System Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify skill definitions in the backend, expose via API, and remove frontend hardcoded skill data. Every feature gets a skill with guidance_prompt.

**Architecture:** Backend defines all skills in `chat_skill_catalog.py` with enhanced dataclass. New `/api/workspaces/{id}/skills` endpoint serves them. Frontend fetches from API, deletes hardcoded definitions.

**Tech Stack:** Python/FastAPI (backend), TypeScript/Next.js/Zustand (frontend)

---

### Task 1: Enhance backend skill dataclass and write complete skill definitions

**Files:**
- Modify: `backend/src/agents/lead_agent/chat_skill_catalog.py`

**Step 1: Replace the entire file with enhanced dataclass + complete skill registry**

The enhanced `WorkspaceChatSkillDefinition` adds: `name`, `icon`, `color`, `guidance_prompt`, `follow_up_skills`, `to_api_dict()`.

Complete skill definitions for all 5 workspace types (21 skills total), each with a Chinese `guidance_prompt` that tells the LLM how to guide the user through conversational parameter collection.

Also update `list_workspace_chat_skills()` to return the enhanced objects, and update `SKILL_TO_FEATURE` mapping generation.

**Step 2: Commit**
```bash
git add backend/src/agents/lead_agent/chat_skill_catalog.py
git commit -m "feat: enhance skill dataclass with guidance_prompt, complete coverage for all features"
```

---

### Task 2: Create skills API endpoint

**Files:**
- Create: `backend/src/gateway/routers/skills.py`
- Modify: `backend/src/gateway/app.py` (add router registration)

**Step 1: Create the skills router**

Model after `features.py` pattern:
```python
# GET /api/workspaces/{workspace_id}/skills
# Returns list of skills for the workspace type
```

Uses `WorkspaceService` to get workspace type, then `list_workspace_chat_skills(type)` to get skills, serializes via `to_api_dict()`.

**Step 2: Register router in app.py**

Add import and `app.include_router(skills.router, prefix="/api", tags=["skills"])`.

**Step 3: Commit**
```bash
git add backend/src/gateway/routers/skills.py backend/src/gateway/app.py
git commit -m "feat: add skills API endpoint /api/workspaces/{id}/skills"
```

---

### Task 3: Inject guidance_prompt into system prompt

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`

**Step 1: Update the skill injection section in `apply_prompt_template`**

Find the section that handles `selected_skill` (around line 238-247). Replace with:
```python
if selected_skill:
    from src.agents.lead_agent.chat_skill_catalog import get_skill_by_id
    skill_def = get_skill_by_id(workspace_type, selected_skill)
    base_prompt += "\n\n## Preferred Skill"
    base_prompt += f"\nThe user selected `{selected_skill}` for this turn."
    if skill_def and skill_def.guidance_prompt:
        base_prompt += f"\n\n{skill_def.guidance_prompt}"
    else:
        base_prompt += "\nUse it as the default approach unless the request clearly requires a different toolchain."
```

Also add `get_skill_by_id()` function to `chat_skill_catalog.py` if not already present.

**Step 2: Commit**
```bash
git add backend/src/agents/lead_agent/agent.py backend/src/agents/lead_agent/chat_skill_catalog.py
git commit -m "feat: inject skill guidance_prompt into system prompt"
```

---

### Task 4: Add skills to frontend features store and API

**Files:**
- Modify: `frontend/lib/api/workspace.ts` (add getWorkspaceSkills)
- Modify: `frontend/lib/api/types.ts` (add WorkspaceChatSkill type)
- Modify: `frontend/stores/features.ts` (add skills state)

**Step 1: Add TypeScript type**
```typescript
// In types.ts
export interface WorkspaceChatSkill {
  id: string;
  name: string;
  description: string;
  featureId: string;
  icon: string;
  color: string;
  guidancePrompt: string;
  followUpSkills: string[];
}
```

**Step 2: Add API function**
```typescript
// In workspace.ts
export async function getWorkspaceSkills(workspaceId: string): Promise<{ skills: WorkspaceChatSkill[] }> {
  const response = await api.get(`/workspaces/${workspaceId}/skills`);
  return response.data;
}
```

**Step 3: Enhance features store**
```typescript
// Add to FeaturesState:
skills: WorkspaceChatSkill[];
fetchSkills: (workspaceId: string) => Promise<void>;
getSkillById: (skillId: string) => WorkspaceChatSkill | undefined;
clearSkills: () => void;
```

**Step 4: Commit**
```bash
git add frontend/lib/api/workspace.ts frontend/lib/api/types.ts frontend/stores/features.ts
git commit -m "feat: add skills state to features store with API fetching"
```

---

### Task 5: Update SkillSelector to use store data

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/SkillSelector.tsx`

**Step 1: Replace import from workspace-chat-skills with store**

Change from:
```typescript
import { getWorkspaceChatSkills } from "@/lib/workspace-chat-skills";
```
To:
```typescript
import { useFeaturesStore } from "@/stores/features";
```

Use `useFeaturesStore((state) => state.skills)` instead of `getWorkspaceChatSkills(workspaceType)`.

Update the rendering to use the new `WorkspaceChatSkill` type (icon as string → resolve to lucide icon component).

**Step 2: Commit**
```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/SkillSelector.tsx
git commit -m "feat: SkillSelector reads from store instead of hardcoded definitions"
```

---

### Task 6: Update ChatPanel and related components

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceChatHeader.tsx`
- Modify: `frontend/components/workspace/AgentStatusBar.tsx`

**Step 1: ChatPanel — replace skill validation**

Remove import of `getWorkspaceChatSkills`. Use store skills for validation.

**Step 2: WorkspaceChatHeader — use store for skill label**

**Step 3: AgentStatusBar — replace `formatWorkspaceChatSkillLabel`**

Use store's `getSkillById` to get skill name instead of the deleted helper.

**Step 4: Commit**
```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/ChatPanel.tsx \
  frontend/app/\(workbench\)/workspaces/\[id\]/components/WorkspaceChatHeader.tsx \
  frontend/components/workspace/AgentStatusBar.tsx
git commit -m "feat: update chat components to use store-based skill data"
```

---

### Task 7: Simplify frontend route and entry files, delete old skill file

**Files:**
- Delete: `frontend/lib/workspace-chat-skills.ts`
- Modify: `frontend/lib/workspace-feature-routes.ts`
- Modify: `frontend/lib/workspace-chat-entry.ts`

**Step 1: Delete workspace-chat-skills.ts**

**Step 2: Simplify workspace-feature-routes.ts**
- Remove `workspaceFeatureSkillMap`
- Remove `resolveWorkspaceFeatureSkillId`
- `getWorkspaceFeatureChatRoute` no longer appends `skill` param — just passes `feature`

**Step 3: Simplify workspace-chat-entry.ts**
- Remove `featureEntryInstructions` (now in backend guidance_prompt)

**Step 4: Commit**
```bash
git add -u frontend/lib/
git commit -m "feat: remove hardcoded skill definitions, simplify route and entry modules"
```

---

### Task 8: Update layout to fetch skills

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/layout.tsx`

**Step 1: Add fetchSkills call alongside fetchFeatures**
```typescript
const { fetchSkills, clearSkills } = useFeaturesStore();
// In useEffect:
void fetchSkills(workspaceId);
// In cleanup:
clearSkills();
```

**Step 2: Commit**
```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/layout.tsx
git commit -m "feat: fetch skills on workspace mount"
```

---

### Task 9: TypeScript check and build verification

**Step 1:** `cd frontend && npx tsc --noEmit`
**Step 2:** `cd frontend && npx next build`
**Step 3:** Fix any errors
**Step 4:** Final commit if needed
