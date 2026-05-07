# Chat Redesign · 并行实施 Task 交接文档

**日期**：2026-05-07
**承接 agent 工作目录**：`/Users/ze/wenjin/.claude/worktrees/chat-redesign`
**承接 agent 工作分支**：`worktree-chat-redesign`
**控制 agent**（写这份文档的我）继续做集成任务，二者并行。

---

## 1. 你（承接 agent）要做的 9 个 task

按这个顺序做。每个 task 都是**机械化的**（Plan 里已经给出完整代码）、**和我的工作不冲突**（不动同一份文件）。

### 来自 Plan 1 (Backend)
- ✅ ~~Task 1: AgentBlock pydantic schema~~ — **已完成**（commit `d5c1dec`），可作为参考样例
- **Task 2: 结构化输出 wrapper + JSON 失败降级**
  - 创建 `backend/src/agents/lead_agent/structured_output.py`
  - 创建 `backend/tests/agents/lead_agent/test_structured_output.py`
- **Task 3: Jargon blacklist + 断言 helper**
  - 创建 `backend/src/agents/lead_agent/prompts/__init__.py`
  - 创建 `backend/src/agents/lead_agent/prompts/jargon.py`
  - 创建 `backend/tests/agents/lead_agent/test_jargon.py`
- **Task 4: 重写 lead_agent system prompt**
  - 创建 `backend/src/agents/lead_agent/prompts/system.py`
  - 创建 `backend/tests/agents/lead_agent/test_prompts_snapshot.py`
  - 注意：snapshot 测试需要 `syrupy` 依赖；如果项目没有 `syrupy`，先 `uv add --dev syrupy` 再做
- **Task 5: 重写 skill guidance prompts**
  - 创建 `backend/src/agents/lead_agent/prompts/skills.py`
  - 修改 `backend/src/workspace_features/skills.py`：把内联的 prompt 字符串替换成 `from src.agents.lead_agent.prompts import skills as skill_prompts; skill_prompts.render(skill_id)`
  - 扩展 `test_prompts_snapshot.py`
- **Task 11: subagent_task 加 `criticality` 列**
  - 创建 alembic 迁移 `<NEXT_REV>_subagent_criticality.py`
  - 修改 `backend/src/database/models/subagent_task.py`
  - 修改 `backend/src/subagents/models.py`（dataclass 加 `criticality: Literal["low","high"] = "low"`）
  - 创建 `backend/tests/database/test_subagent_task_criticality.py`
- **Task 13: 创建 `workspace_run` 表**
  - 创建 alembic 迁移 `<NEXT_REV>_workspace_run.py`（注意 `down_revision` 要指向 Task 11 的迁移）
  - 创建 `backend/src/database/models/workspace_run.py`
  - 创建 `backend/tests/database/test_workspace_run_model.py`
- **Task 14: WorkspaceRunService CRUD**
  - 创建 `backend/src/services/workspace_run_service.py`
  - 创建 `backend/tests/services/test_workspace_run_service.py`
  - 注意：`create_run` 必须接受 `run_id: str` 参数（外部传入，**不能**自动 uuid 生成）。详见 [Plan 1 Task 14 修订说明](docs/superpowers/plans/2026-05-07-chat-redesign-plan-1-backend.md)

### 来自 Plan 2 (Frontend)
- **Task 1: TypeScript AgentBlock types**
  - 创建 `frontend/lib/api/blocks.ts`
  - 修改 `frontend/lib/api/types.ts`：加 `ThreadBlockEvent`，从 thread-stream 事件 union 里**删除** `assistant_message` 路径
  - 创建 `frontend/tests/unit/lib/blocks.test.ts`
- **Task 2: `runs.ts` API wrappers**
  - 创建 `frontend/lib/api/runs.ts`
  - 创建 `frontend/tests/unit/lib/runs.test.ts`

---

## 2. 关键资源

| 类型 | 路径 |
|---|---|
| Spec | `docs/superpowers/specs/2026-05-07-chat-experience-redesign-design.md` |
| Plan 1 (你做 Tasks 2/3/4/5/11/13/14) | `docs/superpowers/plans/2026-05-07-chat-redesign-plan-1-backend.md` |
| Plan 2 (你做 Tasks 1/2) | `docs/superpowers/plans/2026-05-07-chat-redesign-plan-2-frontend.md` |
| Plan 1 Task 1 实现样例 | `backend/src/agents/lead_agent/blocks.py` + `backend/tests/agents/lead_agent/test_blocks_schema.py` |

**每个 task 的完整代码（含 test、实现、commit message）都在 Plan 文档里已经给出来了，按 plan 抄即可。**

---

## 3. **你绝对不要碰**的 task（我在做）

以下文件 / 任务**全是我的工作**，避免冲突：

- Plan 1 Task 6: 修改 `backend/src/agents/lead_agent/agent.py`（接入 `parse_with_fallback`）
- Plan 1 Task 7: 修改 `backend/src/runtime/runs/worker.py`、`backend/src/application/handlers/thread_turn_handler.py`、`backend/src/application/results.py`（替换 `assistant_message` SSE）
- Plan 1 Task 8: 修改 `backend/src/subagents/parallel.py`（加 `pause_event`）
- Plan 1 Task 9: 修改 `backend/src/subagents/manager.py`
- Plan 1 Task 10: 修改 `backend/src/gateway/routers/runs.py` + `backend/src/gateway/dependencies.py`
- Plan 1 Task 12: 修改 `backend/src/subagents/parallel.py` 的 `_execute_task` 失败分支
- Plan 1 Task 15: 修改 `backend/src/agents/lead_agent/agent.py` + `backend/src/gateway/routers/runs.py`（接入 result_card 持久化、DELETE endpoint）
- Plan 1 Task 16: `backend/tests/integration/test_paper_analysis_flow.py`
- Plan 2 Tasks 3-16: 所有右面板组件 / 左 chat 组件 / 状态管理 / SSE 订阅 / i18n
- Plan 3 全部 12 个 task

