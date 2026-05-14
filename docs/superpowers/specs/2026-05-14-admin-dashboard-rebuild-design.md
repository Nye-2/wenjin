# Admin Dashboard Rebuild — Design Spec

**Date**: 2026-05-14
**Status**: Approved for planning
**Scope**: Capability/Skill schema cleanup + admin schema management + credit grant automation + analytics

---

## 1. Context

The wenjin admin dashboard currently exists at [frontend/app/dashboard/admin/page.tsx](../../frontend/app/dashboard/admin/page.tsx) as a single 1869-line page covering: user list + role/status toggle, single-user credit grant/deduct, credit ledger, admin log, MCP server config, release gate, token usage observability.

Three needs drove this redesign:

1. **Schema management** for capability/skill/feature — these subsystems exist but admin can only edit by hand-editing seed YAML or running raw SQL.
2. **Credit grant automation** — current single-user dialog doesn't cover registration / referral / periodic / redeem-code scenarios.
3. **Analytics panels** — only flat number cards exist today; no trend / breakdown / distribution charts.

A pre-design audit also revealed substantial **technical debt** from incomplete v1 → v2 migrations. This spec folds the debt cleanup in so the admin layer sits on a coherent backend.

## 2. Current State Audit

### 2.1 Three subsystems — alive vs dead

| System | Source | Concept | v2 alive? |
|--------|--------|---------|-----------|
| **Capability** | DB `capabilities` table + 25 seed YAML at `backend/seed/capabilities/{workspace_type}/*.yaml` (5 workspace types × 3-8 each) | Per-workspace-type executable workflow template (graph_template, required_decisions, trigger_phrases, brief_schema) | ✅ Alive — lead_agent v2 compiler → CapabilityResolver → LangGraph execution |
| **CapabilitySkill** | DB `capability_skills` table + 9 seed YAML at `backend/seed/skills/*.yaml` | Reusable subagent instruction pack (prompt + tools + resources + config), referenced by `skill_id` from capability graph_template | ✅ Alive — `capability_skill_preload` middleware injects into task_spec at compile time |
| **WorkspaceFeature** | Hardcoded in `backend/src/workspace_features/registry.py` (no DB table) | Frontend feature catalog UI metadata only (id, icon, color, stages, follow_up_prompt) | ⚠️ Half-alive — chat_agent exposes it as `list_workspace_features_tool`, but **actual execution routes through Capability, not WorkspaceFeature** |

### 2.2 Confirmed dead code

| Path | Status | Evidence |
|------|--------|----------|
| [backend/src/agents/feature_leader/](../../backend/src/agents/feature_leader/) (graph_registry / runtime / workflow) | 100% dead | Grep for `FeatureLeaderRuntime\|execute_feature_graph\|get_feature_leader_runtime` outside the module returns zero hits |
| [backend/src/agents/graphs/](../../backend/src/agents/graphs/) (~20 v1 feature graph files across 5 workspace types) | 100% dead | All registered via `@register_feature_graph` to the dead graph_registry; replaced by capability YAML `graph_template` |
| `backend/src/workspace_features/__init__.py:4` comment `"All features now route through FeatureLeaderRuntime"` | Misleading lie | Actual routing: chat_agent → launch_feature → CapabilityResolver |
| `backend/src/agents/lead_agent/*.pyc` cache files | Cache residue from deleted v1 sources | Only `__init__.py` remains as `.py`; 7 `.pyc` files cached |
| `frontend/lib/execution-presenters.ts` + its test file | 100% dead | Exports `buildExecutionPanelSession` / `buildExecutionCurrentTask` consumed only by its own test; replaced by v2 LiveWorkflowPanel + ExecutionCardList |
| `capabilities.result_card_template` column + 25 YAML field | Vestigial, never consumed | Frontend ResultCard renders by `output.kind`, not template name; no Python code branches on this value |

### 2.3 Capability ↔ WorkspaceFeature fragile coupling

- Both are per-workspace-type, both have `id` + display info
- `feature.id` must equal `capability.id`, but enforced by convention only — no FK, no validation
- Adding a capability YAML without registry.py entry → frontend has no entry point
- Adding registry.py entry without capability YAML → frontend can click, backend runs empty

### 2.4 Migration history is clean

Migrations 041 → 042 → 043 → 044 evolved the capability schema cleanly. The mess is entirely in Python code (dead modules, stale comments, vestigial fields), not in DB schema.

## 3. Decisions

