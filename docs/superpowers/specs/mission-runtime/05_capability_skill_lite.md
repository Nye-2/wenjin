# 05 Capability / Skill Lite Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: runtime catalog is cleanly reduced to `mission_policies` and `worker_skills`; old catalogs, compiler, admin CRUD, and user-facing workflow grid were removed. Policy/skill changes are validated seed deployments, not live workflow editing.
Depends on: `01_workspace_agent.md`, `04_stage_acceptance_contract.md`

## Goal

Reduce capability/skill from a visible workflow and fixed agent graph into policy, examples, stage quality contracts, and tool boundaries. The model should be freer inside the loop, while the runtime strictly controls quality and write boundaries.

## Current Code Anchors

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/seed/capabilities/{workspace_type}/*.yaml` | Capability display, mission, graph template, policies, methodology | Convert to MissionPolicy + StageAcceptanceContract; remove fixed user-visible workflow |
| `backend/seed/skills/*.yaml` | Worker instruction packs | Keep as bounded worker/context resources; not user-facing products |
| `backend/src/services/mission_policy_schema.py` | Validates MissionPolicy and stage contracts | Keep catalog resolution hash-bound and fail closed |
| `backend/src/services/capability_resolver.py` | Resolves capability by workspace type/id | Replace with MissionPolicyResolver |
| `backend/src/agents/middlewares/capability_skill_preload.py` | Loads capability route cards into chat | Keep only bounded route hints for WorkspaceAgent |
| `backend/src/agents/lead_agent/v2/compiler.py` | Compiles graph_template | Delete as default execution compiler |

## Target Objects

```text
MissionPolicy
StageAcceptanceContract
ToolPolicy
ReviewPolicy
SandboxPolicy
WorkerSkillRef
ExampleRef
```

MissionPolicy answers:

- What does this task type need to accomplish?
- What minimum context is needed?
- What stages are quality-gated?
- What tools/subagents are allowed?
- What outputs require review?
- What examples define excellent work?
- What outputs are forbidden or high risk?

MissionPolicy does not answer:

- Which exact node must run first.
- Which fixed expert team must be displayed.
- Which frontend card should launch the task.
- Which old graph_template node id owns a result.

## MissionPolicy Shape

```text
schema_version: mission_policy.v1
id
workspace_type
display
routing
mission
minimum_context
stage_contract_refs[]
allowed_tool_groups[]
allowed_worker_skills[]
review_policy_ref
sandbox_policy_ref
examples[]
anti_examples[]
completion_contract
```

`routing` is only for WorkspaceAgent decision support, not frontend navigation.

## Skill Shape

Worker skill should become a bounded resource:

```text
skill_id
role_hint
instruction_ref
allowed_tools
input_contract
output_contract
quality_focus
examples
```

The runtime should pass skills by immutable version/hash reference and bounded excerpt. Do not persist giant skill prompt text into MissionRun snapshot or MissionItem. MissionRun runtime context records the resolved policy/skill/tool schema versions used by the mission.

Reasoning effort vocabulary is globally fixed to `low | medium | high | xhigh`. A StageAcceptanceContract may declare `recommended_model_effort`, but effort is not a hidden quality criterion. Increasing beyond the user's current selection requires transparent confirmation after preflight or observed no-progress; policy resolution must not silently rename, invent, or escalate effort levels.

## Admin Editing

Admin capability editing is not first priority. If kept, admin should edit only:

- visible name and description
- route hints
- minimum context
- MissionPolicy fields
- StageAcceptanceContract criteria
- allowed tool groups
- review policy
- examples/anti-examples

Admin should not edit:

- raw graph templates
- fixed team member list as product workflow
- raw worker prompts without validation
- runtime table bindings
- hidden permission escalation

## Deletions

- default capability grid in right panel
- frontend capability matcher
- graph_template as user-visible workflow
- static expert team template as default UX
- skill launcher product surface
- skill id / schema id exposure to user
- hidden compatibility between old workflow-step ids and new stages

## Migration

1. Define `mission_policy.v1` and `stage_acceptance_contract.v1`.
2. Convert existing YAML seeds for all six workspace types into MissionPolicy + stage contracts:
   - `sci`
   - `thesis`
   - `proposal`
   - `software_copyright`
   - `math_modeling`
   - `patent`
3. Remove `graph_template` from execution path; keep temporarily only in tests until migration is complete.
4. Replace `CapabilityResolver` with `MissionPolicyResolver`.
5. Update WorkspaceAgent route preload to use route hints.
6. Delete compiler paths that assume graph nodes are runtime SSOT.
7. Update docs/current after runtime cutover.

Conversion rules:

- `display` and `routing` become WorkspaceAgent route hints.
- `methodology`, `quality_gates`, and `research_evidence` become StageAcceptanceContracts.
- `team_policy` becomes allowed worker skill / reviewer role guidance, not a fixed product roster.
- `sandbox_policy`, `citation_policy`, and write/review policy become ToolPolicy / ReviewPolicy / SandboxPolicy refs.
- Hidden internal smoke/test capabilities do not become user-visible MissionPolicies.
- No policy may preserve old graph node ids as runtime ids.

## Tests

- Visible mission policy must have route hints and minimum context.
- Mission policy without required stage contracts fails validation.
- Hidden/internal policy never appears in user route hints.
- No runtime code imports `graph_template` after cutover.
- Every supported workspace type has at least one validated MissionPolicy seed.
- Worker skill raw prompt is not exposed in WorkspaceAgent route prompt.
- No frontend import or branch uses capability catalog for launcher grid.
- Old `graph_template` absence does not prevent mission start after migration.
- MissionRun records immutable refs/hashes for every resolved MissionPolicy, stage contract, worker skill, exemplar set, and tool schema.
- Policy validation accepts only `low | medium | high | xhigh` effort values.
