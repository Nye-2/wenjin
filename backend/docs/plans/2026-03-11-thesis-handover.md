# 本科毕业设计模块 - 交接文档

> 最后更新: 2026-03-11

---

## 1. 项目概述

本科毕业设计模块是 AcademiaGPT v2 的核心功能之一，旨在自动化生成完整的本科毕业论文（LaTeX格式），包括文献检索、章节撰写、配图生成和PDF编译。

**技术栈**: Python 3.12, LangGraph, Pydantic v2, FastAPI, asyncio

---

## 2. 已完成功能

### 2.1 模块结构

```
src/thesis/
├── __init__.py                    # 模块导出 ✅
├── api.py                         # HTTP API 端点 ✅
├── task_storage.py                # 任务存储抽象层 ✅
├── config.py                      # 配置管理 ✅ (新增)
│
└── workflow/
    ├── __init__.py
    ├── state.py                   # 工作流状态定义 ✅
    ├── latex_template.py          # LaTeX模板（中英文）✅
    ├── graph.py                   # LangGraph 状态机 ✅ (新增)
    ├── runner.py                  # 工作流执行器 ✅ (新增)
    │
    └── nodes/
        ├── __init__.py            # 节点导出 ✅
        ├── base.py                # 基础工具函数 ✅
        ├── literature_search.py   # 文献搜索节点 ✅
        ├── section_writer.py      # 章节写入节点 ✅
        ├── figure_planner.py      # 配图规划节点 ✅ (新增)
        ├── figure_generator.py    # 配图生成节点 ✅ (新增, stub)
        ├── assembler.py           # LaTeX组装节点 ✅
        └── compiler.py            # LaTeX编译节点 ✅ (新增, stub)
```

### 2.2 已实现组件详情

#### 2.2.1 状态定义 (`workflow/state.py`)

```python
# 核心数据模型
class SectionPlan(BaseModel)      # 章节规划
class SectionContent(BaseModel)   # 章节内容
class SectionStatus(StrEnum)      # 章节状态枚举
class PaperReference(BaseModel)   # 参考文献
class FigureRequest(BaseModel)    # 配图需求
class GeneratedFigure(BaseModel)  # 生成的图片

# 工作流状态 (TypedDict + LangGraph reducers)
class ThesisWorkflowState(TypedDict):
    # 输入
    workspace_id, thread_id, paper_title, discipline, abstract_content, framework_json
    # 规划
    section_plans, writing_order
    # 文献
    references (merge_references), citation_plan
    # 写作
    sections (merge_sections), current_section_index
    # 配图
    figure_requests, generated_figures
    # 输出
    final_latex, pdf_path, bib_content
    # 进度
    current_phase, progress, errors (merge_errors)
```

#### 2.2.2 任务存储 (`task_storage.py`)

```python
class ThesisTask              # 任务数据类
class TaskStorage (ABC)       # 存储抽象接口
class InMemoryTaskStorage     # 线程安全内存存储

# 全局函数
get_storage() -> TaskStorage
set_storage(storage)          # 用于测试/自定义实现
create_thesis_task(...)       # 创建新任务
```

#### 2.2.3 API端点 (`api.py`)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/generate` | POST | 创建论文生成任务 |
| `/status/{task_id}` | GET | 获取任务状态 |
| `/cancel/{task_id}` | DELETE | 取消任务 |
| `/preview/{task_id}` | GET | 获取LaTeX预览 |
| `/list` | GET | 列出任务 |

#### 2.2.4 工作流节点

| 节点 | 文件 | 功能 |
|------|------|------|
| `literature_search_node` | `literature_search.py` | 检查文献充足性，准备搜索上下文 |
| `section_writer_node` | `section_writer.py` | 获取下一章节，标记为writing状态 |
| `assemble_latex_node` | `assembler.py` | 组装完整LaTeX文档，生成BibTeX |

#### 2.2.5 LaTeX模板 (`latex_template.py`)

- `THESIS_TEMPLATE_ZH` - 中文论文模板 (ctexbook)
- `THESIS_TEMPLATE_EN` - 英文论文模板 (article)
- `get_template(language)` - 按语言获取模板

### 2.3 Subagent配置

```
src/subagents/academic/
├── thesis_prompts.py         # ThesisWriter, Librarian, FigurePlanner prompts
└── registry.py               # SubagentConfig 注册 (含 thesis_writer, librarian, figure_planner)
```

### 2.4 测试文件