| Topic | Decision |
|-------|----------|
| Subsystems to keep | Capability + CapabilitySkill only |
| Subsystems to delete | WorkspaceFeature + feature_leader + agents/graphs + execution-presenters frontend file |
| UI metadata target | Merge into Capability as new `ui_meta` JSONB column |
| `result_card_template` field | **Drop entirely** (vestigial, never consumed) |
| Capability/Skill editor form | Pure YAML editor (Monaco), shape-identical to seed files |
| Save-time validation | YAML syntax + Pydantic schema + cross-ref check (`skill_id` exists, `subagent_type` in v2 registry). No dry-run execution. |
| Seed YAML ↔ DB relationship | **DB is SSOT**; seed bootstraps first start; admin provides import / export buttons (manual trigger, not auto-sync) |
| Credit grant enhancements | Auto-grant rules (registration / referral / periodic) + redeem-code generation |
| Analytics scope | 4 panels: user growth, capability hotness, credits/token trends, workspace/task distribution |
| Admin information architecture | Left sidebar + sub-routes (`/dashboard/admin/{users,credits,...}`) |
| Capability runtime hot-reload | EventBus `capability.invalidated` published on save; CapabilityResolver subscribes and invalidates cache |
| Capability version history | Not implemented — recovery via git seed YAML or AdminLog sha256+diff fields |
| Credit rule deletion | Hard delete + AdminLog audit |
| Redeem-code deletion | Soft delete (`enabled=false`) — preserve historical traceability for printed codes |
| Chart library | Recharts |
| DAU definition | Distinct users with at least one `message` row that day |
| Retention matrix size | 6 × 6 (weekly cohorts × week offsets) |
| Failed-task error clustering | `LEFT(last_error, 80)` literal-prefix bucketing, no regex/ML |
| User-side referral signup UI | **Out of scope** (separate PR), but admin spec covers rule config + backend triggers |

## 4. Design

### 4.1 Cleanup scope

#### To delete

```
backend/src/agents/feature_leader/                  # whole dir
backend/src/agents/graphs/                          # whole dir
backend/src/workspace_features/                     # whole dir
backend/src/agents/lead_agent/*.pyc                 # cache residue
frontend/lib/execution-presenters.ts                # whole file
frontend/tests/unit/lib/execution-presenters.test.ts
docs/product/workspace-feature-catalog.md
docs/product/frontend-feature-plugin-contract.md
```

#### To modify

- `backend/src/agents/chat_agent/agent.py` — replace `list_workspace_features_tool` with `list_capabilities_tool` (reads from `/capabilities` API)
- `backend/src/gateway/routers/workspaces.py` — delete `GET /workspaces/{id}/features` endpoint and `WorkspaceFeaturesResponse`
- `backend/src/database/models/capability.py` — add `ui_meta` field, drop `result_card_template` field
- `backend/src/services/capability_loader.py` — add `ui_meta`, drop `result_card_template`
- `backend/src/gateway/routers/capabilities.py` — serialize with `ui_meta`; replace `_NoOpEventBus` with real `EventBus(redis_client.client)`
- 25 capability seed YAMLs — add `ui_meta` block, remove `result_card_template` line
- Frontend types `WorkspaceFeature` — rename to `Capability`, drop fields `agent` / `agentLabel` / `panel`
- 5 frontend production files using `WorkspaceFeature` type — update type imports and field access

#### Migrations

```
049_capability_add_ui_meta.py            # Add ui_meta JSONB NOT NULL DEFAULT '{}' to capabilities
050_capability_drop_result_card_template.py
```

### 4.2 Schema changes

#### Capability ORM additions

```python
ui_meta: Mapped[dict[str, Any]] = mapped_column(
    JSONB, nullable=False, default=dict, server_default="{}"
)
```

#### `ui_meta` Pydantic schema

```python
class UIMetaStage(BaseModel):
    id: str
    label: str

class UIMetaModel(BaseModel):
    icon: str                             # lucide icon name
    color: str                            # tailwind color name
    order: int = 0                        # display order within workspace_type catalog
    stages: list[UIMetaStage] = []        # progress hint chips
    follow_up_prompt: str | None = None   # suggested next prompt after completion
```

#### Pydantic CapabilityYamlModel (full)

```python
class RequiredDecisionModel(BaseModel):
    key: str
    ask: str
    type: Literal["string", "number", "boolean"]

class CapabilityYamlModel(BaseModel):
    id: str
    workspace_type: str
    enabled: bool = True
    display_name: str
    description: str = ""
    intent_description: str
    trigger_phrases: list[str] = []
    required_decisions: list[RequiredDecisionModel] = []
    brief_schema: dict[str, Any]
    graph_template: GraphTemplateModel        # nested phases / tasks
    notes: str | None = None
    ui_meta: UIMetaModel
```