---

## 4. 环境踩坑记录（学到的、你别再踩）

### Backend (Python + uv)
1. **uv 二进制不在默认 PATH 里**：用 `/Users/ze/.local/bin/uv` 全路径
2. **VIRTUAL_ENV 干扰**：跑命令前 `unset VIRTUAL_ENV`，否则 uv 报 "does not match the project environment path .venv"
3. **Worktree 第一次跑 test 需要先建 venv**：
   ```bash
   cd /Users/ze/wenjin/.claude/worktrees/chat-redesign/backend
   unset VIRTUAL_ENV
   /Users/ze/.local/bin/uv sync --all-extras --dev
   source .venv/bin/activate
   ```
4. **跑测试**：`source .venv/bin/activate && python -m pytest <path>` 最稳

### Frontend (Next.js)
- 还没踩坑（你做 Plan 2 Tasks 1/2 时会先遇到）。可能也需要 `npm install` 或者 `npm ci` 在 worktree 里跑一次

---

## 5. 工作约定

### Commits
- 每个 task **一个 commit**（每次都按 plan 写的 commit message 来，保持风格一致）
- Commit 消息后面加：
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- 你做完一个 task **不要** push，只 commit 本地。我做完合并时统一处理

### TDD 节奏
- 严格按 plan 5 步走：① 写失败测试 ② 跑确认失败 ③ 实现 ④ 跑确认通过 ⑤ commit
- 别跳过 step ②（确认失败）—— 这是验证测试是真在测东西

### 不要做的事
- **不要**修改 spec / plan 文档（它们是冻结的契约）
- **不要**碰 §3 列出的我的文件（避免 merge 冲突）
- **不要**做 plan 里没有的工作（YAGNI）—— 哪怕你觉得"顺手优化下"
- **不要** push 远端
- **不要**跑 `git rebase` / `git reset --hard` / `git push --force` 之类的破坏性操作

### 卡住怎么办
- 优先看 plan 里的 "Step 3: Implement" 小节，照抄
- 如果 plan 给的代码跑不起来（test 不过 / import 错误），**停下来**，记录卡点（写到这份文档第 7 节"承接 agent 进度"里）
- 不要硬猜 / 不要 silently 跳过

---

## 6. 完成顺序建议

T2 / T3 / T11 / T13 互相独立，可以并行但建议线性来：

1. T2（结构化输出 wrapper） → 容易 ✅
2. T3（jargon helper） → 容易 ✅
3. T4（系统 prompt + snapshot test 框架）→ 中等
4. T5（skill prompts，依赖 T4 的 snapshot 测试框架）→ 中等
5. T11（criticality 迁移）→ 容易，但需要你跑 alembic
6. T13（workspace_run 迁移）→ 容易，**`down_revision` 必须 = T11 的 revision id**
7. T14（CRUD service，依赖 T13）→ 中等
8. Plan 2 T1（TS 类型镜像）→ 容易（独立于 backend）
9. Plan 2 T2（runs.ts wrapper）→ 容易（独立）

---

## 7. 承接 agent 进度（你边做边更新这一节）

格式：`- [x] T<N>: <commit hash> <一句话说明>` 完成后填进来。卡住就写 `- [ ] T<N>: BLOCKED — <原因>`

```
- [x] T1: d5c1dec  AgentBlock schema (control agent did this as the reference)
- [x] T2: 1bf7877 结构化输出 wrapper + JSON 失败降级
- [x] T3: b770ee3 Jargon blacklist + assert_no_jargon helper
- [x] T4: 298eb00 重写 lead_agent system prompt + snapshot tests
- [x] T5: 3699e75 重写 skill guidance prompts + 替换 workspace_features/skills.py 内联 prompt
- [x] T11: 9686257 添加 criticality 列到 subagent_task_records + SubagentTask dataclass
- [x] T13: 5558a96 创建 workspace_run 表 + run_id FK on subagent_task_records
- [x] T14: 5c3bd46 WorkspaceRunService CRUD + 修复 agent.py 中文引号
- [x] Plan2 T1: dd12b03 TypeScript AgentBlock mirrors + ThreadBlockEvent
- [x] Plan2 T2: 99f8a3f runs.ts wrappers — pause/resume/cancel/delete
```

我（控制 agent）会定期 `git log` 看你的进度，并在我 merge 集成 task 时一起拉过来。

---

## 8. 完工 / 同步信号

你做完 9 个 task 后：
1. 在第 7 节标注全部完成 + commit hash
2. 跑一次 `cd backend && python -m pytest tests/agents/lead_agent/ tests/database/ tests/services/ -v` 确认全绿
3. 跑一次 `cd frontend && npx vitest run tests/unit/lib/blocks.test.ts tests/unit/lib/runs.test.ts` 确认全绿
4. **不要**跑 plan 里的 e2e（playwright）—— 那是 Plan 3 的事
5. 通知用户"我做完 9 个 task 了"，让用户告诉我（控制 agent）
