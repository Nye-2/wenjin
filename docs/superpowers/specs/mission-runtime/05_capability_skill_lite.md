# 05 Capability / Skill Lite Spec

Status: Implemented
Updated: 2026-07-15

Implementation outcome: runtime catalog is cleanly reduced to `mission_policies` and `worker_skills`; old catalogs, compiler, admin CRUD, and user-facing workflow grid were removed. Policy/skill changes are validated seed deployments, not live workflow editing.
Depends on: `01_workspace_agent.md`, `04_stage_acceptance_contract.md`

## Goal

Reduce capability/skill from a visible workflow and fixed agent graph into policy, examples, stage quality contracts, and tool boundaries. The model should be freer inside the loop, while the runtime strictly controls quality and write boundaries.

## Current Code Anchors

| Current file | Responsibility |
|---|---|
| `backend/src/contracts/mission_policy.py` | Strict MissionPolicy, CompletionTarget, review policy, and WorkerSkill contracts |
| `backend/src/contracts/stage_acceptance.py` | Stage families, prerequisites, per-item instantiation, and quality criteria |
| `backend/src/services/mission_policy_loader.py` | Hash-bound policy/skill seed loading |
| `backend/src/services/mission_policy_schema.py` | Cross-contract validation and fail-closed catalog checks |
| `backend/src/agents/middlewares/mission_policy_hints.py` | Bounded route hints for WorkspaceAgent; no launcher catalog |
| `backend/seed/mission_policies/*` | Six workspace policy and stage-contract deployments |
| `backend/seed/skills/*.yaml` | Compact optional worker guidance; never product workflow definitions |

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

`completion_contract` selects an outcome, not a generic list of stages:

```text
default_target
targets[target_id]
  stage_ids[]
  terminal_output_kinds[]
allow_safe_partial_outputs
```

The chosen target atomically binds the required stage families and final semantic outputs. Per-item stage families are expanded from server-owned `stage_item_counts`, which MissionRuntime pins in the same transaction as the passing understanding-stage quality action. `quality_item_counts` must exactly cover the workloads unlocked by that pass. The browser and later plan actions cannot set or change cardinality.

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

## Cutover Result

All six workspace types (`sci`, `thesis`, `proposal`, `software_copyright`, `math_modeling`, and `patent`) now load validated MissionPolicy plus StageAcceptance contracts. `graph_template`, CapabilityResolver, fixed-team compiler paths, launcher grids, and compatibility mappings are absent from the runtime. Development data uses drop/reseed; no old capability record is translated on read.

Conversion rules:

- `display` and `routing` become WorkspaceAgent route hints.
- `methodology`, `quality_gates`, and `research_evidence` become StageAcceptanceContracts.
- `team_policy` becomes allowed worker guidance and optional diagnostic skills, not a fixed product roster or mandatory critic role.
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
- Mission start and completion work without any capability graph or node id.
- MissionRun records immutable refs/hashes for every resolved MissionPolicy, stage contract, worker skill, exemplar set, and tool schema.
- Policy validation accepts only `low | medium | high | xhigh` effort values.
- Each completion target binds unique stage ids and terminal output kinds; an unknown target fails closed.
- Per-item count sources are policy-defined, server-owned, immutable after pinning, and absent from the public start contract.