`graph_template` Pydantic model validates phase/task structure but doesn't validate skill_id / subagent_type — those are cross-reference checks done in the service layer (require DB / registry lookup).

#### API changes

| Path | Before | After |
|------|--------|-------|
| `GET /workspaces/{id}/features` | Returns WorkspaceFeaturesResponse | **Deleted** |
| `GET /capabilities?workspace_type=X` | Returns capability list | Same, but serialization **includes `ui_meta`** |

### 4.3 Admin information architecture

#### Routes

```
/dashboard/admin                          Overview (summary cards + analytics entry cards)
/dashboard/admin/users                    User list + role/status + credit dialog
/dashboard/admin/credits                  Credit transaction ledger
/dashboard/admin/credits/rules            Auto-grant rule list
/dashboard/admin/credits/redeem-codes     Redeem-code list + batch generation
/dashboard/admin/capabilities             Capability list (grouped by workspace_type)
/dashboard/admin/capabilities/[id]        Capability YAML editor
/dashboard/admin/skills                   CapabilitySkill list
/dashboard/admin/skills/[id]              CapabilitySkill YAML editor
/dashboard/admin/analytics                4-panel analytics view
/dashboard/admin/mcp                      MCP server config (migrated)
/dashboard/admin/release-gate             Release gate runner (migrated)
/dashboard/admin/logs                     Admin operation logs (migrated)
```

#### Sidebar menu

```
管理后台
─────────────
📊 概览
👥 用户管理
💰 积分中心
   ├ 流水
   ├ 发放规则
   └ 兑换码
🧩 Capability
🛠 Skill
📈 数据分析
─────────────
🔌 MCP 配置
🛡 发布门禁
📝 操作日志
```

Only "积分中心" has a two-level submenu (3 children). All other entries are top-level. Two visual groups separated by a divider: business (top) vs system (bottom).

#### File structure

```
frontend/app/dashboard/admin/
├── layout.tsx                          # auth + sidebar + outlet (new)
├── page.tsx                            # overview (slimmed from 1869 lines to ~200)
├── components/
│   ├── AdminSidebar.tsx                # nav menu, active-route highlight, collapsible
│   ├── AdminPageHeader.tsx             # per-page title + refresh button
│   └── CreditAdjustDialog.tsx          # shared grant/deduct dialog (extracted)
├── hooks/
│   └── use-admin-auth.ts               # extracted auth guard
├── users/page.tsx                      # from current page.tsx lines 1211-1465
├── credits/
│   ├── page.tsx                        # from current page.tsx lines 1467-1638
│   ├── rules/page.tsx                  # new
│   └── redeem-codes/page.tsx           # new
├── capabilities/{page.tsx,[id]/page.tsx}
├── skills/{page.tsx,[id]/page.tsx}
├── analytics/page.tsx
├── mcp/page.tsx                        # from current page.tsx lines 1043-1209
├── release-gate/page.tsx               # from current page.tsx lines 786-1041
└── logs/page.tsx                       # from current page.tsx lines 1640-1799
```

#### Common behavior

- `layout.tsx` runs `useAdminAuth()` — non-admin redirects to `/dashboard/me`, unauthenticated to `/login`. Child pages do not repeat auth checks.
- Responsive: sidebar collapses to hamburger menu below `lg:` breakpoint.
- Visual: reuses existing `route-card` / `--accent-primary` tokens for consistency with current admin.
- Loading / error: each page self-manages; layout does not centralize.

### 4.4 Capability / Skill management module

#### List page (`capabilities/page.tsx`)

- Group capabilities by `workspace_type`, each group collapsible (expanded by default)
- Row columns: enabled toggle (●/○), id, display_name, [edit] button
- Filters: keyword search (id/display_name), status, workspace_type
- "Create new" button → opens empty YAML template with skeleton of required fields
- Footer: "Reimport from seed" button, "Export all as YAML zip" button

#### Edit page (`capabilities/[id]/page.tsx`)

- Monaco editor (`@monaco-editor/react`), yaml language mode, syntax highlighting
- `id` and `workspace_type` rendered as readonly (PK composite, immutable post-creation)
- Metadata header: updated_at, updated_by_admin
- Validation status indicator: shows live YAML parse errors (300ms debounce) and final server-side Pydantic errors at save time
- Save button disabled when validation fails
- Actions: cancel, "copy as duplicate" (prompts new id, creates copy in same workspace_type), "download .yaml"
- Unsaved-changes guard on route navigation

