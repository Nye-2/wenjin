"""Deep Research Skill for comprehensive literature analysis.

This skill performs deep research on a topic by:
1. Searching for relevant papers using Semantic Scholar
2. Analyzing paper abstracts and identifying patterns
3. Identifying research gaps
4. Generating novel research ideas

It uses ParallelExecutor for phased subagent execution:
- Phase 1 (parallel): Scout x2 + Trend Spotter -> papers[], trends[]
- Phase 2 (depends on 1): Gap Miner -> gaps[]
- Phase 3 (depends on 2): Synthesizer -> ideas[]
"""

import asyncio
import copy
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.config import settings
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.subagents.parallel import ExecutionPhase, ParallelExecutor, PhasedPlan, PhaseResult


@dataclass
class Paper:
    """Represents a paper from Semantic Scholar search."""
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    citations: int | None
    url: str | None
    doi: str | None
    paper_id: str | None = None


@dataclass
class ResearchPattern:
    """Represents an identified research pattern."""
    description: str
    frequency: int
    papers: list[str] = field(default_factory=list)


@dataclass
class ResearchGap:
    """Represents an identified research gap."""
    description: str
    supporting_evidence: list[str]
    potential_impact: str


@dataclass
class ResearchIdea:
    """Represents a generated research idea."""
    title: str
    description: str
    methodology_hints: list[str]
    related_papers: list[str]
    novelty_score: float


@dataclass
class ResearchTrend:
    """Represents an identified research trend."""
    topic: str
    description: str
    growth_rate: float = 0.0
    paper_count: int = 0


