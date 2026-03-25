"""Tests for ThreadState and academic extensions.

Tests the AgentState-based ThreadState with:
- deer-flow base fields (sandbox, thread_data, title, artifacts, todos, uploaded_files, viewed_images)
- Academic fields (workspace_id, discipline, etc.) as NotRequired
- Custom reducers (merge_artifacts, merge_academic_artifacts, merge_cited_papers, merge_viewed_images)
- Dict-like access patterns (replacing Pydantic .attribute access)
"""

from src.agents.thread_state import (
    AcademicArtifact,
    AgentState,
    SandboxState,
    ThreadDataState,
    ThreadState,
    ViewedImageData,
    merge_academic_artifacts,
    merge_artifacts,
    merge_cited_papers,
    merge_viewed_images,
)


# ============ ThreadState Inheritance & Type Tests ============


class TestThreadStateInheritance:
    """Verify ThreadState inherits from AgentState (TypedDict)."""

    def test_inherits_from_agent_state(self):
        """ThreadState must extend AgentState (TypedDict with add_messages)."""
        # TypedDict inheritance is structural, not nominal at runtime.
        # Verify ThreadState has AgentState's key field (messages with add_messages).
        assert "messages" in ThreadState.__annotations__
        # Verify the AgentState base type is in the MRO or orig_bases
        orig_bases = getattr(ThreadState, "__orig_bases__", ())
        assert AgentState in orig_bases

    def test_is_dict_like(self):
        """ThreadState instances are plain dicts."""
        state = ThreadState(messages=[])
        assert isinstance(state, dict)

    def test_messages_field_exists(self):
        """ThreadState has messages field from AgentState."""
        assert "messages" in ThreadState.__annotations__

    def test_basic_creation(self):
        """ThreadState can be created with just messages."""
        state = ThreadState(messages=[])
        assert state["messages"] == []

    def test_creation_with_academic_fields(self):
        """ThreadState can be created with academic fields."""
        state = ThreadState(
            messages=[],
            workspace_id="ws-1",
            workspace_type="sci",
            discipline="computer_science",
        )
        assert state["workspace_id"] == "ws-1"
        assert state["workspace_type"] == "sci"
        assert state["discipline"] == "computer_science"

    def test_dict_access_patterns(self):
        """Dict-like get/set access works."""
        state = ThreadState(messages=[], workspace_id="ws-1")
        # .get() access
        assert state.get("workspace_id") == "ws-1"
        assert state.get("nonexistent") is None
        assert state.get("nonexistent", "default") == "default"
        # [] assignment
        state["literature_context"] = "some context"
        assert state["literature_context"] == "some context"

    def test_optional_fields_default_to_absent(self):
        """NotRequired fields are absent when not provided."""
        state = ThreadState(messages=[])
        assert "workspace_id" not in state
        assert "discipline" not in state
        assert "sandbox" not in state
        assert "title" not in state
        assert state.get("workspace_id") is None
        assert state.get("discipline") is None


# ============ Deer-flow Base Fields Tests ============


class TestDeerFlowBaseFields:
    """Test deer-flow infrastructure fields."""

    def test_sandbox_field(self):
        """Test sandbox field with SandboxState."""
        state = ThreadState(
            messages=[],
            sandbox=SandboxState(sandbox_id="local"),
        )
        assert state["sandbox"]["sandbox_id"] == "local"

    def test_thread_data_field(self):
        """Test thread_data field with ThreadDataState."""
        state = ThreadState(
            messages=[],
            thread_data=ThreadDataState(
                workspace_path="/tmp/ws",
                uploads_path="/tmp/up",
                outputs_path="/tmp/out",
            ),
        )
        assert state["thread_data"]["workspace_path"] == "/tmp/ws"

    def test_title_field(self):
        """Test title field."""
        state = ThreadState(messages=[], title="My Thread")
        assert state["title"] == "My Thread"

    def test_todos_field(self):
        """Test todos field."""
        state = ThreadState(messages=[], todos=[{"task": "do something"}])
        assert len(state["todos"]) == 1

    def test_uploaded_files_field(self):
        """Test uploaded_files field."""
        state = ThreadState(
            messages=[],
            uploaded_files=[{"name": "paper.pdf", "path": "/tmp/paper.pdf"}],
        )
        assert len(state["uploaded_files"]) == 1

    def test_viewed_images_field(self):
        """Test viewed_images field with ViewedImageData."""
        state = ThreadState(
            messages=[],
            viewed_images={
                "/img/test.png": ViewedImageData(base64="abc123", mime_type="image/png"),
            },
        )
        assert state["viewed_images"]["/img/test.png"]["base64"] == "abc123"


# ============ Academic Fields Tests ============