Skill editor follows the same shape but is simpler:
- No composite PK (id only)
- No graph_template
- `subagent_type` rendered as select (values from v2 subagent registry), not free text

#### Backend APIs

```
GET    /admin/capabilities                              List (grouped)
GET    /admin/capabilities/{id}?workspace_type=X        Read full YAML
POST   /admin/capabilities                              Create (body: yaml string)
PUT    /admin/capabilities/{id}?workspace_type=X        Update (body: yaml string)
DELETE /admin/capabilities/{id}?workspace_type=X        Delete
POST   /admin/capabilities/{id}/toggle                  Toggle enabled
POST   /admin/capabilities/validate                     Validate only (no write)
POST   /admin/capabilities/import-from-seed             Bulk reseed (overwrites DB)
GET    /admin/capabilities/export                       Download all as zip
```

Skill APIs are structurally identical.

#### Cross-reference validation

Done in service layer (requires DB / registry lookup, not in Pydantic):

**For Capability**:
1. Collect all `skill_id` references in `graph_template.phases[*].tasks[*].skill_id`
2. Query `capability_skills` for existence; fail with line-pointed error if any missing
3. Collect all `subagent_type` values from `graph_template.phases[*].tasks[*].subagent_type`
4. Check each against v2 subagent registry (`backend/src/subagents/v2/registry.py`); fail if unknown

**For CapabilitySkill**:
1. Validate `subagent_type` against the same v2 subagent registry. Frontend renders this as a select to prevent free-text entry, but backend re-validates as the final defense.

#### EventBus wiring

Currently `backend/src/gateway/routers/capabilities.py:43-51` uses a `_NoOpEventBus` stub. Replace with real `EventBus(redis_client.client)` (already used in `backend/src/task/tasks/execution.py:57`).

