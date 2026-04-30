# Wenjin 长期方向种子

更新时间：2026-04-30
状态：Seed
适用范围：产品战略、数据产品方向、长期路线回顾

> 本文不是当前实现事实源，也不是短期交付承诺。它用于保存关于 Wenjin 长期方向的判断种子，后续产品评审时可回顾、修订或废弃。

## 1. 核心判断

Wenjin 不应长期定位为普通 AI 写作工具。

普通 AI 工具的壁垒会持续下降：模型能力会被平台化，prompt 模板会被复制，单点写作功能也会被通用办公软件吸收。Wenjin 更有前景的定位是：

**以 Workspace/Compute 为科研工作流引擎，以 WenjinPrism 为稿件基础设施，以人类编辑决策和科研过程轨迹为数据飞轮的科研交付平台。**

短期卖点是帮助用户更可靠地完成论文、学位论文、申报书、专利、软著材料等交付。

长期资产不是“拥有很多 prompt”，而是沉淀：

1. 科研任务如何被拆解。
2. 什么上下文会提高 AI 输出质量。
3. 哪些指令、证据组织方式和工作流会被用户接受。
4. 用户如何把 AI 输出改成最终稿。
5. 什么样的稿件质量检查能降低科研写作风险。

## 2. 当前基础

项目已经具备从工具走向平台的几个关键条件：

1. Workspace 已经覆盖 thesis、sci、proposal、software_copyright、patent 五类科研交付场景。
2. Chat 作为控制入口，Feature 作为执行事务，Compute 作为长任务工作面，WenjinPrism 作为最终稿件承载，边界比较清晰。
3. WenjinPrism 已经支持 LaTeX 项目文件树、编译、PDF 预览、点评改写、SyncTeX、file-change preview/apply/revert。
4. ExecutionSession、Task、Artifact、GenerationRecord、Paper、PaperSection、UserKnowledge 等模型已经提供了过程数据与产物数据基础。
5. Prism 的 apply/revert 是天然的高质量人工反馈信号，比普通聊天点赞更适合构建数据飞轮。

这些基础说明，Wenjin 的优势不在“能不能调用模型写一段文字”，而在能不能把调研、证据、写作、审阅、落稿、修改、编译、交付串成可复现的系统。

## 3. 功能层面优先补齐方向

如果先落实功能层面，建议优先补齐以下能力。它们同时服务短期产品体验和长期数据资产。

### 3.1 可验证文献与证据层

当前文献检索和调研能力应逐步从 LLM synthesis 升级为 evidence-grounded workflow。

目标：

1. 当前实现收敛为 Semantic Scholar 单源核验；OpenAlex、Crossref、arXiv、PubMed、专利库等只能作为未来同一检索接口下的可选扩展，不能重新形成多套事实来源。
2. 每条文献、专利、期刊信息、引用建议都带 `source`、`external_id`、`url`、`doi`、`verified_at`。
3. 用户可区分“已核验事实”“模型推断”“待核验线索”。
4. 检索结果可进入 workspace-scoped Reference Library，并能被后续写作、综述、审稿、引用检查复用。

关键产品能力：

1. 文献检索结果去重、筛选、标星、加入文献库。
2. 文献 section 级阅读和引用摘录。
3. 证据包 evidence pack：围绕一个研究问题组织文献、论点、方法、实验、局限。

### 3.2 Claim-Evidence Graph

科研写作的核心不是生成文本，而是保证论断有证据。

建议新增一等实体：

1. `Claim`：稿件中的关键论断、贡献点、研究空白、实验结论。
2. `Evidence`：支持 claim 的文献片段、实验结果、数据表、代码运行结果、用户输入事实。
3. `CitationBinding`：claim 与引用标记之间的绑定关系。
4. `VerificationStatus`：verified、inferred、missing、conflict、needs_review。

Prism 中每个段落或 section 可以显示证据状态：

1. 证据充足。
2. 引用缺失。
3. 引用存在但证据不匹配。
4. 有待核验事实。
5. 与其他段落结论冲突。

这个方向会让 Wenjin 从“写作助手”升级为“可信科研写作系统”。

### 3.3 Prism 稿件语义层

WenjinPrism 不应只停留在文件编辑器。它应逐步形成稿件语义层。

建议沉淀：