class TestAcademicFields:
    """Test academic-specific fields."""

    def test_workspace_config_field(self):
        """Test workspace_config field (formerly _workspace_config PrivateAttr)."""
        state = ThreadState(
            messages=[],
            workspace_config={"citation_style": "APA"},
        )
        assert state["workspace_config"]["citation_style"] == "APA"

    def test_literature_context_field(self):
        """Test literature_context field (formerly _literature_context PrivateAttr)."""
        state = ThreadState(
            messages=[],
            literature_context="Some literature context",
        )
        assert state["literature_context"] == "Some literature context"

    def test_knowledge_context_field(self):
        """Test knowledge_context field (formerly _knowledge_context PrivateAttr)."""
        state = ThreadState(
            messages=[],
            knowledge_context="Knowledge context string",
        )
        assert state["knowledge_context"] == "Knowledge context string"

    def test_memory_context_field(self):
        """Test long-term memory_context field."""
        state = ThreadState(
            messages=[],
            memory_context="<academic_memory>偏好 IEEE</academic_memory>",
        )
        assert state["memory_context"] == "<academic_memory>偏好 IEEE</academic_memory>"

    def test_discipline_norms_field(self):
        """Test discipline_norms field (formerly _discipline_norms PrivateAttr)."""
        norms = {"citation_style": "IEEE", "writing_style": "technical"}
        state = ThreadState(messages=[], discipline_norms=norms)
        assert state["discipline_norms"]["citation_style"] == "IEEE"

    def test_current_skill_field(self):
        """Test current_skill field."""
        state = ThreadState(messages=[], current_skill="deep-research")
        assert state["current_skill"] == "deep-research"

    def test_subagent_tasks_field(self):
        """Test subagent_tasks field."""
        state = ThreadState(
            messages=[],
            subagent_tasks={"task-1": {"status": "running"}},
        )
        assert state["subagent_tasks"]["task-1"]["status"] == "running"


# ============ AcademicArtifact Tests ============


class TestAcademicArtifact:
    """Test AcademicArtifact Pydantic model."""

    def test_creation(self):
        """Test basic artifact creation."""
        artifact = AcademicArtifact(
            id="a1",
            workspace_id="ws1",
            type="research_idea",
            content={"title": "Test"},
            created_by_skill="deep-research",
        )
        assert artifact.type == "research_idea"
        assert artifact.created_by_skill == "deep-research"
        assert artifact.created_at is not None

    def test_creation_with_defaults(self):
        """Test artifact creation with default values."""
        artifact = AcademicArtifact(
            id="a2",
            workspace_id="ws1",
            type="methodology",
            content={"steps": [1, 2, 3]},
        )
        assert artifact.created_by_skill is None
        assert artifact.created_at is not None

    def test_content_is_dict(self):
        """Test that content field is a dict."""
        artifact = AcademicArtifact(
            id="a3",
            workspace_id="ws1",
            type="paper_draft",
            content={"text": "some paper", "sections": ["intro", "conclusion"]},
        )
        assert isinstance(artifact.content, dict)
        assert artifact.content["text"] == "some paper"


# ============ Reducer Tests ============


class TestMergeArtifacts:
    """Test merge_artifacts reducer for string paths."""

    def test_merge_deduplicates(self):
        """Test deduplication of artifact paths."""
        existing = ["/path/a", "/path/b"]
        new = ["/path/b", "/path/c"]
        result = merge_artifacts(existing, new)
        assert result == ["/path/a", "/path/b", "/path/c"]

    def test_merge_with_none_existing(self):
        """Test merge when existing is None."""
        result = merge_artifacts(None, ["/path/a"])
        assert result == ["/path/a"]

    def test_merge_with_none_new(self):
        """Test merge when new is None."""
        result = merge_artifacts(["/path/a"], None)
        assert result == ["/path/a"]

    def test_merge_both_none(self):
        """Test merge when both are None."""
        result = merge_artifacts(None, None)
        assert result == []

    def test_merge_preserves_order(self):
        """Test that merge preserves insertion order."""
        existing = ["/path/a", "/path/b"]
        new = ["/path/c"]
        result = merge_artifacts(existing, new)
        assert result == ["/path/a", "/path/b", "/path/c"]


class TestMergeAcademicArtifacts:
    """Test merge_academic_artifacts reducer."""

    def test_deduplicates_by_id(self):
        """Test deduplication by artifact ID (new takes precedence)."""
        existing = [
            AcademicArtifact(id="a1", workspace_id="ws1", type="idea", content={"v": 1}),
            AcademicArtifact(id="a2", workspace_id="ws1", type="method", content={"v": 1}),
        ]
        new = [
            AcademicArtifact(id="a2", workspace_id="ws1", type="method", content={"v": 2}),
            AcademicArtifact(id="a3", workspace_id="ws1", type="abstract", content={"v": 1}),
        ]
        result = merge_academic_artifacts(existing, new)
        assert len(result) == 3
        # a2 should be updated (new takes precedence)
        a2 = next(a for a in result if a.id == "a2")
        assert a2.content == {"v": 2}

    def test_with_none_existing(self):
        """Test merge when existing is None."""
        new = [AcademicArtifact(id="a1", workspace_id="ws1", type="idea", content={})]
        result = merge_academic_artifacts(None, new)
        assert len(result) == 1

    def test_with_none_new(self):
        """Test merge when new is None."""
        existing = [AcademicArtifact(id="a1", workspace_id="ws1", type="idea", content={})]
        result = merge_academic_artifacts(existing, None)
        assert len(result) == 1

    def test_both_none(self):
        """Test merge when both are None."""
        result = merge_academic_artifacts(None, None)
        assert result == []


