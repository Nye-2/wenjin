"""Tests for thesis workflow runner."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.thesis.task_storage import (
    ThesisTask,
    InMemoryTaskStorage,
    set_storage,
    get_storage,
)
from src.thesis.workflow.runner import (
    _build_section_plans,
    _build_writing_order,
    run_thesis_workflow,
)
from src.thesis.workflow.state import SectionPlan


@pytest.fixture
def isolated_storage():
    """Use isolated storage for each test."""
    storage = InMemoryTaskStorage()
    set_storage(storage)
    yield storage
    set_storage(None)


class TestBuildSectionPlans:
    """Tests for _build_section_plans function."""

    def test_build_section_plans_from_framework(self):
        """Test converting framework_json to SectionPlan list."""
        framework = {
            "sections": [
                {
                    "index": 1,
                    "title": "Introduction",
                    "purpose": "Introduce the topic",
                    "key_points": ["Background", "Motivation"],
                    "target_words": 1500,
                    "dependencies": [],
                    "literature_needs": ["overview papers"],
                },
                {
                    "index": 2,
                    "title": "Methods",
                    "purpose": "Describe methods",
                    "key_points": ["Algorithm design"],
                    "target_words": 2000,
                    "dependencies": [1],
                    "literature_needs": ["methodology papers"],
                },
            ]
        }

        plans = _build_section_plans(framework)

        assert len(plans) == 2
        assert isinstance(plans[0], SectionPlan)
        assert plans[0].index == 1
        assert plans[0].title == "Introduction"
        assert plans[0].purpose == "Introduce the topic"
        assert plans[0].key_points == ["Background", "Motivation"]
        assert plans[0].target_words == 1500
        assert plans[1].index == 2
        assert plans[1].dependencies == [1]

    def test_build_section_plans_empty_framework(self):
        """Test handling empty framework."""
        framework = {}
        plans = _build_section_plans(framework)
        assert plans == []

    def test_build_section_plans_missing_fields(self):
        """Test handling sections with missing optional fields."""
        framework = {
            "sections": [
                {
                    "index": 1,
                    "title": "Minimal Section",
                }
            ]
        }

        plans = _build_section_plans(framework)

        assert len(plans) == 1
        assert plans[0].index == 1
        assert plans[0].title == "Minimal Section"
        assert plans[0].purpose == ""  # Default
        assert plans[0].key_points == []  # Default
        assert plans[0].target_words == 2000  # Default


class TestBuildWritingOrder:
    """Tests for _build_writing_order function."""

    def test_build_writing_order_simple(self):
        """Test simple writing order based on section indices."""
        plans = [
            SectionPlan(index=1, title="Intro"),
            SectionPlan(index=2, title="Methods"),
            SectionPlan(index=3, title="Results"),
        ]

        order = _build_writing_order(plans)

        assert order == [1, 2, 3]

    def test_build_writing_order_respects_dependencies(self):
        """Test writing order respects dependencies."""
        plans = [
            SectionPlan(index=1, title="Intro", dependencies=[]),
            SectionPlan(index=2, title="Methods", dependencies=[1]),
            SectionPlan(index=3, title="Results", dependencies=[2]),
        ]

        order = _build_writing_order(plans)

        # 1 must come before 2, 2 must come before 3
        assert order.index(1) < order.index(2)
        assert order.index(2) < order.index(3)

    def test_build_writing_order_empty_plans(self):
        """Test handling empty plans list."""
        order = _build_writing_order([])
        assert order == []


class TestRunThesisWorkflow:
    """Tests for run_thesis_workflow async function."""

    @pytest.mark.asyncio
    async def test_run_thesis_workflow_updates_task_status(self, isolated_storage):
        """Test that workflow runner updates task status correctly."""
        # Create a task
        task = ThesisTask(
            task_id="test-task-001",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        # Create request with framework
        request = {
            "workspace_id": "ws-001",
            "paper_title": "Test Thesis",
            "discipline": "计算机科学",
            "abstract_content": "Test abstract",
            "framework_json": {
                "sections": [
                    {
                        "index": 1,
                        "title": "Introduction",
                        "target_words": 1000,
                    }
                ]
            },
        }

        # Create async generator for streaming events (empty for this test)
        async def mock_astream(*args, **kwargs):
            # No events to yield
            return
            yield  # Make this a generator

        # Mock the graph to avoid actual execution
        mock_graph = MagicMock()
        mock_graph.astream = mock_astream
        mock_graph.get_state = MagicMock(return_value=MagicMock(values={
            "final_latex": "\\documentclass{article}",
            "pdf_path": "/output/thesis.pdf",
            "bib_content": "@article{test}",
            "sections": [],
            "progress": 1.0,
            "current_phase": "completed",
        }))

        with patch("src.thesis.workflow.runner.thesis_graph", mock_graph):
            await run_thesis_workflow("test-task-001", request)

        # Verify task was updated
        updated_task = isolated_storage.get_task("test-task-001")
        assert updated_task is not None
        assert updated_task.status == "completed"
        assert updated_task.progress == 1.0
        assert updated_task.latex_content == "\\documentclass{article}"
        assert updated_task.pdf_path == "/output/thesis.pdf"
        assert updated_task.bib_content == "@article{test}"

    @pytest.mark.asyncio
    async def test_run_thesis_workflow_handles_missing_task(self, isolated_storage):
        """Test that runner handles missing task gracefully."""
        request = {
            "workspace_id": "ws-001",
            "paper_title": "Test Thesis",
            "framework_json": {},
        }

        # Should not raise, just return
        await run_thesis_workflow("nonexistent-task", request)

        # Verify no task was created
        assert isolated_storage.get_task("nonexistent-task") is None

    @pytest.mark.asyncio
    async def test_run_thesis_workflow_handles_error(self, isolated_storage):
        """Test that runner sets failed status on error."""
        # Create a task
        task = ThesisTask(
            task_id="test-task-002",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        request = {
            "workspace_id": "ws-001",
            "paper_title": "Test Thesis",
            "framework_json": {
                "sections": [{"index": 1, "title": "Intro"}]
            },
        }

        # Create async generator that raises an error
        async def mock_astream_error(*args, **kwargs):
            raise RuntimeError("Simulated error")
            yield  # Make this a generator

        # Mock the graph to raise an error
        mock_graph = MagicMock()
        mock_graph.astream = mock_astream_error

        with patch("src.thesis.workflow.runner.thesis_graph", mock_graph):
            await run_thesis_workflow("test-task-002", request)

        # Verify task was marked as failed
        updated_task = isolated_storage.get_task("test-task-002")
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert "Simulated error" in updated_task.error

    @pytest.mark.asyncio
    async def test_run_thesis_workflow_updates_progress_during_execution(
        self, isolated_storage
    ):
        """Test that progress is updated during workflow execution."""
        # Create a task
        task = ThesisTask(
            task_id="test-task-003",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        request = {
            "workspace_id": "ws-001",
            "paper_title": "Test Thesis",
            "framework_json": {
                "sections": [{"index": 1, "title": "Intro"}]
            },
        }

        # Create async generator for streaming events
        async def mock_astream(*args, **kwargs):
            # Simulate streaming events
            yield {"literature_search": {"progress": 0.1, "current_phase": "literature"}}
            yield {"section_writer": {"progress": 0.5, "current_phase": "writing"}}
            yield {"assembler": {"progress": 0.9, "current_phase": "assemble"}}

        mock_graph = MagicMock()
        mock_graph.astream = mock_astream
        mock_graph.get_state = MagicMock(return_value=MagicMock(values={
            "final_latex": "content",
            "pdf_path": "/output/test.pdf",
            "bib_content": "",
            "sections": [],
            "progress": 1.0,
            "current_phase": "completed",
        }))

        with patch("src.thesis.workflow.runner.thesis_graph", mock_graph):
            await run_thesis_workflow("test-task-003", request)

        # Verify final state
        updated_task = isolated_storage.get_task("test-task-003")
        assert updated_task is not None
        assert updated_task.status == "completed"
        assert updated_task.progress == 1.0

    @pytest.mark.asyncio
    async def test_run_thesis_workflow_sets_running_status_at_start(
        self, isolated_storage
    ):
        """Test that status is set to running at the start."""
        # Create a task
        task = ThesisTask(
            task_id="test-task-004",
            workspace_id="ws-001",
            paper_title="Test Thesis",
            status="pending",
        )
        isolated_storage.create_task(task)

        request = {
            "workspace_id": "ws-001",
            "paper_title": "Test Thesis",
            "framework_json": {},
        }

        # Track status updates
        status_history = []

        original_update = isolated_storage.update_task

        def track_update(task_id, updates):
            if "status" in updates:
                status_history.append(updates["status"])
            return original_update(task_id, updates)

        isolated_storage.update_task = track_update

        # Create async generator for streaming events (empty for this test)
        async def mock_astream(*args, **kwargs):
            # No events to yield
            return
            yield  # Make this a generator

        mock_graph = MagicMock()
        mock_graph.astream = mock_astream
        mock_graph.get_state = MagicMock(return_value=MagicMock(values={
            "final_latex": "",
            "pdf_path": "",
            "bib_content": "",
            "sections": [],
            "progress": 1.0,
            "current_phase": "completed",
        }))

        with patch("src.thesis.workflow.runner.thesis_graph", mock_graph):
            await run_thesis_workflow("test-task-004", request)

        # Verify status progression
        assert "running" in status_history
        assert "completed" in status_history
