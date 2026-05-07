# 给另一个 Claude session 的交接提示词

把下面的内容（从 `===== COPY BELOW =====` 到末尾）整段复制粘贴到一个**新开的 Claude Code session** 里。

---

`===== COPY BELOW =====`

我有一份并行任务交接给你做。这是 wenjin 项目（科研写作平台）chat 体验重设计的实施工作，原本由另一个 Claude session 主导设计 + 拆 plan，现在他做需要判断的集成 task，让你做不需要判断的机械化 task，俩并行省时间。

## 第一步：进入工作目录

```bash
cd /Users/ze/wenjin/.claude/worktrees/chat-redesign
git branch --show-current  # 应该输出 worktree-chat-redesign
git log -1 --oneline       # 应该是 d5c1dec feat(agent): add AgentBlock pydantic schema...
```

如果分支不对或目录不在，**停下来告诉我**，不要继续。

## 第二步：读交接文档

完整看一遍：

```
docs/superpowers/handoff/2026-05-07-parallel-task-handoff.md
```

这份文档列出了你要做的 **9 个 task**、不要碰的文件、环境踩坑记录、工作约定、完成信号。重点看：
- §1 你的 9 个 task（顺序、文件路径）
- §3 **不要碰**的文件清单（避免和另一个 agent 冲突）
- §4 环境踩坑（uv 路径 / VIRTUAL_ENV / venv 设置流程）
- §5 工作约定（commit 风格、TDD 节奏、不能做的事）
- §7 进度记录（你做完一个 task 在那里打勾）

## 第三步：参考 Plan 1 Task 1 的实现样例

控制 agent 已经做完了 Plan 1 Task 1（AgentBlock schema），作为风格示例。看：

```
backend/src/agents/lead_agent/blocks.py
backend/tests/agents/lead_agent/test_blocks_schema.py
```

你做的所有 task 都应该和这个一样的风格：
- 文件顶部有 docstring 说明用途 + 引用 spec 章节
- 严格按 plan 给的代码抄
- TDD 五步走（写失败测试 → 跑确认失败 → 实现 → 跑确认通过 → commit）
- 一个 task 一个 commit

## 第四步：完整的 plan 文档

每个 task 的具体步骤、要写的代码、要跑的命令、要写的 commit message — **plan 里全有了**。你只要照抄。

```
docs/superpowers/plans/2026-05-07-chat-redesign-plan-1-backend.md
docs/superpowers/plans/2026-05-07-chat-redesign-plan-2-frontend.md
```

## 第五步：开始做

按交接文档 §6 的顺序做：T2 → T3 → T4 → T5 → T11 → T13 → T14 → Plan 2 T1 → Plan 2 T2。

**每完成一个 task**：
1. 跑一遍 plan 指定的测试命令，确认通过
2. commit（按 plan 给的 commit message，记得加 Co-Authored-By 行）
3. 在 [docs/superpowers/handoff/2026-05-07-parallel-task-handoff.md](docs/superpowers/handoff/2026-05-07-parallel-task-handoff.md) 第 7 节把那条 `- [ ] T<N>: ___` 改成 `- [x] T<N>: <commit hash> <一句话说明>`，commit 这次 doc 更新

## 重要约束

- **不要 push 远端**
- **不要 rebase / reset --hard / branch -D**
- **不要碰**交接文档 §3 列的我的文件（merge 冲突会很麻烦）
- **不要修改** spec 或 plan 文档（它们是冻结契约）
- **不要做 plan 之外的优化**（哪怕你觉得"顺手"），如果发现 plan 有问题，**停下来**写到第 7 节"BLOCKED"里
- **superpowers 工作流**：你不需要走 brainstorming / writing-plans / subagent-driven-development —— 那些控制 agent 已经做完了。你只需要按 plan 抄、跑测试、commit

## 完工

9 个 task 全做完后，按交接文档 §8 跑两轮测试确认全绿，然后告诉我（用户）"我做完了"。我会通知控制 agent 接手集成。

---

现在开始：先进入目录、看交接文档、看 Plan 1 Task 1 样例，然后做 Task 2（结构化输出 wrapper + JSON 失败降级）。

`===== END OF COPY =====`