```
tests/thesis/
├── test_api.py                              # API测试
├── test_config.py                           # 配置测试 ✅ (新增)
└── workflow/
    ├── test_state.py                        # 状态测试
    ├── test_graph.py                        # 工作流图测试 ✅ (新增)
    ├── test_runner.py                       # 执行器测试 ✅ (新增)
    └── nodes/
        ├── test_literature_search.py        # 文献搜索节点测试
        ├── test_section_writer.py           # 章节写入节点测试
        ├── test_figure_planner.py           # 配图规划节点测试 ✅ (新增)
        ├── test_figure_generator.py         # 配图生成节点测试 ✅ (新增)
        ├── test_assembler.py                # 组装节点测试
        └── test_compiler.py                 # 编译节点测试 ✅ (新增)
```

---

## 3. Phase 1 实现状态 ✅ (2026-03-11)

### 3.1 已完成文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/thesis/config.py` | ✅ 完成 | ThesisSettings 配置管理 |
| `src/thesis/workflow/graph.py` | ✅ 完成 | LangGraph 状态机 (6节点) |
| `src/thesis/workflow/runner.py` | ✅ 完成 | 后台任务执行器 |
| `src/thesis/workflow/nodes/figure_planner.py` | ✅ 完成 | 配图规划节点 |
| `src/thesis/workflow/nodes/figure_generator.py` | ✅ 完成 (stub) | 配图生成节点 |
| `src/thesis/workflow/nodes/compiler.py` | ✅ 完成 (stub) | LaTeX编译节点 |
| `src/thesis/api.py` | ✅ 更新 | 集成后台任务 |

### 3.2 Stub 实现说明

以下节点为 stub 实现，需要后续集成 ExecutionService:

- **figure_generator.py**: 需要 `ExecutionType.MERMAID_DIAGRAM`, `PYTHON_PLOT`, `AI_IMAGE`
- **compiler.py**: 需要 `ExecutionType.LATEX_COMPILE` 完整集成

### 3.3 测试覆盖

```
tests/thesis/
├── test_api.py                    # 11 tests
├── test_config.py                 # 14 tests
└── workflow/
    ├── test_state.py              # 4 tests
    ├── test_graph.py              # 9 tests
    ├── test_runner.py             # 11 tests
    └── nodes/
        ├── test_literature_search.py  # 3 tests
        ├── test_section_writer.py     # 2 tests
        ├── test_assembler.py          # 2 tests
        ├── test_figure_planner.py     # 26 tests
        ├── test_figure_generator.py   # 4 tests
        └── test_compiler.py           # 2 tests

总计: 88 tests ✅
```

### 3.4 Phase 2/3 规划

| Phase | 功能 |
|-------|------|
| Phase 2 | 真实文献搜索 (Semantic Scholar API)、WebSocket进度推送、Memory系统集成、ExecutionService完整集成 |
| Phase 3 | Skills补充 (thesis-outline, thesis-reviewer)、完整测试覆盖、性能优化 |

---

## 4. 依赖关系

### 4.1 内部依赖

- `src/thesis/workflow/state.py` - 状态定义
- `src/thesis/task_storage.py` - 任务存储
- `src/thesis/workflow/latex_template.py` - LaTeX模板
- `src/subagents/academic/` - Subagent配置

### 4.2 外部依赖

- **LangGraph** (已安装 `langgraph>=0.2.60`)
- **deer-flow ExecutionMiddleware** - LaTeX编译工具
- **ExecutionService** - 配图生成 (MERMAID_DIAGRAM, PYTHON_PLOT, AI_IMAGE)

---

## 5. 关键代码位置

| 功能 | 文件:行号 |
|------|-----------|
| 状态定义 | `src/thesis/workflow/state.py:109-148` |
| 任务创建 | `src/thesis/task_storage.py:190-217` |
| API generate端点 | `src/thesis/api.py:70-112` |
| 章节写入逻辑 | `src/thesis/workflow/nodes/section_writer.py:48-110` |
| LaTeX组装 | `src/thesis/workflow/nodes/assembler.py:31-94` |
| 进度计算 | `src/thesis/workflow/nodes/base.py:12-48` |

---

## 6. 测试命令

```bash
# 运行thesis模块测试
pytest tests/thesis/ -v

# 运行单个测试文件
pytest tests/thesis/test_api.py -v
pytest tests/thesis/workflow/nodes/ -v
```

---

## 7. 注意事项

1. **类型安全**: 节点函数需要处理 `dict` 和 `Pydantic Model` 两种输入，使用 `get_section_attr()` 等辅助函数
2. **线程安全**: `InMemoryTaskStorage` 使用 `RLock`，适合单worker部署，生产环境需替换为Redis
3. **时间处理**: 使用 `datetime.now(UTC)` 而非已弃用的 `datetime.utcnow()`
4. **LangGraph reducers**: `sections`、`references`、`errors` 使用自定义合并函数

---

## 8. 相关文档

- 设计文档: `docs/plans/2026-03-11-thesis-phase1-design.md`
- 原始规划: `docs/plans/2026-03-11-undergraduate-thesis.md`