class TestMergeCitedPapers:
    """Test merge_cited_papers reducer."""

    def test_deduplicates(self):
        """Test deduplication of cited papers."""
        existing = ["doi:10.1", "doi:10.2"]
        new = ["doi:10.2", "doi:10.3"]
        result = merge_cited_papers(existing, new)
        assert result == ["doi:10.1", "doi:10.2", "doi:10.3"]

    def test_with_none_existing(self):
        """Test merge when existing is None."""
        result = merge_cited_papers(None, ["doi:10.1"])
        assert result == ["doi:10.1"]

    def test_with_none_new(self):
        """Test merge when new is None."""
        result = merge_cited_papers(["doi:10.1"], None)
        assert result == ["doi:10.1"]

    def test_both_none(self):
        """Test merge when both are None."""
        result = merge_cited_papers(None, None)
        assert result == []


class TestMergeViewedImages:
    """Test merge_viewed_images reducer."""

    def test_merges_dicts(self):
        """Test merging image dictionaries."""
        existing = {"img1.png": ViewedImageData(base64="a", mime_type="image/png")}
        new = {"img2.png": ViewedImageData(base64="b", mime_type="image/png")}
        result = merge_viewed_images(existing, new)
        assert len(result) == 2
        assert "img1.png" in result
        assert "img2.png" in result

    def test_empty_dict_clears(self):
        """Test that empty dict clears all images."""
        existing = {"img1.png": ViewedImageData(base64="a", mime_type="image/png")}
        result = merge_viewed_images(existing, {})
        assert result == {}

    def test_new_overrides_existing(self):
        """Test that new values override existing for same keys."""
        existing = {"img1.png": ViewedImageData(base64="old", mime_type="image/png")}
        new = {"img1.png": ViewedImageData(base64="new", mime_type="image/png")}
        result = merge_viewed_images(existing, new)
        assert result["img1.png"]["base64"] == "new"

    def test_with_none_existing(self):
        """Test merge when existing is None."""
        new = {"img1.png": ViewedImageData(base64="a", mime_type="image/png")}
        result = merge_viewed_images(None, new)
        assert len(result) == 1

    def test_with_none_new(self):
        """Test merge when new is None."""
        existing = {"img1.png": ViewedImageData(base64="a", mime_type="image/png")}
        result = merge_viewed_images(existing, None)
        assert len(result) == 1

    def test_both_none(self):
        """Test merge when both are None."""
        result = merge_viewed_images(None, None)
        assert result == {}


# ============ Supporting TypedDict Tests ============


class TestSupportingTypes:
    """Test supporting TypedDict types."""

    def test_sandbox_state(self):
        """Test SandboxState creation."""
        sandbox = SandboxState(sandbox_id="local")
        assert sandbox["sandbox_id"] == "local"

    def test_thread_data_state(self):
        """Test ThreadDataState creation."""
        td = ThreadDataState(
            workspace_path="/ws",
            uploads_path="/up",
            outputs_path="/out",
        )
        assert td["workspace_path"] == "/ws"

    def test_viewed_image_data(self):
        """Test ViewedImageData creation."""
        vid = ViewedImageData(base64="abc", mime_type="image/png")
        assert vid["base64"] == "abc"
        assert vid["mime_type"] == "image/png"


# ============ Migration Pattern Tests ============


class TestMigrationPatterns:
    """Verify dict-based access patterns work correctly (replacing old Pydantic patterns)."""

    def test_get_replaces_attribute_access(self):
        """state.get('field') replaces state.field for optional fields."""
        state = ThreadState(messages=[], workspace_id="ws1")
        assert state.get("workspace_id") == "ws1"

    def test_bracket_replaces_set_context(self):
        """state['key'] = val replaces state.set_context('key', val)."""
        state = ThreadState(messages=[])
        state["literature_context"] = "context value"
        assert state["literature_context"] == "context value"

    def test_get_replaces_get_context(self):
        """state.get('key') replaces state.get_context('key')."""
        state = ThreadState(messages=[], knowledge_context="knowledge")
        assert state.get("knowledge_context") == "knowledge"

    def test_dict_state_replaces_model_dump(self):
        """dict(state) or {**state, ...} replaces state.model_dump()."""
        state = ThreadState(messages=[], workspace_id="ws1")
        d = dict(state)
        assert d["workspace_id"] == "ws1"
        assert d["messages"] == []

    def test_spread_with_updates(self):
        """{**state, 'key': val} works for state updates."""
        state = ThreadState(messages=[], workspace_id="ws1")
        updated = {**state, "discipline": "cs"}
        assert updated["workspace_id"] == "ws1"
        assert updated["discipline"] == "cs"

    def test_state_is_already_dict(self):
        """State is dict-like - no conversion needed for most operations."""
        state = ThreadState(messages=[])
        assert isinstance(state, dict)
        assert list(state.keys()) == ["messages"]