On capability create/update/delete/toggle, service publishes `capability.invalidated` event with payload `{id, workspace_type}`. CapabilityResolver subscribes (already wired at [capability_resolver.py:71](../../backend/src/services/capability_resolver.py#L71)) and invalidates its cache entry.

CapabilitySkill has no cache layer today (the `capability_skill_preload` middleware queries DB per task), so no EventBus needed yet. Add bus subscription only when a skill cache is introduced.

#### Audit

Every save writes to existing `admin_logs` table:

```python
AdminLog(
    action="capability_update",   # or capability_create / capability_delete / capability_toggle
    admin_id=current_user.id,
    target_user_id=None,
    details={
        "capability_id": id,
        "workspace_type": ws,
        "yaml_before_sha256": ...,
        "yaml_after_sha256": ...,
        "diff_fields": ["trigger_phrases", "graph_template.phases[0]"],
    }
)
```

Full diff body is not stored — sha256 + field-level diff summary is enough for forensic purposes. Skill audit is structurally identical.

#### New files

```
backend/src/gateway/routers/admin_capabilities.py
backend/src/gateway/routers/admin_skills.py
backend/src/services/admin_capability_service.py
backend/src/services/admin_skill_service.py
backend/src/services/capability_schema.py        # Pydantic models
```

### 4.5 Credit grant rules + redeem codes module

#### Data model

**Table `credit_grant_rules`**

```python
class CreditGrantRuleType(StrEnum):
    REGISTRATION_BONUS = "registration_bonus"
    REFERRAL_REFERRER  = "referral_referrer"
    REFERRAL_REFERRED  = "referral_referred"
    PERIODIC           = "periodic"

class CreditGrantRule(Base, UUIDMixin):
    __tablename__ = "credit_grant_rules"
    name: str
    rule_type: CreditGrantRuleType
    enabled: bool
    amount: int                              # >0
    description: str | None
    config: dict[str, Any]                   # JSONB, type-specific
    last_triggered_at: datetime | None       # periodic only
    created_at, updated_at
    created_by_admin_id: FK users (nullable)
```

`config` JSONB shape per rule_type:

| rule_type | config fields |
|-----------|---------------|
| `registration_bonus` | (empty) |
| `referral_referrer` | `{trigger: "on_signup" \| "on_first_task"}` (default `on_first_task`) |
| `referral_referred` | `{trigger: "on_signup"}` |
| `periodic` | `{cron: "0 0 * * 1", target_filter: {active_within_days: 30, role: "user"}}` |

Backend uses a discriminated union of Pydantic models keyed on `rule_type` to validate `config` shape on create/update. Submitting `rule_type=periodic` without `cron` (or with an unparseable cron expression) fails with a 400-level error pointing at the offending field.

**Table `credit_redeem_codes`**

```python
class CreditRedeemCode(Base, UUIDMixin):
    __tablename__ = "credit_redeem_codes"
    code: str                                # unique, 16 chars XXXX-XXXX-XXXX-XXXX
    amount: int
    max_uses: int                            # 1 = single-use; N = multi-use (team code)
    use_count: int                           # atomic increment
    per_user_limit: int                      # typical 1
    expires_at: datetime | None
    valid_from: datetime | None
    enabled: bool                            # soft-delete flag
    batch_id: str | None                     # batch UUID
    description: str | None
    created_at
    created_by_admin_id: FK users (nullable)
```

**Table `credit_redemptions`** (per-user redemption ledger, enforces per_user_limit)

```python
class CreditRedemption(Base, UUIDMixin):
    __tablename__ = "credit_redemptions"
    code_id: FK credit_redeem_codes
    user_id: FK users
    transaction_id: FK credit_transactions   # links to actual credit grant
    redeemed_at: datetime
    # Index (code_id, user_id) for per_user_limit count queries
```

**Table `referrals`** (invitation relationship)

```python
class Referral(Base, UUIDMixin):
    __tablename__ = "referrals"
    referrer_user_id: FK users               # inviter
    referee_user_id: FK users                # invitee (unique)
    referrer_credited_at: datetime | None    # when inviter received credits
    referee_credited_at: datetime | None     # when invitee received credits
    referee_first_task_at: datetime | None   # for on_first_task trigger
    created_at
```

**`CreditTransactionType` additions** (existing enum in [backend/src/database/models/credit.py](../../backend/src/database/models/credit.py))

- `REFERRAL_BONUS` — used for both referrer and referee, distinguished by description
- `REDEEM_CODE` — redeem-code redemption

**Migration**: `051_credit_grant_rules_and_redeem_codes.py` — 4 new tables + 2 enum values.

#### Triggers

**Registration** — modify existing register flow to read enabled `registration_bonus` rule and apply its `amount`; if no enabled rule, grant nothing.

**Referral**:
- Backend register endpoint accepts an optional `invite_code` parameter (added in P4). When present, the registration handler resolves the referring user (from a separate user-side invite-code system whose UI plumbing is out of scope), then creates a `Referral` row.
- Until user-side UI passes `invite_code`, the parameter stays null and no `Referral` rows are created — the referral feature is dormant but the backend is ready.
- Fire `REFERRAL_REFERRED` rule at signup if its trigger is `on_signup`.
- Fire `REFERRAL_REFERRER` rule when invitee first completes a task: at task completion event, check whether the user has a referral row with null `referee_first_task_at`, set it, then apply the rule.

**Periodic** — celery beat task `process_credit_grant_rules` runs every 5 minutes:
1. Query enabled `periodic` rules
2. Parse `config.cron` with `croniter`; check whether `last_triggered_at` is overdue
3. Apply `target_filter` to find target users
4. Batch-grant credits via existing credit ledger path (writes `credit_transactions`)
5. Update `last_triggered_at`

**Redeem-code** (user-side endpoint `POST /credits/redeem`):

```python
async with db.begin():
    code = await get_code_for_update(payload.code)   # SELECT ... FOR UPDATE
    # Validate: enabled, not expired, not before valid_from, use_count < max_uses,
    #           current user's redemption count < per_user_limit
    txn = await credit_service.grant(
        user_id=user.id, amount=code.amount,
        transaction_type=REDEEM_CODE,
        description=f"兑换码 {code.code[:9]}***",
    )
    redemption = CreditRedemption(code_id=code.id, user_id=user.id, transaction_id=txn.id)
    code.use_count += 1
    db.add_all([redemption, code])
```

`FOR UPDATE` row lock prevents over-redemption under concurrency.

#### Code generation

```python
import secrets
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # excludes I/1/O/0/l (confusable)

def generate_code() -> str:
    chunks = ["".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(chunks)
```

Entropy: 32^16 ≈ 2^80. DB unique constraint as collision safety net; retry on rare conflict.

#### Backend APIs

```
GET    /admin/credit-rules                    List
POST   /admin/credit-rules                    Create
PUT    /admin/credit-rules/{id}               Update
POST   /admin/credit-rules/{id}/toggle        Toggle enabled
DELETE /admin/credit-rules/{id}               Hard delete (with AdminLog audit)

GET    /admin/redeem-codes?batch_id=...&enabled=...&keyword=...    List
POST   /admin/redeem-codes/batch              Batch generate (body: count, amount, max_uses, per_user_limit, expires_at, batch_description)
GET    /admin/redeem-codes/export.csv?batch_id Download batch as CSV
POST   /admin/redeem-codes/{id}/disable       Soft delete (enabled=false)

POST   /credits/redeem                        User-side (body: code) — in scope but UI integration is out
```

#### Frontend pages

**`/dashboard/admin/credits/rules`** — table of rules with toggle, edit dialog rendering rule_type-specific config fields (registration_bonus has none; referral rules have trigger select; periodic has cron input + target_filter form).

**`/dashboard/admin/credits/redeem-codes`** — list with batch filter, keyword search, table showing code/amount/status/redeemer. "Batch generate" button opens dialog (amount, count 1-10000, max_uses, per_user_limit, expires_at, description); on submit, downloads CSV immediately. "Disable" action soft-deletes.

#### New files

```
backend/src/database/models/credit_grant_rule.py
backend/src/database/models/credit_redeem_code.py
backend/src/database/models/referral.py
backend/src/services/credit_grant_rule_service.py
backend/src/services/credit_redeem_service.py
backend/src/services/referral_service.py
backend/src/gateway/routers/admin_credit_rules.py
backend/src/gateway/routers/admin_redeem_codes.py
backend/src/gateway/routers/credits_redeem.py
backend/src/task/tasks/credit_periodic.py
```

### 4.6 Analytics module

#### Layout

`/dashboard/admin/analytics` — single page with top-bar time range selector (preset: last 7/30/90 days; custom date range) + granularity selector (day/week). 2×2 panel grid below.

#### Panel ① — User growth / activity

- Dual-line chart: daily signups (from `users.created_at`) + daily DAU (distinct `messages.user_id` per day)
- Retention matrix: 6 × 6 weekly cohorts (rows = signup week, columns = week offset 0-5, cell = % of cohort still active)
- KPI cards: current DAU / WAU / 7d retention / 30d retention

#### Panel ② — Capability hotness

- Horizontal bar chart: top 15 capabilities by call count
- Sortable table: capability_id / workspace_type / calls / success rate / avg duration (s) / p95 duration (s)
- Source: `executions` table (`capability_id`, `status`, `created_at`, `completed_at`, join `workspaces` for type)
- Success rate = `status IN ('completed', 'failed_partial')` / total
- Duration = `completed_at - created_at`

#### Panel ③ — Credits / Token trends

- Dual-Y stacked area chart
  - Left axis (credits): daily stacked by `transaction_type` (inflows: admin_grant + registration_bonus + referral_bonus + redeem_code; outflows: workflow_consume + thread_token_consume + admin_deduct)
  - Right axis (tokens): daily total token count line
- KPI cards: total issued / total spent / current pool / total tokens (30d window)
- Token aggregation reuses logic from existing [admin_dashboard_service.py](../../backend/src/services/admin_dashboard_service.py) (thread + feature_tasks + subagents three-source token join)

#### Panel ④ — Workspace / Task distribution

- Dual donut chart: left = workspaces by type (5 categories); right = tasks by status (pending/running/completed/failed/cancelled)
- Failed-top table: top 10 failure patterns by `LEFT(executions.last_error, 80)` literal prefix clustering
- KPI cards: total workspaces / running tasks / 24h failures / failure rate

#### Backend APIs

```
GET /admin/analytics/users-growth?range=30d&granularity=day
GET /admin/analytics/capabilities-usage?range=30d
GET /admin/analytics/credits-tokens-trends?range=30d&granularity=day
GET /admin/analytics/workspaces-tasks?range=30d
```

Each endpoint returns its panel's complete payload (KPIs + chart series + tables). Independent — frontend issues 4 parallel requests.

#### Aggregation strategy

- Real-time SQL aggregation against PG
- Redis cache layer: key `analytics:{endpoint}:{range}:{granularity}`, TTL 5 minutes; `cache_bust=1` query param bypasses
- No ETL / data warehouse — admin access frequency is low
- Index supplements (Migration 052): `executions(created_at, status)`, `messages(user_id, created_at)`

#### Chart library

**Recharts** (`npm i recharts`). Rationale: lightweight (~400KB), React-friendly, theme integration with Tailwind tokens is straightforward, visual style fits v2 Glass/visionOS minimal aesthetic.

#### New files

```
frontend/app/dashboard/admin/analytics/page.tsx
frontend/app/dashboard/admin/analytics/components/
    UserGrowthPanel.tsx
    CapabilityUsagePanel.tsx
    CreditsTokensPanel.tsx
    WorkspaceTasksPanel.tsx
    KpiCard.tsx
    DateRangePicker.tsx
frontend/lib/api/admin-analytics.ts
backend/src/gateway/routers/admin_analytics.py
backend/src/services/admin_analytics_service.py
backend/src/services/admin_analytics_cache.py
```

## 5. Implementation Phasing

| Phase | Content | Effort | Depends on |
|-------|---------|--------|------------|
| **P1 — Cleanup + schema convergence** | Delete dead code; drop `result_card_template`; Capability adds `ui_meta`; EventBus real-wired; frontend type rename | ~1 week | — |
| **P2 — Admin IA migration** | New layout + sidebar + auth hook; existing 5 pages migrated to sub-routes; overview slimmed | ~1 week | P1 |
| **P3 — Capability/Skill mgmt** | Monaco YAML editor + Pydantic + cross-ref + import/export + AdminLog | ~1.5 weeks | P1 + P2 |
| **P4 — Credit rules + redeem codes** | 4 tables + rule triggers + worker beat + atomic redeem + 2 frontend pages | ~1.5 weeks | P2 |
| **P5 — Analytics** | 4 APIs + Redis cache + Recharts 4 panels + index supplements | ~1 week | P2 |

**Total**: ~6 weeks single-developer. P3 / P4 / P5 are mutually independent and can parallelize if multiple developers are available.

### P1 task list

```
P1.1  One-off ETL script: pull icon/color/stages/follow_up_prompt from WorkspaceFeatureDefinition
       and write into the corresponding 25 capability seed YAMLs (matched by id)
P1.2  Migration 049: add ui_meta JSONB column to capabilities
P1.3  Migration 050: drop result_card_template column from capabilities
P1.4  ORM Capability: add ui_meta field, remove result_card_template field
P1.5  capability_loader.py: handle ui_meta, drop result_card_template
P1.6  Delete backend/src/workspace_features/ directory
P1.7  Delete backend/src/agents/feature_leader/ directory
P1.8  Delete backend/src/agents/graphs/ directory
P1.9  chat_agent/agent.py: replace list_workspace_features_tool with list_capabilities_tool
P1.10 gateway/routers/workspaces.py: delete /features endpoint and WorkspaceFeaturesResponse
P1.11 gateway/routers/capabilities.py: include ui_meta in serialization; replace _NoOpEventBus
       with real EventBus(redis_client.client)
P1.12 admin_capability_service skeleton: invalidate-event interface (full CRUD in P3)
P1.13 Frontend: delete lib/execution-presenters.ts and its test
P1.14 Frontend: rename WorkspaceFeature type to Capability, drop agent/agentLabel/panel fields
P1.15 Frontend: update 5 production files using WorkspaceFeature type
P1.16 Frontend: update API calls from /features to /capabilities
P1.17 Delete docs/product/workspace-feature-catalog.md and frontend-feature-plugin-contract.md
P1.18 Run all tests + e2e golden-path; verify EventBus pub/sub works across gateway and worker processes
```

### P2 task list

```
P2.1  Create app/dashboard/admin/layout.tsx (sidebar + auth + outlet)
P2.2  Create AdminSidebar.tsx and AdminPageHeader.tsx
P2.3  Create hooks/use-admin-auth.ts (extract auth guard)
P2.4  Migrate users/page.tsx (current page.tsx 1211-1465 + dialog)
P2.5  Migrate credits/page.tsx (1467-1638)
P2.6  Migrate mcp/page.tsx (1043-1209)
P2.7  Migrate release-gate/page.tsx (786-1041)
P2.8  Migrate logs/page.tsx (1640-1799)
P2.9  Slim overview page.tsx to summary cards + analytics entry cards
P2.10 Extract CreditAdjustDialog.tsx shared component
P2.11 Replace old /dashboard/admin single page
P2.12 Update e2e tests for new routes
```

### P3 task list

```
P3.1  Define Pydantic CapabilityYamlModel / CapabilitySkillYamlModel (incl. ui_meta)
P3.2  admin_capability_service.py: list/get/create/update/delete/toggle/validate +
       EventBus publish + AdminLog (sha256 + diff_fields)
P3.3  admin_skill_service.py same shape (no EventBus, no skill cache)
P3.4  Cross-reference validation (skill_id exists + subagent_type in v2 registry)
P3.5  import-from-seed / export.zip endpoints
P3.6  Frontend capabilities/page.tsx (grouped by workspace_type)
P3.7  Frontend capabilities/[id]/page.tsx (Monaco YAML editor)
P3.8  Frontend skills/page.tsx + skills/[id]/page.tsx (mirrored)
P3.9  Copy-as-duplicate dialog
P3.10 Integrate @monaco-editor/react; configure yaml language mode
P3.11 Unsaved-changes route guard
P3.12 Unit + e2e tests (create capability, save, cross-ref failure, duplicate)
```

### P4 task list

```
P4.1  Migration 051: 4 new tables + 2 CreditTransactionType enum values
P4.2  4 ORM models + relationships
P4.3  credit_grant_rule_service.py: rule CRUD + triggers (registration / referral / periodic)
P4.4  credit_redeem_service.py: batch generate + atomic redeem (FOR UPDATE)
P4.5  referral_service.py: build Referral on signup; fire on first task
P4.6  Hook into existing register flow (replace hardcoded REGISTRATION_BONUS)
P4.7  Hook into first-task-completion event (fire referral_referrer)
P4.8  task/tasks/credit_periodic.py: celery beat task; cron via croniter
P4.9  Celery beat schedule configuration (scan every 5 min)
P4.10 Gateway routers: admin_credit_rules / admin_redeem_codes / credits_redeem
P4.11 Frontend credits/rules/page.tsx + detail dialog
P4.12 Frontend credits/redeem-codes/page.tsx + batch generate dialog + CSV export
P4.13 Unit tests: redemption concurrency safety, rule trigger conditions, cron parsing
```

### P5 task list

```
P5.1  Migration 052: indexes for analytics queries (executions, messages)
P5.2  admin_analytics_service.py: 4 aggregation functions
P5.3  admin_analytics_cache.py: Redis cache decorator (TTL 5min, cache_bust param)
P5.4  Gateway router: 4 endpoints
P5.5  Frontend: npm i recharts
P5.6  Shared KpiCard + DateRangePicker components
P5.7  4 Panel components (UserGrowth / CapabilityUsage / CreditsTokens / WorkspaceTasks)
P5.8  analytics/page.tsx container (2x2 grid + time range + granularity)
P5.9  Overview page (built in P2) adds 4 analytics entry cards (anchor links)
P5.10 Performance validation: 6×6 retention matrix < 200ms
```

## 6. Risks & Assumptions

1. **EventBus cross-process** — P1.11 replaces `_NoOpEventBus` assuming gateway and worker connect to the same Redis. This holds today: [redis_client.py:285](../../backend/src/academic/cache/redis_client.py#L285) is a module-level singleton. Verify in P1 by publishing from gateway and confirming worker-side subscribers receive.
2. **Celery beat deployment** — P4.8 assumes a beat process exists. If `docker-compose.yml` lacks a beat service, add one before P4 begins.
3. **Data volume** — P5 assumes < 10k users, < 100k executions. Real-time SQL aggregation suffices at this scale. If volumes grow, switch to materialized views or pg_cron precomputation.
4. **User-side referral signup UI** — P4 covers rule config and backend triggers, but the **registration page change to accept an invite code** is **out of scope** as a separate PR. P4's referral feature is dormant without this dependency.
5. **No version history** — recovery from a broken capability/skill edit goes via: git seed YAML → admin "import-from-seed" button to bulk-reset, OR AdminLog `yaml_before_sha256` + `diff_fields` for forensic reconstruction.

## 7. Out of Scope

- User-side invite code input on registration page (P4 dependency)
- User-side redeem code input UI (backend endpoint exists; UI placement is a separate decision)
- Frontend `WorkspaceFeature` → `Capability` type rename is in P1, but **renaming downstream variable names** (e.g., `features` state → `capabilities`) is incidental refactoring kept to a minimum to limit P1 blast radius. Variable rename can ride along where natural; otherwise deferred.
- Capability/skill draft / review / publish workflow — explicit non-goal per CLAUDE.md "no draft/review cycle — lead agent has runtime discretion".
- Multi-admin permission tiers (current model: binary admin / user role).
- Soft-delete recovery UI for redeem codes (codes disabled stay disabled; if accidentally disabled, hand-edit DB).