1. section map：LaTeX 文件、章节、小节、段落的结构映射。
2. claim map：段落到 claim 的映射。
3. citation map：引用命令、bib entry、证据来源的映射。
4. figure/table map：图表、caption、正文引用、源数据的映射。
5. review finding map：审稿意见、用户 feedback、AI 评审意见与具体文本位置的映射。

这样 AI 后续不只是“改写选区”，而是能理解：

1. 这段在论文结构中承担什么功能。
2. 这里缺哪个证据。
3. 这里的引用是否支撑论断。
4. 修改是否破坏前后文逻辑。

### 3.4 质量门禁体系

现有 Prism 已有结构门禁、签名校验、哈希校验和编译门禁。下一步应扩展为科研质量门禁。

建议门禁：

1. Citation correctness gate：引用是否真实、是否支撑对应论断。
2. Hallucination gate：稿件中是否存在未证实的论文、专利号、实验结果、期刊指标。
3. Consistency gate：摘要、贡献点、方法、实验、结论是否一致。
4. Journal guideline gate：格式、字数、section、图表、引用风格是否符合目标期刊或模板。
5. Reviewer risk gate：从审稿人视角输出 major concerns、minor concerns、reject risk。
6. Reproducibility gate：实验结果是否能追溯到数据、代码、运行日志或用户确认事实。

这些 gate 不应只是报告，而应能回写到 Compute、Prism、Activity 和 next actions。

### 3.5 全流程工作流状态

用户需要看到的不只是功能列表，而是当前项目进度。

建议新增工作流层实体：

1. `ResearchPlan`：研究计划或写作计划。
2. `Milestone`：调研完成、大纲完成、初稿完成、审稿完成、投稿准备完成等阶段。
3. `Requirement`：模板、导师、期刊、项目指南、专利交底要求。
4. `Todo`：由 AI 或用户创建的下一步动作。
5. `ReviewFinding`：质量检查或人工审阅发现的问题。
6. `SubmissionChecklist`：终稿前检查项。

这会把 23 个 feature 串成“从调研到终稿”的可执行路线，而不是让用户在功能面板里自行选择。

### 3.6 协作与审阅

真实科研写作往往涉及导师、合作者、客户、代理师、审稿人。

建议逐步补齐：

1. 多角色权限：owner、editor、reviewer、viewer。
2. 评论与批注流：Prism feedback、PDF feedback、section review。
3. 审阅任务分配：把某个 section 或 claim 指派给合作者确认。
4. 版本对比：AI 修改、人工修改、导师意见修改之间的 diff。
5. 决策记录：为什么接受、拒绝或回滚某次 AI 修改。

协作层既能提升产品价值，也能产生更强的质量标签。

### 3.7 实验、数据与代码侧入口

如果未来要靠近 AI Scientist，不能只做写作。

应预留：

1. Hypothesis：研究假设。
2. ExperimentPlan：实验设计。
3. Dataset：数据集与数据处理记录。
4. CodeRun：代码运行、环境、日志、结果。
5. ResultTable：实验结果表。
6. FigureSource：图表源数据、绘图代码、caption。
7. ReproducibilityPackage：复现包与投稿补充材料。

短期不一定全做，但数据模型和 artifact contract 应避免把这些堵死。

## 4. 数据产品方向

不要把长期数据产品理解成“prompt 库”。

Prompt 本身有几个问题：

1. 强依赖上下文和模型版本。
2. 噪声高，很多 prompt 只是用户临时表达。
3. 容易包含未发表想法、论文草稿、专利交底等敏感内容。
4. 没有 outcome label 时无法判断好坏。
5. 容易被复制，单独作为资产壁垒弱。

更有价值的数据资产是：

**Research Workflow Trace Dataset**

也就是“科研任务轨迹数据集”。

一个高价值样本应包含：

```json
{
  "task_type": "sci_introduction_revision",
  "workspace_type": "sci",
  "research_field": "machine_learning",
  "input_context": {
    "section_type": "Introduction",
    "claims": ["..."],
    "evidence_ids": ["paper_section_x", "paper_section_y"],
    "journal_target": "optional"
  },
  "instruction": {
    "system_prompt_version": "v3",
    "user_prompt": "...",
    "feature_id": "writing",
    "skill_id": "section-writer"
  },
  "tool_trace": {
    "retrieval": ["..."],
    "citation_check": ["..."],
    "latex_compile": "passed"
  },
  "model_output": "...",
  "human_decision": {
    "previewed": true,
    "applied": true,
    "edited_after_apply": true,
    "reverted": false
  },
  "quality_signal": {
    "compile_passed": true,
    "citation_verified": true,
    "review_score_delta": 0.18,
    "accepted_by_user": true
  }
}
```

