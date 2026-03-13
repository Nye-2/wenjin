"""Tests for concrete workspace feature handlers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import (
    THESIS_HANDLER_KEYS,
    THESIS_AGENTS,
    THESIS_WORKSPACE_TYPES,
    _is_thesis_payload,
    execute_workspace_feature,
    execute_thesis_generation,
    generate_outline_only,
    write_single_chapter,
)


class TestThesisPayloadDetection:
    def test_all_thesis_sets_empty(self):
        """All thesis detection sets should be empty.
        thesis features now route via task_type at _dispatch_task level,
        so _is_thesis_payload() should never trigger."""
        assert THESIS_WORKSPACE_TYPES == set()
        assert THESIS_AGENTS == set()
        assert THESIS_HANDLER_KEYS == set()

    def test_is_thesis_payload_always_false(self):
        """_is_thesis_payload should return False for any workspace_feature payload.
        All thesis-specific features use task_type=thesis_generation and bypass
        execute_workspace_feature() entirely."""
        test_cases = [
            {"workspace_type": "thesis", "agent": "thesis_writer", "handler_key": "thesis.compile_export"},
            {"workspace_type": "thesis", "agent": "figure_planner", "handler_key": "thesis.figure_generation"},
            {"workspace_type": "thesis", "agent": "deep_research", "handler_key": "thesis.deep_research"},
            {"workspace_type": "thesis", "agent": "librarian", "handler_key": "thesis.literature_management"},
            {"workspace_type": "thesis", "agent": "scout", "handler_key": "thesis.opening_research"},
        ]
        for payload in test_cases:
            assert not _is_thesis_payload(payload), f"Should not detect thesis for {payload}"


class DummyArtifactService:
    """Record artifact creation calls for handler tests."""

    created_artifacts: list[dict] = []

    def __init__(self, db) -> None:
        self.db = db

    async def create(
        self,
        *,
        workspace_id: str,
        type: str,
        content: dict,
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
    ):
        record = {
            "workspace_id": workspace_id,
            "type": type,
            "content": content,
            "title": title,
            "created_by_skill": created_by_skill,
            "parent_artifact_id": parent_artifact_id,
        }
        self.created_artifacts.append(record)
        return SimpleNamespace(
            id=f"artifact-{len(self.created_artifacts)}",
            type=type,
            title=title,
        )


@pytest.mark.asyncio
async def test_copyright_materials_handler_persists_artifact(monkeypatch):
    """The software copyright materials feature should generate a real artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "software_copyright",
        "workspace_name": "AcademiaGPT Desktop",
        "workspace_description": "Academic assistant desktop client",
        "workspace_discipline": "computer_science",
        "workspace_config": {"deployment": "desktop"},
        "feature_id": "copyright_materials",
        "feature_name": "材料准备",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "software_copyright.copyright_materials",
        "params": {
            "version": "V2.0",
            "applicant_name": "Open Research Lab",
            "source_modules": ["登录鉴权", "工作区管理", "成果导出"],
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "software_copyright.copyright_materials"
    assert result["artifacts"] == [
        {
            "id": "artifact-1",
            "type": "copyright_materials",
            "title": "AcademiaGPT Desktop 软著申请材料清单",
        }
    ]

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["workspace_id"] == "ws-1"
    assert artifact["type"] == "copyright_materials"
    assert artifact["title"] == "AcademiaGPT Desktop 软著申请材料清单"
    assert artifact["created_by_skill"] == "software_copyright.copyright_materials"
    assert artifact["content"]["document_type"] == "copyright_materials"
    assert artifact["content"]["software_profile"] == {
        "software_name": "AcademiaGPT Desktop",
        "version": "V2.0",
        "applicant_name": "Open Research Lab",
        "completion_date": "待确认开发完成日期",
        "description": "Academic assistant desktop client",
        "config_snapshot": {"deployment": "desktop"},
    }
    assert len(artifact["content"]["required_materials"]) == 5
    assert artifact["content"]["required_materials"][1]["suggested_modules"] == [
        "登录鉴权",
        "工作区管理",
        "成果导出",
    ]

    assert progress.update.await_count == 3


@pytest.mark.asyncio
async def test_technical_description_handler_persists_artifact(monkeypatch):
    """The software copyright technical description feature should generate a real artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )
    # Mock the service layer to avoid LLM calls
    async def fake_build_technical_description_payload(**kwargs):
        return {
            "document_type": "technical_description",
            "workspace": {
                "id": kwargs.get("workspace_id", ""),
                "name": kwargs.get("workspace_name", ""),
                "description": kwargs.get("workspace_description", ""),
            },
            "software_profile": {
                "software_name": kwargs.get("software_name", ""),
                "version": kwargs.get("version", "V1.0"),
                "core_modules": kwargs.get("core_modules", []),
                "deployment_architecture": kwargs.get("deployment_architecture", "B/S架构"),
                "database_middleware": kwargs.get("database_middleware", []),
                "interface_protocols": kwargs.get("interface_protocols", []),
                "highlights": kwargs.get("highlights", []),
            },
            "generation_mode": "template_fallback",
            "model_id": None,
            "generation_error": "no_generation_model_configured",
            "sections": {
                "system_overview": {
                    "title": "系统概述",
                    "content": f"{kwargs.get('software_name', '')}是一款软件系统。",
                    "source": "template",
                },
                "module_design": {
                    "title": "模块设计",
                    "content": "系统包含核心模块。",
                    "source": "template",
                },
                "data_flow": {
                    "title": "数据流程",
                    "content": "数据流程说明。",
                    "source": "template",
                },
                "deployment_architecture": {
                    "title": "部署架构",
                    "content": "部署架构说明。",
                    "source": "template",
                },
                "security_and_permissions": {
                    "title": "安全与权限",
                    "content": "安全机制说明。",
                    "source": "template",
                },
                "operation_steps": {
                    "title": "操作步骤",
                    "content": "操作步骤说明。",
                    "source": "template",
                },
            },
            "generated_at": "2025-01-01T00:00:00Z",
            "upgrade": {
                "auto_upgrade": True,
                "can_regenerate_with_llm": True,
                "last_error": "no_generation_model_configured",
            },
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.software_copyright.build_technical_description_payload",
        fake_build_technical_description_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-2",
        "workspace_type": "software_copyright",
        "workspace_name": "智能数据分析平台",
        "workspace_description": "企业级数据分析与可视化平台",
        "workspace_discipline": "computer_science",
        "workspace_config": {"deployment": "cloud"},
        "feature_id": "technical_description",
        "feature_name": "技术说明",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "software_copyright.technical_description",
        "params": {
            "software_name": "智能数据分析平台",
            "version": "V2.1",
            "core_modules": ["数据采集", "数据分析", "可视化展示"],
            "deployment_architecture": "微服务架构",
            "database_middleware": ["MySQL", "Redis", "Elasticsearch"],
            "interface_protocols": ["HTTP/REST", "WebSocket"],
            "highlights": ["实时数据分析", "多维度可视化"],
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "software_copyright.technical_description"
    assert result["artifacts"] == [
        {
            "id": "artifact-1",
            "type": "technical_description",
            "title": "智能数据分析平台 技术说明书",
        }
    ]

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["workspace_id"] == "ws-2"
    assert artifact["type"] == "technical_description"
    assert artifact["title"] == "智能数据分析平台 技术说明书"
    assert artifact["created_by_skill"] == "software_copyright.technical_description"
    assert artifact["content"]["document_type"] == "technical_description"
    assert artifact["content"]["software_profile"]["software_name"] == "智能数据分析平台"
    assert artifact["content"]["software_profile"]["version"] == "V2.1"
    assert artifact["content"]["software_profile"]["deployment_architecture"] == "微服务架构"
    assert "sections" in artifact["content"]
    assert "system_overview" in artifact["content"]["sections"]

    assert progress.update.await_count == 3


@pytest.mark.asyncio
async def test_patent_outline_handler_persists_artifact(monkeypatch):
    """Patent outline feature should persist a patent_outline artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_patent_outline_payload(**kwargs):
        return {
            "document_type": "patent_outline",
            "workspace": {
                "id": kwargs.get("workspace_id", ""),
                "name": kwargs.get("workspace_name", ""),
            },
            "generation_mode": "template_fallback",
            "sections": [
                {"id": "technical_field", "title": "技术领域"},
                {"id": "background", "title": "背景技术"},
            ],
            "claims_draft": {
                "independent_claims": [{"id": "claim_1", "text": "一种系统..."}],
                "dependent_claims": [],
            },
            "evidence_points_needed": ["实验数据", "性能对比结果"],
            "generated_at": "2026-03-13T00:00:00Z",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.patent.build_patent_outline_payload",
        fake_build_patent_outline_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-pat-1",
        "workspace_type": "patent",
        "workspace_name": "智能调度系统专利",
        "workspace_description": "基于强化学习的调度优化",
        "feature_id": "patent_outline",
        "feature_name": "专利框架",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "patent.patent_outline",
        "params": {
            "innovation_description": "通过动态策略实现低延迟调度",
            "technical_field": "计算机系统优化",
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["handler_key"] == "patent.patent_outline"
    assert result["refresh_targets"] == ["artifacts"]
    assert result["artifacts"] == [
        {
            "id": "artifact-1",
            "type": "patent_outline",
            "title": "智能调度系统专利 - 专利说明书框架",
        }
    ]

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["workspace_id"] == "ws-pat-1"
    assert artifact["type"] == "patent_outline"
    assert artifact["created_by_skill"] == "patent.patent_outline"
    assert artifact["content"]["document_type"] == "patent_outline"
    assert artifact["content"]["generation_mode"] == "template_fallback"

    assert progress.update.await_count == 3


@pytest.mark.asyncio
async def test_prior_art_search_handler_persists_artifact(monkeypatch):
    """Prior art search feature should persist a prior_art_report artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_prior_art_search_payload(**kwargs):
        return {
            "document_type": "prior_art_report",
            "workspace": {
                "id": kwargs.get("workspace_id", ""),
                "name": kwargs.get("workspace_name", ""),
            },
            "generation_mode": "template_fallback",
            "keywords": kwargs.get("keywords", []),
            "ipc_codes": kwargs.get("ipc_codes", []),
            "time_range": kwargs.get("time_range", "近5年"),
            "comparison_table": [
                {
                    "id": "ref_1",
                    "title": "调度优化相关专利",
                    "patent_number": "CNXXXXXX",
                }
            ],
            "novelty_risks": [{"id": "risk_1", "level": "high", "description": "核心流程类似"}],
            "avoidance_suggestions": ["强调动态策略更新机制"],
            "generated_at": "2026-03-13T00:00:00Z",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.patent.build_prior_art_search_payload",
        fake_build_prior_art_search_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-pat-2",
        "workspace_type": "patent",
        "workspace_name": "智能调度系统专利",
        "workspace_description": "基于强化学习的调度优化",
        "feature_id": "prior_art_search",
        "feature_name": "现有技术检索",
        "agent": "scout",
        "agent_label": "Scout",
        "handler_key": "patent.prior_art_search",
        "params": {
            "keywords": ["调度优化", "强化学习"],
            "ipc_codes": ["G06F"],
            "time_range": "近5年",
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["handler_key"] == "patent.prior_art_search"
    assert result["refresh_targets"] == ["artifacts"]
    assert result["artifacts"] == [
        {
            "id": "artifact-1",
            "type": "prior_art_report",
            "title": "智能调度系统专利 - 现有技术检索报告",
        }
    ]

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["workspace_id"] == "ws-pat-2"
    assert artifact["type"] == "prior_art_report"
    assert artifact["created_by_skill"] == "patent.prior_art_search"
    assert artifact["content"]["document_type"] == "prior_art_report"
    assert artifact["content"]["keywords"] == ["调度优化", "强化学习"]

    assert progress.update.await_count == 3


@pytest.mark.asyncio
async def test_sci_literature_search_handler_persists_artifact(monkeypatch):
    """SCI literature search should persist a literature_search_results artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_literature_search_payload(**kwargs):
        return {
            "query": kwargs.get("query"),
            "discipline": kwargs.get("discipline", ""),
            "papers": [{"title": "Sample Paper", "year": 2024}],
            "top_hits": [{"title": "Sample Paper", "reason": "high relevance"}],
            "filters": {"year_range": {"min": 2020, "max": 2025}},
            "summary": "Sample summary",
            "search_strategy": "template_fallback",
            "generated_at": "2026-03-13T00:00:00Z",
            "model_id": None,
            "generation_error": "no_generation_model_configured",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.sci.build_literature_search_payload",
        fake_build_literature_search_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-sci-1",
        "workspace_type": "sci",
        "workspace_name": "SCI Workspace",
        "workspace_description": "Computer vision",
        "workspace_discipline": "computer_science",
        "feature_id": "literature_search",
        "feature_name": "文献检索",
        "agent": "scout",
        "agent_label": "Scout",
        "handler_key": "sci.literature_search",
        "params": {"query": "vision transformer"},
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "sci.literature_search"
    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "literature_search_results"
    assert artifact["content"]["query"] == "vision transformer"
    assert artifact["content"]["search_strategy"] == "template_fallback"


@pytest.mark.asyncio
async def test_sci_paper_analysis_handler_persists_artifact(monkeypatch):
    """SCI paper analysis should persist a paper_analysis artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_paper_analysis_payload(**kwargs):
        return {
            "paper_id": kwargs.get("paper_id"),
            "paper_title": kwargs.get("paper_title", "Sample Paper"),
            "analysis_mode": "template_fallback",
            "sections": {
                "methodology": {"title": "研究方法", "content": "模板内容", "key_points": []},
                "experiments": {"title": "实验设计", "content": "模板内容", "key_points": []},
                "conclusions": {"title": "研究结论", "content": "模板内容", "key_points": []},
                "innovations": {"title": "创新点", "content": "模板内容", "key_points": []},
            },
            "summary": "Sample analysis",
            "generated_at": "2026-03-13T00:00:00Z",
            "model_id": None,
            "generation_error": "no_generation_model_configured",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.sci.build_paper_analysis_payload",
        fake_build_paper_analysis_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-sci-2",
        "workspace_type": "sci",
        "workspace_name": "SCI Workspace",
        "workspace_description": "NLP",
        "workspace_discipline": "computer_science",
        "feature_id": "paper_analysis",
        "feature_name": "论文分析",
        "agent": "analyst",
        "agent_label": "Analyst",
        "handler_key": "sci.paper_analysis",
        "params": {"paper_title": "Attention Is All You Need"},
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "sci.paper_analysis"
    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "paper_analysis"
    assert artifact["content"]["paper_title"] == "Attention Is All You Need"
    assert artifact["content"]["analysis_mode"] == "template_fallback"


@pytest.mark.asyncio
async def test_sci_writing_handler_persists_artifact(monkeypatch):
    """SCI writing should persist a paper_draft artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_sci_writing_payload(**kwargs):
        return {
            "document_type": "paper_draft",
            "paper_title": kwargs.get("paper_title"),
            "section_type": kwargs.get("section_type"),
            "section_title": "引言",
            "target_words": kwargs.get("target_words"),
            "word_count": 820,
            "writing_mode": "template_fallback",
            "content": "这是论文引言草稿模板内容。",
            "generated_at": "2026-03-13T00:00:00Z",
            "model_id": None,
            "generation_error": "no_generation_model_configured",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.sci.build_sci_writing_payload",
        fake_build_sci_writing_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-sci-3",
        "workspace_type": "sci",
        "workspace_name": "SCI Workspace",
        "workspace_description": "Diffusion model paper",
        "workspace_discipline": "computer_science",
        "feature_id": "writing",
        "feature_name": "论文写作",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "sci.writing",
        "params": {
            "paper_title": "Diffusion Models in Vision",
            "section_type": "introduction",
            "target_words": 1200,
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "sci.writing"
    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "paper_draft"
    assert artifact["created_by_skill"] == "sci.writing"
    assert artifact["content"]["paper_title"] == "Diffusion Models in Vision"
    assert artifact["content"]["section_type"] == "introduction"
    assert artifact["content"]["writing_mode"] == "template_fallback"


@pytest.mark.asyncio
async def test_proposal_outline_handler_persists_artifact(monkeypatch):
    """Proposal outline should persist a proposal artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )

    async def fake_build_proposal_outline_payload(**kwargs):
        return {
            "topic": kwargs.get("topic"),
            "proposal_type": kwargs.get("proposal_type", "other"),
            "proposal_type_label": "其他类型",
            "period_months": kwargs.get("period_months", 24),
            "generation_mode": "template_fallback",
            "model_id": None,
            "generation_error": "no_generation_model_configured",
            "sections": [{"id": "basis", "title": "立项依据", "content": "模板内容"}],
            "milestones": [{"phase": "中期", "time": "第12月", "deliverable": "进展报告"}],
            "risks": [{"type": "技术风险", "description": "示例", "mitigation": "示例"}],
            "generated_at": "2026-03-13T00:00:00Z",
        }

    monkeypatch.setattr(
        "src.workspace_features.handlers.proposal.build_proposal_outline_payload",
        fake_build_proposal_outline_payload,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-proposal-1",
        "workspace_type": "proposal",
        "workspace_name": "项目申报",
        "workspace_description": "智能制造项目",
        "workspace_discipline": "engineering",
        "feature_id": "proposal_outline",
        "feature_name": "申报书大纲",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "proposal.proposal_outline",
        "params": {
            "topic": "智能制造关键技术研究",
            "proposal_type": "provincial",
            "period_months": 24,
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "proposal.proposal_outline"
    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "proposal"
    assert artifact["content"]["topic"] == "智能制造关键技术研究"
    assert artifact["content"]["generation_mode"] == "template_fallback"


class TestThesisActionRouting:
    """Tests for thesis workflow action routing."""

    @pytest.mark.asyncio
    async def test_default_action_is_write_all(self):
        """Default action should call the full thesis workflow."""
        payload = {"workspace_id": "ws-1"}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.run_thesis_workflow_request") as mock_run:
            mock_run.return_value = {"status": "completed"}
            await execute_thesis_generation(payload, progress)
            # Default should call the thesis workflow (write_all behavior)
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_outline_action(self):
        """generate_outline action should route to outline-only handler."""
        payload = {"workspace_id": "ws-1", "action": "generate_outline", "params": {"topic": "test"}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.generate_outline_only") as mock_outline:
            mock_outline.return_value = {"message": "Outline generated"}
            result = await execute_thesis_generation(payload, progress)
            mock_outline.assert_called_once_with(payload, progress)
            assert result["message"] == "Outline generated"

    @pytest.mark.asyncio
    async def test_write_chapter_action(self):
        """write_chapter action should route to single chapter handler."""
        payload = {"workspace_id": "ws-1", "action": "write_chapter", "params": {"chapter_index": 1}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.write_single_chapter") as mock_ch:
            mock_ch.return_value = {"message": "Chapter written"}
            result = await execute_thesis_generation(payload, progress)
            mock_ch.assert_called_once_with(payload, progress)
            assert result["message"] == "Chapter written"


@pytest.mark.asyncio
async def test_generate_outline_only_persists_framework_outline(monkeypatch):
    """Outline-only action should persist a framework_outline artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.task.handlers.workspace_feature_handler.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.task.handlers.workspace_feature_handler.ArtifactService",
        DummyArtifactService,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "智能问答系统研究",
        "feature_id": "thesis_writing",
        "feature_name": "论文写作",
        "handler_key": "thesis.thesis_writing",
        "params": {
            "paper_title": "智能问答系统研究",
            "target_words": 20000,
        },
    }

    result = await generate_outline_only(payload, progress)

    assert result["message"] == "大纲已生成"
    assert result["refresh_targets"] == ["artifacts"]
    assert len(result["artifacts"]) == 1
    assert len(result["outline"]["chapters"]) == 5

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "framework_outline"
    assert artifact["workspace_id"] == "ws-1"
    assert artifact["created_by_skill"] == "thesis.thesis_writing"


@pytest.mark.asyncio
async def test_write_single_chapter_persists_thesis_chapter(monkeypatch):
    """Single-chapter action should persist a thesis_chapter artifact."""
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.task.handlers.workspace_feature_handler.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.task.handlers.workspace_feature_handler.ArtifactService",
        DummyArtifactService,
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "thesis_writing",
        "feature_name": "论文写作",
        "handler_key": "thesis.thesis_writing",
        "params": {
            "paper_title": "智能问答系统研究",
            "chapter_index": 1,
            "chapter_title": "相关工作与理论基础",
            "target_words": 3000,
        },
    }

    result = await write_single_chapter(payload, progress)

    assert result["message"] == "第 2 章已生成"
    assert result["refresh_targets"] == ["artifacts"]
    assert len(result["artifacts"]) == 1
    assert result["chapter"]["index"] == 1

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "thesis_chapter"
    assert artifact["workspace_id"] == "ws-1"
    assert artifact["content"]["chapter_index"] == 1