class DeepResearchSkill(BaseSkill):
    """Comprehensive literature analysis with parallel subagent execution.

    This skill performs deep research analysis using a phased parallel execution model:
    - Phase 1 (parallel): Scout x2 + Trend Spotter for paper discovery and trend analysis
    - Phase 2 (depends on 1): Gap Miner for identifying research gaps
    - Phase 3 (depends on 2): Synthesizer for generating research ideas

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description.
        version: Version string for the skill.
    """

    name = "deep-research"
    description = "Comprehensive literature analysis and research idea generation"
    version = "2.0.0"

    # Configuration
    DEFAULT_SEARCH_LIMIT = 20
    MIN_PAPERS_FOR_ANALYSIS = 5
    KEYWORD_EXTRACTION_MIN_FREQ = 2
    RUNTIME_PHASES = {
        "discovery": {
            "label": "文献发现",
            "description": "并行检索相关论文并提炼趋势",
            "start_progress": 12,
            "end_progress": 40,
        },
        "gap_mining": {
            "label": "空白挖掘",
            "description": "从已有研究中归纳关键空白",
            "start_progress": 48,
            "end_progress": 68,
        },
        "synthesis": {
            "label": "创意综合",
            "description": "生成候选研究创意与方法方向",
            "start_progress": 74,
            "end_progress": 88,
        },
    }

    def __init__(self):
        """Initialize the skill with a ParallelExecutor."""
        super().__init__()
        self._executor = ParallelExecutor(max_concurrent=4)

    def _create_runtime_state(
        self,
        query: str,
        *,
        search_limit: int,
        year_range: str | None,
    ) -> dict[str, Any]:
        """Create the initial runtime state for long-running UI updates."""
        return {
            "title": "Deep Research",
            "current_phase": "discovery",
            "phases": [
                {
                    "id": phase_id,
                    "label": phase["label"],
                    "description": phase["description"],
                    "status": "running" if phase_id == "discovery" else "pending",
                    "progress": 0,
                }
                for phase_id, phase in self.RUNTIME_PHASES.items()
            ],
            "blocks": [
                {
                    "id": "overview",
                    "kind": "metrics",
                    "title": "执行配置",
                    "entries": [
                        {"label": "主题", "value": query},
                        {"label": "检索上限", "value": str(search_limit)},
                        {"label": "时间范围", "value": year_range or "不限"},
                    ],
                },
                {
                    "id": "activity",
                    "kind": "activity",
                    "title": "执行日志",
                    "items": [],
                },
            ],
            "updated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _set_phase_state(
        runtime: dict[str, Any],
        phase_id: str,
        *,
        status: str,
        progress: int,
    ) -> None:
        """Update a single runtime phase in place."""
        for phase in runtime.get("phases", []):
            if phase.get("id") == phase_id:
                phase["status"] = status
                phase["progress"] = progress
                return

    @staticmethod
    def _upsert_runtime_block(runtime: dict[str, Any], block: dict[str, Any]) -> None:
        """Insert or replace a runtime block by id."""
        blocks = runtime.setdefault("blocks", [])
        for index, existing in enumerate(blocks):
            if existing.get("id") == block.get("id"):
                blocks[index] = block
                return
        blocks.append(block)

    @staticmethod
    def _append_activity(
        runtime: dict[str, Any],
        *,
        title: str,
        description: str,
        tone: str = "info",
    ) -> None:
        """Append a short activity log entry to the runtime state."""
        blocks = runtime.setdefault("blocks", [])
        activity_block = next(
            (block for block in blocks if block.get("id") == "activity"),
            None,
        )
        if activity_block is None:
            activity_block = {
                "id": "activity",
                "kind": "activity",
                "title": "执行日志",
                "items": [],
            }
            blocks.append(activity_block)

        items = activity_block.setdefault("items", [])
        items.append(
            {
                "title": title,
                "description": description,
                "tone": tone,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        if len(items) > 12:
            del items[:-12]

    @staticmethod
    def _paper_runtime_item(paper: Paper) -> dict[str, Any]:
        """Serialize a paper into a runtime list item."""
        meta_parts = [str(part) for part in [paper.year, paper.venue] if part]
        return {
            "title": paper.title,
            "description": (paper.abstract or "").strip()[:220] or "暂无摘要",
            "meta": " · ".join(meta_parts) or "未标注来源",
            "badge": (
                f"{paper.citations} citations"
                if paper.citations is not None
                else None
            ),
        }

    @staticmethod
    def _trend_runtime_item(trend: ResearchTrend) -> dict[str, Any]:
        """Serialize a trend into a runtime list item."""
        return {
            "title": trend.topic,
            "description": trend.description,
            "meta": f"{trend.paper_count} papers",
            "badge": (
                f"{trend.growth_rate:.1f}%"
                if trend.growth_rate
                else None
            ),
        }

    @staticmethod
    def _gap_runtime_item(gap: ResearchGap) -> dict[str, Any]:
        """Serialize a research gap into a runtime list item."""
        return {
            "title": gap.description,
            "description": gap.potential_impact,
            "meta": (
                f"{len(gap.supporting_evidence)} 条证据"
                if gap.supporting_evidence
                else "待补充证据"
            ),
            "badge": None,
        }

    @staticmethod
    def _idea_runtime_item(idea: ResearchIdea) -> dict[str, Any]:
        """Serialize a research idea into a runtime list item."""
        return {
            "title": idea.title,
            "description": idea.description,
            "meta": (
                f"{len(idea.methodology_hints)} 个方法提示"
                if idea.methodology_hints
                else "待细化方法"
            ),
            "badge": f"{idea.novelty_score:.2f}",
        }

    async def _emit_runtime(
        self,
        progress_callback,
        runtime: dict[str, Any],
        *,
        progress: int,
        message: str,
        current_phase: str,
        stage_transition: bool = False,
    ) -> None:
        """Emit a runtime update through the unified task progress callback."""
        if progress_callback is None:
            return
        runtime["current_phase"] = current_phase
        runtime["updated_at"] = datetime.now(UTC).isoformat()
        await progress_callback(
            {
                "progress": progress,
                "message": message,
                "current_phase": current_phase,
                "runtime": copy.deepcopy(runtime),
                "stage_transition": stage_transition,
            }
        )

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the deep research skill synchronously.

        This method exposes the async pipeline through the synchronous skill interface.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the research analysis results.
        """
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                # If we have a running loop, run in a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.execute_async(input, state)
                    )
                    return future.result()
            except RuntimeError:
                # No running loop, create one
                return asyncio.run(self.execute_async(input, state))
        except Exception as e:
            return SkillOutput(
                success=False,
                content="",
                error_message=f"Deep research failed: {str(e)}",
            )

    async def execute_async(
        self,
        input: SkillInput,
        state: ThreadState,
        progress_callback=None,
    ) -> SkillOutput:
        """Execute the deep research skill asynchronously with parallel subagents.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the research analysis results.
        """
        try:
            # Get configuration from context
            search_limit = input.context.get("search_limit", self.DEFAULT_SEARCH_LIMIT)
            year_range = input.context.get("year_range", None)
            runtime = self._create_runtime_state(
                input.user_query,
                search_limit=search_limit,
                year_range=year_range,
            )
            self._append_activity(
                runtime,
                title="任务启动",
                description="正在初始化 Deep Research 执行计划。",
            )
            await self._emit_runtime(
                progress_callback,
                runtime,
                progress=self.RUNTIME_PHASES["discovery"]["start_progress"],
                message="正在并行检索论文与研究趋势...",
                current_phase="discovery",
                stage_transition=True,
            )

            # Create the execution plan
            plan = self._create_execution_plan(
                input.user_query,
                search_limit=search_limit,
                year_range=year_range,
            )

            # Execute the plan with context
            context = {
                "workspace_id": input.workspace_id,
                "user_query": input.user_query,
                "search_limit": search_limit,
                "year_range": year_range,
            }

            async def handle_phase_result(phase_result: PhaseResult) -> None:
                if phase_result.phase_name == "discovery":
                    papers = self._extract_papers([phase_result])
                    trends = self._extract_trends([phase_result])
                    self._set_phase_state(
                        runtime,
                        "discovery",
                        status="completed",
                        progress=100,
                    )
                    self._set_phase_state(
                        runtime,
                        "gap_mining",
                        status="running",
                        progress=0,
                    )
                    self._upsert_runtime_block(
                        runtime,
                        {
                            "id": "papers",
                            "kind": "list",
                            "title": "候选论文",
                            "description": f"已发现 {len(papers)} 篇相关论文",
                            "items": [self._paper_runtime_item(paper) for paper in papers[:8]],
                        },
                    )
                    self._upsert_runtime_block(
                        runtime,
                        {
                            "id": "trends",
                            "kind": "list",
                            "title": "研究趋势",
                            "description": f"已提取 {len(trends)} 个趋势信号",
                            "items": [self._trend_runtime_item(trend) for trend in trends[:5]],
                        },
                    )
                    self._upsert_runtime_block(
                        runtime,
                        {
                            "id": "summary",
                            "kind": "metrics",
                            "title": "中间统计",
                            "entries": [
                                {"label": "论文", "value": str(len(papers))},
                                {"label": "趋势", "value": str(len(trends))},
                                {"label": "空白", "value": "0"},
                                {"label": "创意", "value": "0"},
                            ],
                        },
                    )
                    self._append_activity(
                        runtime,
                        title="文献发现完成",
                        description=f"已汇总 {len(papers)} 篇论文并提炼 {len(trends)} 个趋势。",
                        tone="success",
                    )
                    await self._emit_runtime(
                        progress_callback,
                        runtime,
                        progress=self.RUNTIME_PHASES["discovery"]["end_progress"],
                        message=f"已发现 {len(papers)} 篇论文，开始挖掘研究空白...",
                        current_phase="gap_mining",
                        stage_transition=True,
                    )

                elif phase_result.phase_name == "gap_mining":
                    gaps = self._extract_gaps([phase_result])
                    self._set_phase_state(
                        runtime,
                        "gap_mining",
                        status="completed",
                        progress=100,
                    )
                    self._set_phase_state(
                        runtime,
                        "synthesis",
                        status="running",
                        progress=0,
                    )
                    summary_block = next(
                        (
                            block for block in runtime.get("blocks", [])
                            if block.get("id") == "summary"
                        ),
                        None,
                    )
                    if summary_block:
                        summary_block["entries"] = [
                            {"label": "论文", "value": next((entry["value"] for entry in summary_block.get("entries", []) if entry.get("label") == "论文"), "0")},
                            {"label": "趋势", "value": next((entry["value"] for entry in summary_block.get("entries", []) if entry.get("label") == "趋势"), "0")},
                            {"label": "空白", "value": str(len(gaps))},
                            {"label": "创意", "value": "0"},
                        ]
                    self._upsert_runtime_block(
                        runtime,
                        {
                            "id": "gaps",
                            "kind": "list",
                            "title": "研究空白",
                            "description": f"已识别 {len(gaps)} 个可行动的研究空白",
                            "items": [self._gap_runtime_item(gap) for gap in gaps[:5]],
                        },
                    )
                    self._append_activity(
                        runtime,
                        title="空白挖掘完成",
                        description=f"已识别 {len(gaps)} 个关键研究空白，进入创意综合阶段。",
                        tone="success",
                    )
                    await self._emit_runtime(
                        progress_callback,
                        runtime,
                        progress=self.RUNTIME_PHASES["gap_mining"]["end_progress"],
                        message=f"已识别 {len(gaps)} 个研究空白，开始生成研究创意...",
                        current_phase="synthesis",
                        stage_transition=True,
                    )

                elif phase_result.phase_name == "synthesis":
                    ideas = self._extract_ideas([phase_result])
                    self._set_phase_state(
                        runtime,
                        "synthesis",
                        status="completed",
                        progress=100,
                    )
                    summary_block = next(
                        (
                            block for block in runtime.get("blocks", [])
                            if block.get("id") == "summary"
                        ),
                        None,
                    )
                    if summary_block:
                        entries = {entry.get("label"): entry.get("value") for entry in summary_block.get("entries", [])}
                        summary_block["entries"] = [
                            {"label": "论文", "value": entries.get("论文", "0")},
                            {"label": "趋势", "value": entries.get("趋势", "0")},
                            {"label": "空白", "value": entries.get("空白", "0")},
                            {"label": "创意", "value": str(len(ideas))},
                        ]
                    self._upsert_runtime_block(
                        runtime,
                        {
                            "id": "ideas",
                            "kind": "list",
                            "title": "候选创意",
                            "description": f"已生成 {len(ideas)} 个候选研究创意",
                            "items": [self._idea_runtime_item(idea) for idea in ideas[:5]],
                        },
                    )
                    self._append_activity(
                        runtime,
                        title="创意综合完成",
                        description=f"已输出 {len(ideas)} 个研究创意，正在整理最终结果。",
                        tone="success",
                    )
                    await self._emit_runtime(
                        progress_callback,
                        runtime,
                        progress=self.RUNTIME_PHASES["synthesis"]["end_progress"],
                        message=f"已生成 {len(ideas)} 个候选创意，正在整理研究报告...",
                        current_phase="synthesis",
                        stage_transition=True,
                    )

            phase_results = await self._executor.execute_plan(
                plan,
                context,
                phase_callback=handle_phase_result,
            )

            # Extract results from phases
            papers = self._extract_papers(phase_results)
            trends = self._extract_trends(phase_results)
            gaps = self._extract_gaps(phase_results)
            ideas = self._extract_ideas(phase_results)

            # If no papers were found via subagents, fall back to direct search
            if not papers:
                papers = self._search_papers(input.user_query, search_limit, year_range)
                self._upsert_runtime_block(
                    runtime,
                    {
                        "id": "papers",
                        "kind": "list",
                        "title": "候选论文",
                        "description": f"兜底检索补充到 {len(papers)} 篇论文",
                        "items": [self._paper_runtime_item(paper) for paper in papers[:8]],
                    },
                )
                self._append_activity(
                    runtime,
                    title="兜底检索",
                    description=f"子代理未返回论文，已通过直接检索补充 {len(papers)} 篇论文。",
                    tone="warning",
                )

            if not papers:
                self._append_activity(
                    runtime,
                    title="未找到论文",
                    description="当前主题未检索到足够相关的文献，请尝试放宽查询。",
                    tone="warning",
                )
                return SkillOutput(
                    success=True,
                    content=f"No papers found for query: '{input.user_query}'. Try broadening your search.",
                    metadata={"papers_found": 0, "runtime": runtime},
                )

            # Analyze patterns from papers
            patterns = self._analyze_patterns(papers)
            synthesis = self._synthesize_findings(papers, patterns)

            # If no gaps/ideas from subagents, generate them locally
            if not gaps:
                gaps = self._identify_research_gaps(papers, patterns)
            if not ideas:
                ideas = self._generate_research_ideas(papers, patterns, gaps)

            # Create artifacts
            artifacts = self._create_artifacts(
                input.workspace_id,
                input.user_query,
                papers,
                patterns,
                trends,
                gaps,
                ideas,
                synthesis,
            )
            self._upsert_runtime_block(
                runtime,
                {
                    "id": "artifacts",
                    "kind": "metrics",
                    "title": "最终产物",
                    "entries": [
                        {"label": "Artifact 数量", "value": str(len(artifacts))},
                        {"label": "报告状态", "value": "已生成"},
                    ],
                },
            )
            self._append_activity(
                runtime,
                title="最终结果已生成",
                description=f"已完成研究报告并生成 {len(artifacts)} 个结构化产物。",
                tone="success",
            )

            # Build content report
            content = self._build_report(
                input.user_query,
                papers,
                patterns,
                gaps,
                ideas,
                synthesis,
            )

            # Update cited papers in state
            cited_papers = [p.doi for p in papers if p.doi]
            if cited_papers:
                state["cited_papers"] = list(set(state.get("cited_papers", []) + cited_papers))

            return SkillOutput(
                success=True,
                content=content,
                artifacts=artifacts,
                metadata={
                    "papers_analyzed": len(papers),
                    "patterns_identified": len(patterns),
                    "gaps_identified": len(gaps),
                    "ideas_generated": len(ideas),
                    "trends_identified": len(trends),
                    "search_query": input.user_query,
                    "parallel_execution": True,
                    "runtime": runtime,
                },
            )

        except Exception as e:
            if progress_callback is not None:
                self._append_activity(
                    runtime,
                    title="执行失败",
                    description=str(e),
                    tone="danger",
                )
                if runtime.get("current_phase"):
                    self._set_phase_state(
                        runtime,
                        runtime["current_phase"],
                        status="failed",
                        progress=100,
                    )
                await self._emit_runtime(
                    progress_callback,
                    runtime,
                    progress=90,
                    message=f"Deep Research 执行失败：{e}",
                    current_phase=runtime.get("current_phase", "discovery"),
                    stage_transition=True,
                )
            return SkillOutput(
                success=False,
                content="",
                error_message=f"Deep research failed: {str(e)}",
                metadata={"runtime": runtime} if "runtime" in locals() else {},
            )

    def _create_execution_plan(
        self,
        query: str,
        search_limit: int = 20,
        year_range: str | None = None,
    ) -> PhasedPlan:
        """Create a phased execution plan for parallel subagent execution.

        The plan follows a three-phase structure:
        - Phase 1 (parallel): Discovery - 2 Scouts + Trend Spotter
        - Phase 2 (depends on 1): Gap Mining
        - Phase 3 (depends on 2): Synthesis

        Args:
            query: The research query.
            search_limit: Maximum number of papers to search.
            year_range: Optional year range filter.

        Returns:
            A PhasedPlan with execution phases.
        """
        year_filter = f" between {year_range}" if year_range else ""

        # Phase 1: Parallel discovery
        discovery_phase = ExecutionPhase(
            name="discovery",
            tasks=[
                {
                    "subagent_type": "scout",
                    "prompt": f"Search for highly-cited papers about '{query}'{year_filter}. "
                    f"Find {search_limit} relevant papers. Focus on seminal works and foundational research. "
                    "Return a structured list with title, authors, year, venue, abstract, citations, url, and doi.",
                },
                {
                    "subagent_type": "scout",
                    "prompt": f"Search for recent papers about '{query}' from the last 2-3 years. "
                    "Focus on cutting-edge research and emerging directions. "
                    "Return a structured list with title, authors, year, venue, abstract, citations, url, and doi.",
                },
                {
                    "subagent_type": "trend_spotter",
                    "prompt": f"Analyze research trends for '{query}'. "
                    "Identify: 1) Hot topics gaining traction, 2) Declining areas, "
                    "3) Emerging methodologies, 4) Future directions. "
                    "Provide specific paper counts and growth rates where possible.",
                },
            ],
            depends_on=[],
        )

        # Phase 2: Gap mining (depends on discovery)
        gap_mining_phase = ExecutionPhase(
            name="gap_mining",
            tasks=[
                {
                    "subagent_type": "gap_miner",
                    "prompt": f"Based on the literature about '{query}', identify 3-5 significant research gaps. "
                    "For each gap provide: 1) Clear description, 2) Supporting evidence from existing work, "
                    "3) Potential impact of addressing this gap. "
                    "Focus on actionable gaps with clear research potential.",
                },
            ],
            depends_on=["discovery"],
        )

        # Phase 3: Synthesis (depends on gap mining)
        synthesis_phase = ExecutionPhase(
            name="synthesis",
            tasks=[
                {
                    "subagent_type": "synthesizer",
                    "prompt": f"Synthesize research ideas for '{query}' based on the identified gaps. "
                    "Generate 2-3 novel research ideas that address the gaps. "
                    "For each idea include: 1) Title, 2) Description, 3) Methodology hints, "
                    "4) Related papers, 5) Novelty score (0-1). "
                    "Focus on ideas with high potential impact and feasibility.",
                },
            ],
            depends_on=["gap_mining"],
        )

        return PhasedPlan(
            phases=[discovery_phase, gap_mining_phase, synthesis_phase],
            context={
                "query": query,
                "search_limit": search_limit,
                "year_range": year_range,
            },
        )

    def _extract_papers(self, phase_results: list[PhaseResult]) -> list[Paper]:
        """Extract papers from phase results.

        Args:
            phase_results: Results from executing phases.

        Returns:
            List of Paper objects extracted from results.
        """
        papers = []
        seen_titles = set()

        for phase in phase_results:
            if phase.phase_name == "discovery":
                for task_result in phase.task_results:
                    if isinstance(task_result, dict) and task_result.get("success"):
                        result = task_result.get("result", {})
                        if isinstance(result, dict):
                            # Handle papers from scout subagents
                            for paper_data in result.get("papers", []):
                                if isinstance(paper_data, dict):
                                    title = paper_data.get("title", "")
                                    if title and title not in seen_titles:
                                        seen_titles.add(title)
                                        papers.append(Paper(
                                            title=title,
                                            authors=paper_data.get("authors", []),
                                            year=paper_data.get("year"),
                                            venue=paper_data.get("venue"),
                                            abstract=paper_data.get("abstract"),
                                            citations=paper_data.get("citations"),
                                            url=paper_data.get("url"),
                                            doi=paper_data.get("doi"),
                                            paper_id=paper_data.get("paper_id"),
                                        ))

        return papers

    def _extract_trends(self, phase_results: list[PhaseResult]) -> list[ResearchTrend]:
        """Extract research trends from phase results.

        Args:
            phase_results: Results from executing phases.

        Returns:
            List of ResearchTrend objects extracted from results.
        """
        trends = []

        for phase in phase_results:
            if phase.phase_name == "discovery":
                for task_result in phase.task_results:
                    if isinstance(task_result, dict) and task_result.get("success"):
                        result = task_result.get("result", {})
                        if isinstance(result, dict):
                            for trend_data in result.get("trends", []):
                                if isinstance(trend_data, dict):
                                    trends.append(ResearchTrend(
                                        topic=trend_data.get("topic", ""),
                                        description=trend_data.get("description", ""),
                                        growth_rate=trend_data.get("growth_rate", 0.0),
                                        paper_count=trend_data.get("paper_count", 0),
                                    ))

        return trends

    def _extract_gaps(self, phase_results: list[PhaseResult]) -> list[ResearchGap]:
        """Extract research gaps from phase results.

        Args:
            phase_results: Results from executing phases.

        Returns:
            List of ResearchGap objects extracted from results.
        """
        gaps = []

        for phase in phase_results:
            if phase.phase_name == "gap_mining":
                for task_result in phase.task_results:
                    if isinstance(task_result, dict) and task_result.get("success"):
                        result = task_result.get("result", {})
                        if isinstance(result, dict):
                            for gap_data in result.get("gaps", []):
                                if isinstance(gap_data, dict):
                                    gaps.append(ResearchGap(
                                        description=gap_data.get("description", ""),
                                        supporting_evidence=gap_data.get("supporting_evidence", []),
                                        potential_impact=gap_data.get("potential_impact", ""),
                                    ))

        return gaps

    def _extract_ideas(self, phase_results: list[PhaseResult]) -> list[ResearchIdea]:
        """Extract research ideas from phase results.

        Args:
            phase_results: Results from executing phases.

        Returns:
            List of ResearchIdea objects extracted from results.
        """
        ideas = []

        for phase in phase_results:
            if phase.phase_name == "synthesis":
                for task_result in phase.task_results:
                    if isinstance(task_result, dict) and task_result.get("success"):
                        result = task_result.get("result", {})
                        if isinstance(result, dict):
                            for idea_data in result.get("ideas", []):
                                if isinstance(idea_data, dict):
                                    ideas.append(ResearchIdea(
                                        title=idea_data.get("title", ""),
                                        description=idea_data.get("description", ""),
                                        methodology_hints=idea_data.get("methodology_hints", []),
                                        related_papers=idea_data.get("related_papers", []),
                                        novelty_score=idea_data.get("novelty_score", 0.5),
                                    ))

        return ideas

    def _search_papers(
        self,
        query: str,
        limit: int,
        year_range: str | None = None,
    ) -> list[Paper]:
        """Search for papers using Semantic Scholar.

        This is a fallback method used when subagents don't return papers.

        Args:
            query: The search query.
            limit: Maximum number of results.
            year_range: Optional year range filter.

        Returns:
            List of Paper objects.
        """
        try:
            from semanticscholar import SemanticScholar

            client = SemanticScholar(api_key=settings.semantic_scholar_api_key)

            search_params = {
                "query": query,
                "limit": limit,
            }

            if year_range:
                search_params["year"] = year_range

            results = client.search_paper(**search_params)

            papers = []
            for paper in results:
                # Extract authors
                authors = []
                if paper.authors:
                    authors = [a.get("name", "Unknown") for a in paper.authors]

                # Extract DOI
                doi = None
                if paper.externalIds and "DOI" in paper.externalIds:
                    doi = paper.externalIds["DOI"]

                papers.append(Paper(
                    title=paper.title or "Untitled",
                    authors=authors,
                    year=paper.year,
                    venue=paper.venue,
                    abstract=paper.abstract,
                    citations=paper.citationCount,
                    url=paper.url,
                    doi=doi,
                    paper_id=paper.paperId,
                ))

            return papers

        except ImportError:
            # Return empty list if semanticscholar package is not installed
            return []
        except Exception:
            # Return empty list on any API error
            return []

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text.

        Args:
            text: The text to extract keywords from.

        Returns:
            List of extracted keywords.
        """
        if not text:
            return []

        # Common stopwords to filter out
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "this",
            "that", "these", "those", "we", "our", "their", "its", "paper",
            "study", "research", "approach", "method", "result", "results",
            "propose", "present", "show", "using", "based", "new", "novel",
        }

        # Extract words (alphanumeric sequences)
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Filter out stopwords and count
        filtered = [w for w in words if w not in stopwords]

        return filtered

    def _analyze_patterns(self, papers: list[Paper]) -> list[ResearchPattern]:
        """Analyze patterns across paper abstracts.

        Args:
            papers: List of papers to analyze.

        Returns:
            List of identified research patterns.
        """
        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return []

        # Collect all keywords from abstracts
        all_keywords = []
        paper_keywords: dict[str, list[str]] = {}

        for paper in papers:
            if paper.abstract:
                keywords = self._extract_keywords(paper.abstract)
                paper_keywords[paper.title] = keywords
                all_keywords.extend(keywords)

        # Count keyword frequencies
        keyword_counts = Counter(all_keywords)

        # Identify patterns (frequent meaningful keywords)
        patterns = []
        for keyword, count in keyword_counts.most_common(15):
            if count >= self.KEYWORD_EXTRACTION_MIN_FREQ:
                # Find papers containing this keyword
                related_papers = [
                    title for title, kwds in paper_keywords.items()
                    if keyword in kwds
                ]

                patterns.append(ResearchPattern(
                    description=f"Frequent focus on '{keyword}' (appears in {count} abstracts)",
                    frequency=count,
                    papers=related_papers[:5],  # Limit to top 5 papers
                ))

        # Identify methodology patterns
        methodology_terms = [
            "deep learning", "neural network", "transformer", "attention",
            "reinforcement learning", "supervised", "unsupervised", "semi-supervised",
            "transfer learning", "fine-tuning", "pre-training", "embedding",
            "classification", "regression", "clustering", "gan", "vae",
            "lstm", "cnn", "rnn", "bert", "gpt", "graph neural",
        ]

        for term in methodology_terms:
            count = sum(
                1 for p in papers
                if p.abstract and term in p.abstract.lower()
            )
            if count >= self.KEYWORD_EXTRACTION_MIN_FREQ:
                related_papers = [
                    p.title for p in papers
                    if p.abstract and term in p.abstract.lower()
                ]
                patterns.append(ResearchPattern(
                    description=f"Common methodology: '{term}' (used in {count} papers)",
                    frequency=count,
                    papers=related_papers[:5],
                ))

        # Identify temporal patterns (year distribution)
        years = [p.year for p in papers if p.year]
        if years:
            year_counts = Counter(years)
            if len(year_counts) > 1:
                most_common_year = year_counts.most_common(1)[0]
                patterns.append(ResearchPattern(
                    description=f"Peak publication year: {most_common_year[0]} ({most_common_year[1]} papers)",
                    frequency=most_common_year[1],
                    papers=[p.title for p in papers if p.year == most_common_year[0]][:5],
                ))

        return patterns

    def _synthesize_findings(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
    ) -> str:
        """Synthesize findings from papers and patterns.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.

        Returns:
            Synthesis summary string.
        """
        if not papers:
            return "No papers available for synthesis."

        # Calculate basic statistics
        total_papers = len(papers)
        papers_with_abstracts = sum(1 for p in papers if p.abstract)
        total_citations = sum(p.citations or 0 for p in papers)

        # Year range
        years = [p.year for p in papers if p.year]
        year_range = ""
        if years:
            min_year, max_year = min(years), max(years)
            year_range = f"Published between {min_year} and {max_year}."

        # Top venues
        venues = [p.venue for p in papers if p.venue]
        venue_counts = Counter(venues).most_common(3)
        top_venues = ", ".join([v[0] for v in venue_counts]) if venue_counts else "N/A"

        # Top cited papers
        sorted_papers = sorted(
            [p for p in papers if p.citations],
            key=lambda x: x.citations or 0,
            reverse=True,
        )[:3]
        top_cited = "; ".join([f"{p.title} ({p.citations} citations)" for p in sorted_papers])

        synthesis_parts = [
            f"Analyzed {total_papers} papers ({papers_with_abstracts} with abstracts).",
            year_range,
            f"Total citations across all papers: {total_citations}.",
            f"Top venues: {top_venues}.",
        ]

        if top_cited:
            synthesis_parts.append(f"Most cited papers: {top_cited}.")

        if patterns:
            synthesis_parts.append(f"Identified {len(patterns)} significant patterns.")

        return " ".join(synthesis_parts)

    def _identify_research_gaps(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
    ) -> list[ResearchGap]:
        """Identify research gaps based on analysis.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.

        Returns:
            List of identified research gaps.
        """
        gaps = []

        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return gaps

        # Collect all abstract text
        all_abstracts = " ".join([p.abstract or "" for p in papers]).lower()

        # Identify potential gaps based on common research frontiers
        gap_indicators = [
            (
                "interpretability",
                "Explainability and interpretability of models",
                "limited attention to model interpretability",
            ),
            (
                "robustness",
                "Robustness and adversarial resilience",
                "limited study of model robustness",
            ),
            (
                "efficiency",
                "Computational efficiency and scalability",
                "limited focus on computational efficiency",
            ),
            (
                "real-world",
                "Real-world deployment and applications",
                "limited real-world validation",
            ),
            (
                "benchmark",
                "Standardized benchmarks and evaluation",
                "lack of standardized benchmarks",
            ),
            (
                "cross-domain",
                "Cross-domain generalization",
                "limited cross-domain evaluation",
            ),
            (
                "long-term",
                "Long-term performance and temporal aspects",
                "limited longitudinal studies",
            ),
            (
                "ethical",
                "Ethical considerations and fairness",
                "limited discussion of ethical implications",
            ),
        ]

        for keyword, gap_title, _evidence_template in gap_indicators:
            if keyword not in all_abstracts:
                # Find supporting papers that partially relate
                supporting = []
                for p in papers:
                    if p.abstract and any(
                        related in p.abstract.lower()
                        for related in ["evaluation", "future", "limitation", "challenge"]
                    ):
                        supporting.append(p.title)

                gaps.append(ResearchGap(
                    description=gap_title,
                    supporting_evidence=supporting[:3],
                    potential_impact=f"Addressing {gap_title.lower()} could significantly advance the field.",
                ))

        # Identify methodology gaps
        abstracts_text = all_abstracts
        method_gaps = []

        if "ablation" not in abstracts_text:
            method_gaps.append("comprehensive ablation studies")

        if "error analysis" not in abstracts_text and "failure" not in abstracts_text:
            method_gaps.append("detailed error analysis")

        if method_gaps:
            gaps.append(ResearchGap(
                description=f"Rigorous methodology: {', '.join(method_gaps)}",
                supporting_evidence=[p.title for p in papers[:3]],
                potential_impact="Improved methodological rigor would strengthen research validity.",
            ))

        # Limit to most significant gaps
        return gaps[:5]

    def _generate_research_ideas(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        gaps: list[ResearchGap],
    ) -> list[ResearchIdea]:
        """Generate novel research ideas based on analysis.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            gaps: List of identified gaps.

        Returns:
            List of generated research ideas.
        """
        ideas = []

        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return ideas

        # Get top patterns
        top_patterns = patterns[:5] if patterns else []
        pattern_keywords = [
            p.description.split("'")[1] if "'" in p.description else "research"
            for p in top_patterns
        ]

        # Generate ideas based on gaps
        for i, gap in enumerate(gaps[:3]):
            # Create a novel combination idea
            related_papers = []
            for p in papers[:5]:
                if p.abstract:
                    related_papers.append(p.title)

            # Calculate novelty based on gap frequency in literature
            novelty = min(0.9, 0.5 + (len(gaps) - i) * 0.1)

            ideas.append(ResearchIdea(
                title=f"Novel approach combining {pattern_keywords[0] if pattern_keywords else 'techniques'} with {gap.description.lower()}",
                description=f"This research could address the gap in {gap.description.lower()} by leveraging insights from {pattern_keywords[0] if pattern_keywords else 'recent advances'}. {gap.potential_impact}",
                methodology_hints=[
                    "Systematic literature review",
                    "Experimental validation",
                    "Comparative analysis",
                ],
                related_papers=related_papers[:3],
                novelty_score=novelty,
            ))

        # Generate cross-pollination ideas
        if len(top_patterns) >= 2:
            ideas.append(ResearchIdea(
                title=f"Cross-pollination: Integrating {pattern_keywords[0]} with {pattern_keywords[1]}",
                description=f"Exploring the intersection of {pattern_keywords[0]} and {pattern_keywords[1]} could reveal novel insights and methodologies not yet explored in the literature.",
                methodology_hints=[
                    f"Apply {pattern_keywords[0]} techniques to {pattern_keywords[1]} problems",
                    "Develop unified framework",
                    "Empirical comparison",
                ],
                related_papers=[p.title for p in papers[:4]],
                novelty_score=0.85,
            ))

        # Generate future direction ideas based on recent papers
        recent_papers = sorted(
            [p for p in papers if p.year],
            key=lambda x: x.year or 0,
            reverse=True,
        )[:3]

        if recent_papers:
            recent_topics = []
            for p in recent_papers:
                if p.abstract:
                    keywords = self._extract_keywords(p.abstract)[:3]
                    recent_topics.extend(keywords)

            if recent_topics:
                ideas.append(ResearchIdea(
                    title=f"Emerging direction: Advanced applications in {recent_topics[0]}",
                    description=f"Building on recent work, this research could explore advanced applications and extensions in {recent_topics[0]}, addressing current limitations and opening new research frontiers.",
                    methodology_hints=[
                        "State-of-the-art baseline comparison",
                        "Novel dataset creation",
                        "Performance benchmarking",
                    ],
                    related_papers=[p.title for p in recent_papers],
                    novelty_score=0.75,
                ))

        return ideas

    def _create_artifacts(
        self,
        workspace_id: str,
        query: str,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        trends: list[ResearchTrend],
        gaps: list[ResearchGap],
        ideas: list[ResearchIdea],
        synthesis: str,
    ) -> list[AcademicArtifact]:
        """Create academic artifacts from the analysis.

        Args:
            workspace_id: The workspace ID.
            query: The original deep research query.
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            trends: List of identified trends.
            gaps: List of identified gaps.
            ideas: List of generated ideas.
            synthesis: Final synthesis summary.

        Returns:
            List of AcademicArtifact objects.
        """
        timestamp = datetime.now(UTC)
        serialized_papers = [
            {
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "venue": paper.venue,
                "citations": paper.citations,
                "doi": paper.doi,
                "url": paper.url,
                "paper_id": paper.paper_id,
                "abstract": paper.abstract,
            }
            for paper in papers
        ]
        serialized_patterns = [
            {
                "description": pattern.description,
                "frequency": pattern.frequency,
                "papers": pattern.papers,
            }
            for pattern in patterns
        ]
        serialized_trends = [
            {
                "topic": trend.topic,
                "description": trend.description,
                "growth_rate": trend.growth_rate,
                "paper_count": trend.paper_count,
            }
            for trend in trends
        ]
        serialized_gaps = [
            {
                "description": gap.description,
                "supporting_evidence": gap.supporting_evidence,
                "potential_impact": gap.potential_impact,
            }
            for gap in gaps
        ]
        serialized_ideas = [
            {
                "title": idea.title,
                "description": idea.description,
                "methodology_hints": idea.methodology_hints,
                "related_papers": idea.related_papers,
                "novelty_score": idea.novelty_score,
            }
            for idea in ideas
        ]

        recommended_actions = [
            {
                "action": "literature_management",
                "reason": "将调研结果导入文献管理，便于筛选与引用。",
            }
        ]
        if serialized_gaps or serialized_ideas:
            recommended_actions.append(
                {
                    "action": "thesis_writing.generate_outline",
                    "reason": "基于研究空白与候选创意生成论文大纲。",
                }
            )
        if serialized_ideas:
            recommended_actions.append(
                {
                    "action": "opening_research",
                    "reason": "把调研结论进一步整理为开题背景与研究意义。",
                }
            )

        return [
            AcademicArtifact(
                id=f"deep-research-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                type="deep_research_report",
                content={
                    "schema_version": "v1",
                    "source_feature": "deep_research",
                    "topic": query,
                    "discipline": None,
                    "query": {
                        "keywords": [query],
                        "constraints": [],
                    },
                    "corpus": {
                        "paper_count": len(serialized_papers),
                        "top_papers": serialized_papers[:8],
                    },
                    "discovery": {
                        "patterns": serialized_patterns,
                        "trends": serialized_trends,
                        "summary": synthesis,
                    },
                    "gaps": serialized_gaps,
                    "ideas": serialized_ideas,
                    "recommended_actions": recommended_actions,
                    "generated_at": timestamp.isoformat(),
                    "generation_mode": "skill",
                },
                created_by_skill=self.name,
            )
        ]

    def _build_report(
        self,
        query: str,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        gaps: list[ResearchGap],
        ideas: list[ResearchIdea],
        synthesis: str,
    ) -> str:
        """Build a formatted report of the research analysis.

        Args:
            query: The original search query.
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            gaps: List of identified gaps.
            ideas: List of generated ideas.
            synthesis: Synthesis summary.

        Returns:
            Formatted report string.
        """
        sections = []

        # Title
        sections.append(f"# Deep Research Analysis: {query}")
        sections.append("")

        # Summary
        sections.append("## Summary")
        sections.append(synthesis)
        sections.append("")

        # Papers analyzed
        sections.append("## Papers Analyzed")
        for i, paper in enumerate(papers[:10], 1):  # Limit to top 10
            sections.append(f"### {i}. {paper.title}")
            if paper.authors:
                sections.append(f"**Authors:** {', '.join(paper.authors[:3])}")
            if paper.year:
                sections.append(f"**Year:** {paper.year}")
            if paper.venue:
                sections.append(f"**Venue:** {paper.venue}")
            if paper.citations is not None:
                sections.append(f"**Citations:** {paper.citations}")
            if paper.doi:
                sections.append(f"**DOI:** {paper.doi}")
            sections.append("")

        if len(papers) > 10:
            sections.append(f"*...and {len(papers) - 10} more papers.*")
            sections.append("")

        # Patterns
        if patterns:
            sections.append("## Research Patterns Identified")
            for pattern in patterns:
                sections.append(f"- {pattern.description}")
            sections.append("")

        # Research Gaps
        if gaps:
            sections.append("## Research Gaps")
            for gap in gaps:
                sections.append(f"### {gap.description}")
                sections.append(f"*Potential Impact:* {gap.potential_impact}")
                if gap.supporting_evidence:
                    sections.append("*Supporting Evidence:*")
                    for evidence in gap.supporting_evidence:
                        sections.append(f"  - {evidence}")
                sections.append("")

        # Research Ideas
        if ideas:
            sections.append("## Generated Research Ideas")
            for i, idea in enumerate(ideas, 1):
                sections.append(f"### Idea {i}: {idea.title}")
                sections.append(idea.description)
                sections.append(f"**Novelty Score:** {idea.novelty_score:.2f}")
                if idea.methodology_hints:
                    sections.append("**Methodology Hints:**")
                    for hint in idea.methodology_hints:
                        sections.append(f"  - {hint}")
                if idea.related_papers:
                    sections.append("**Related Papers:**")
                    for paper in idea.related_papers:
                        sections.append(f"  - {paper}")
                sections.append("")

        return "\n".join(sections)