这种数据能回答：

1. 哪些科研任务最适合 AI 自动化。
2. 哪种上下文组织方式最有效。
3. 哪类 prompt 或 instruction recipe 能提高 apply 率。
4. 哪些输出会被用户回滚。
5. 哪些质量门禁最能预测最终稿件质量。
6. 哪类工作流可以从选题推进到终稿。

最终沉淀的产品不是 prompt market，而是：

1. 科研任务 benchmark。
2. 领域 workflow recipe。
3. 写作质量评估集。
4. 个性化科研写作模型。
5. 实验室或机构级科研知识与交付数据平台。

## 5. 数据采集原则

科研数据高度敏感。任何数据产品方向都必须先设计边界。

基本原则：

1. 明确 opt-in：默认不把用户内容用于跨用户数据产品。
2. 可解释 consent：告诉用户采集什么、为什么、如何脱敏、如何退出。
3. 内容与信号分离：优先采集结构化行为信号，谨慎采集原文。
4. 脱敏与摘要化：研究主题、草稿、专利交底、实验结果必须可脱敏或只保留抽象特征。
5. 租户隔离：个人、团队、机构数据边界必须清晰。
6. 可删除：用户应能删除 workspace 和对应可识别数据。
7. 不训练未授权内容：未授权原文不得进入全局训练集。

长期可信度比短期数据量更重要。

## 6. 阶段路线

### Phase 1：可信写作工作台

目标：把“从调研到初稿到 Prism 落稿”打通并稳定。

重点：

1. 强化文献检索真实数据源。
2. 强化 Prism file-change review gate。
3. 完善 workspace workflow dashboard。
4. 让论文、申报书、专利三类至少各有一条端到端成功路径。

### Phase 2：证据驱动写作系统

目标：每个关键论断都有证据状态。

重点：

1. Claim-Evidence Graph。
2. Citation correctness gate。
3. 稿件语义层。
4. 文献 section 级引用与证据绑定。

### Phase 3：科研工作流数据平台

目标：把用户选择、AI 输出、工具调用和稿件结果沉淀为可分析数据。

重点：

1. ResearchTrace / PromptTrace / HumanDecision 数据模型。
2. Prism apply/revert/edit diff 数据化。
3. Feature outcome 评估指标。
4. 可视化 prompt/workflow effectiveness。

### Phase 4：机构与实验室工作台

目标：让 Wenjin 成为实验室、课题组或机构的科研交付系统。

重点：

1. 多人协作。
2. 组织模板。
3. 团队知识库。
4. 数据隔离与权限。
5. 团队级质量标准和复用 workflow。

### Phase 5：AI Scientist 雏形

目标：从可信写作扩展到可验证研究执行。

重点：

1. Hypothesis generation。
2. Experiment design。
3. Code execution。
4. Result analysis。
5. Figure/table generation from real data。
6. Paper drafting with evidence and reproducibility links。

AI Scientist 不应从“自动写论文”开始，而应从“可验证的小型科研闭环”开始。

## 7. 近期最值得做的三件事

如果只选三件能同时提升功能体验和长期壁垒的事：

1. **Prism apply/revert 数据化**：把 preview、apply、revert、人工后编辑、编译结果记录为 HumanDecision 事件。
2. **文献真实检索与证据包**：减少 LLM 编造空间，让调研 feature 输出可核验 evidence pack。
3. **Claim-Evidence 最小闭环**：先让用户能把一个段落或 claim 绑定到若干文献 section，并在 Prism 中看到证据状态。

这三件事完成后，Wenjin 会明显区别于普通 AI 写作工具。

## 8. 产品定位句

短期定位：

**Wenjin 是面向科研交付的 AI 工作台，覆盖调研、写作、审阅、LaTeX 落稿与终稿准备。**

中期定位：

**Wenjin 是证据驱动的科研写作系统，让每个关键论断、引用和修改都有来源、有状态、可审阅。**

长期定位：

**Wenjin 是科研工作流数据平台，通过真实科研任务轨迹、人工编辑决策和稿件质量反馈，持续逼近可验证的 AI Scientist。**
