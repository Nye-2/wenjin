"""Tests for gateway validators.

This module provides comprehensive tests for all validator classes
and utility functions.
"""

import pytest
from pydantic import ValidationError

from src.gateway.validators.artifact import (
    ArtifactIdValidator,
    ArtifactStatus,
    ArtifactType,
    CreateArtifactValidator,
    ListArtifactsQueryValidator,
    UpdateArtifactValidator,
)
from src.gateway.validators.common import (
    sanitize_html,
    validate_email,
    validate_limit,
    validate_page_number,
    validate_password_strength,
    validate_uuid,
)
from src.gateway.validators.paper import (
    AuthorValidator,
    CreatePaperValidator,
    PaperIdValidator,
    PaperSource,
    SearchPapersValidator,
    UpdatePaperValidator,
)
from src.gateway.validators.workspace import (
    AddPaperToWorkspaceValidator,
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
    WorkspaceIdValidator,
    WorkspaceStatus,
    WorkspaceType,
)

# ============ Common Validators Tests ============

class TestValidateUUID:
    """Tests for validate_uuid function."""

    def test_valid_uuid_lowercase(self):
        """Test valid lowercase UUID."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        assert validate_uuid(uuid) == uuid

    def test_valid_uuid_uppercase(self):
        """Test valid uppercase UUID is normalized to lowercase."""
        uuid = "550E8400-E29B-41D4-A716-446655440000"
        assert validate_uuid(uuid) == uuid.lower()

    def test_valid_uuid_mixed_case(self):
        """Test valid mixed case UUID is normalized."""
        uuid = "550e8400-E29B-41d4-A716-446655440000"
        assert validate_uuid(uuid) == uuid.lower()

    def test_invalid_uuid_no_hyphens(self):
        """Test invalid UUID without hyphens."""
        with pytest.raises(ValueError, match="Invalid UUID format"):
            validate_uuid("550e8400e29b41d4a716446655440000")

    def test_invalid_uuid_wrong_format(self):
        """Test invalid UUID with wrong format."""
        with pytest.raises(ValueError, match="Invalid UUID format"):
            validate_uuid("not-a-uuid")

    def test_invalid_uuid_empty_string(self):
        """Test empty string raises error."""
        with pytest.raises(ValueError, match="Invalid UUID format"):
            validate_uuid("")


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_email(self):
        """Test valid email address."""
        assert validate_email("test@example.com") == "test@example.com"

    def test_valid_email_normalized(self):
        """Test email is normalized to lowercase."""
        assert validate_email("Test@Example.COM") == "test@example.com"

    def test_valid_email_with_dots(self):
        """Test valid email with dots in local part."""
        assert validate_email("test.user@example.com") == "test.user@example.com"

    def test_valid_email_with_plus(self):
        """Test valid email with plus sign."""
        assert validate_email("test+tag@example.com") == "test+tag@example.com"

    def test_invalid_email_no_at(self):
        """Test invalid email without @ symbol."""
        with pytest.raises(ValueError, match="Invalid email format"):
            validate_email("testexample.com")

    def test_invalid_email_no_domain(self):
        """Test invalid email without domain."""
        with pytest.raises(ValueError, match="Invalid email format"):
            validate_email("test@")

    def test_invalid_email_no_tld(self):
        """Test invalid email without TLD."""
        with pytest.raises(ValueError, match="Invalid email format"):
            validate_email("test@example")


class TestSanitizeHtml:
    """Tests for sanitize_html function."""

    def test_plain_text(self):
        """Test plain text passes through."""
        assert sanitize_html("Hello World") == "Hello World"

    def test_removes_html_tags(self):
        """Test HTML tags are removed."""
        assert sanitize_html("<p>Hello</p>") == "Hello"

    def test_removes_script_tags(self):
        """Test script tags are removed."""
        assert sanitize_html("<script>alert('xss')</script>Hello") == "alert(&#x27;xss&#x27;)Hello"

    def test_escapes_special_chars(self):
        """Test special characters are escaped."""
        assert "<" not in sanitize_html("<div>test</div>")
        assert ">" not in sanitize_html("<div>test</div>")

    def test_empty_string(self):
        """Test empty string returns empty."""
        assert sanitize_html("") == ""

    def test_whitespace_preserved(self):
        """Test leading/trailing whitespace is stripped."""
        assert sanitize_html("  Hello  ") == "Hello"


class TestValidatePageNumber:
    """Tests for validate_page_number function."""

    def test_valid_page_number(self):
        """Test valid page number."""
        assert validate_page_number(1) == 1
        assert validate_page_number(100) == 100

    def test_invalid_page_zero(self):
        """Test page zero raises error."""
        with pytest.raises(ValueError, match="Page number must be positive"):
            validate_page_number(0)

    def test_invalid_page_negative(self):
        """Test negative page raises error."""
        with pytest.raises(ValueError, match="Page number must be positive"):
            validate_page_number(-1)


class TestValidateLimit:
    """Tests for validate_limit function."""

    def test_valid_limit(self):
        """Test valid limit values."""
        assert validate_limit(10) == 10
        assert validate_limit(1) == 1
        assert validate_limit(100) == 100

    def test_invalid_limit_zero(self):
        """Test limit zero raises error."""
        with pytest.raises(ValueError, match="Limit must be at least 1"):
            validate_limit(0)

    def test_invalid_limit_exceeds_max(self):
        """Test limit exceeding max raises error."""
        with pytest.raises(ValueError, match="Limit cannot exceed 100"):
            validate_limit(101)

    def test_custom_max_limit(self):
        """Test custom max limit."""
        assert validate_limit(50, max_limit=50) == 50
        with pytest.raises(ValueError, match="Limit cannot exceed 50"):
            validate_limit(51, max_limit=50)


class TestValidatePasswordStrength:
    """Tests for validate_password_strength function."""

    def test_valid_password(self):
        """Test valid password passes."""
        assert validate_password_strength("Password123") == "Password123"

    def test_password_too_short(self):
        """Test short password raises error."""
        with pytest.raises(ValueError, match="at least 8 characters"):
            validate_password_strength("Pass1")

    def test_password_no_uppercase(self):
        """Test password without uppercase raises error."""
        with pytest.raises(ValueError, match="uppercase letter"):
            validate_password_strength("password123")

    def test_password_no_lowercase(self):
        """Test password without lowercase raises error."""
        with pytest.raises(ValueError, match="lowercase letter"):
            validate_password_strength("PASSWORD123")

    def test_password_no_digit(self):
        """Test password without digit raises error."""
        with pytest.raises(ValueError, match="at least one digit"):
            validate_password_strength("PasswordOnly")


# ============ Workspace Validators Tests ============

class TestCreateWorkspaceValidator:
    """Tests for CreateWorkspaceValidator."""

    def test_valid_workspace(self):
        """Test valid workspace creation."""
        workspace = CreateWorkspaceValidator(
            name="My Research",
            type=WorkspaceType.SCI,
            discipline="Computer Science",
            description="A research workspace",
        )
        assert workspace.name == "My Research"
        assert workspace.type == WorkspaceType.SCI

    def test_name_sanitization(self):
        """Test name is sanitized."""
        workspace = CreateWorkspaceValidator(
            name="  <b>Test</b>  ",
            type=WorkspaceType.THESIS,
        )
        assert workspace.name == "Test"

    def test_empty_name_raises_error(self):
        """Test empty name raises error."""
        with pytest.raises(ValidationError):
            CreateWorkspaceValidator(name="", type=WorkspaceType.SCI)

    def test_whitespace_only_name_raises_error(self):
        """Test whitespace-only name raises error."""
        with pytest.raises(ValidationError):
            CreateWorkspaceValidator(name="   ", type=WorkspaceType.SCI)

    def test_invalid_workspace_type(self):
        """Test invalid workspace type raises error."""
        with pytest.raises(ValidationError):
            CreateWorkspaceValidator(name="Test", type="invalid_type")

    def test_description_sanitized(self):
        """Test description is sanitized."""
        workspace = CreateWorkspaceValidator(
            name="Test",
            type=WorkspaceType.SCI,
            description="<script>alert('xss')</script>Description",
        )
        assert "<script>" not in workspace.description

    def test_long_name_raises_error(self):
        """Test name exceeding max length raises error."""
        with pytest.raises(ValidationError):
            CreateWorkspaceValidator(name="x" * 300, type=WorkspaceType.SCI)


class TestUpdateWorkspaceValidator:
    """Tests for UpdateWorkspaceValidator."""

    def test_valid_update(self):
        """Test valid workspace update."""
        update = UpdateWorkspaceValidator(name="New Name")
        assert update.name == "New Name"

    def test_partial_update(self):
        """Test partial update with only some fields."""
        update = UpdateWorkspaceValidator(discipline="Physics")
        assert update.discipline == "Physics"
        assert update.name is None

    def test_status_update(self):
        """Test status can be updated."""
        update = UpdateWorkspaceValidator(status=WorkspaceStatus.ARCHIVED)
        assert update.status == WorkspaceStatus.ARCHIVED


class TestAddPaperToWorkspaceValidator:
    """Tests for AddPaperToWorkspaceValidator."""

    def test_valid_add_paper(self):
        """Test valid add paper request."""
        request = AddPaperToWorkspaceValidator(
            notes="Important paper",
            tags=["machine-learning", "nlp"],
            is_primary=True,
        )
        assert request.notes == "Important paper"
        assert len(request.tags) == 2

    def test_tags_limit(self):
        """Test tags limit is enforced."""
        with pytest.raises(ValidationError, match="20 tags"):
            AddPaperToWorkspaceValidator(tags=[f"tag{i}" for i in range(21)])

    def test_empty_request_valid(self):
        """Test empty request is valid (defaults)."""
        request = AddPaperToWorkspaceValidator()
        assert request.notes is None
        assert request.tags is None
        assert request.is_primary is False


class TestWorkspaceIdValidator:
    """Tests for WorkspaceIdValidator."""

    def test_valid_uuid(self):
        """Test valid UUID passes."""
        validator = WorkspaceIdValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000"
        )
        assert validator.workspace_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid(self):
        """Test invalid UUID raises error."""
        with pytest.raises(ValidationError):
            WorkspaceIdValidator(workspace_id="invalid")


# ============ Paper Validators Tests ============

class TestAuthorValidator:
    """Tests for AuthorValidator."""

    def test_valid_author(self):
        """Test valid author."""
        author = AuthorValidator(name="John Doe")
        assert author.name == "John Doe"

    def test_author_with_affiliation(self):
        """Test author with affiliation."""
        author = AuthorValidator(
            name="Jane Smith",
            affiliation="MIT",
            email="jane@mit.edu"
        )
        assert author.affiliation == "MIT"
        assert author.email == "jane@mit.edu"

    def test_invalid_email(self):
        """Test invalid email raises error."""
        with pytest.raises(ValidationError):
            AuthorValidator(name="Test", email="invalid-email")

    def test_empty_name_raises_error(self):
        """Test empty name raises error."""
        with pytest.raises(ValidationError):
            AuthorValidator(name="")


class TestCreatePaperValidator:
    """Tests for CreatePaperValidator."""

    def test_valid_paper(self):
        """Test valid paper creation."""
        paper = CreatePaperValidator(
            title="Attention Is All You Need",
            authors=[{"name": "Vaswani et al."}],
            year=2017,
            venue="NeurIPS",
        )
        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017

    def test_title_sanitization(self):
        """Test title is sanitized."""
        paper = CreatePaperValidator(
            title="  <b>Test Paper</b>  ",
        )
        assert paper.title == "Test Paper"

    def test_doi_validation(self):
        """Test DOI format validation."""
        paper = CreatePaperValidator(
            title="Test",
            doi="10.1234/test.5678",
        )
        assert paper.doi == "10.1234/test.5678"

    def test_invalid_doi(self):
        """Test invalid DOI raises error."""
        with pytest.raises(ValidationError):
            CreatePaperValidator(title="Test", doi="not-a-doi")

    def test_year_range(self):
        """Test year must be in valid range."""
        with pytest.raises(ValidationError):
            CreatePaperValidator(title="Test", year=1700)

        with pytest.raises(ValidationError):
            CreatePaperValidator(title="Test", year=2200)

    def test_empty_title_raises_error(self):
        """Test empty title raises error."""
        with pytest.raises(ValidationError):
            CreatePaperValidator(title="")

    def test_author_validation(self):
        """Test authors are validated."""
        paper = CreatePaperValidator(
            title="Test",
            authors=[
                {"name": "John Doe", "email": "john@example.com"},
                {"name": "Jane Smith"},
            ],
        )
        assert len(paper.authors) == 2

    def test_author_missing_name(self):
        """Test author without name raises error."""
        with pytest.raises(ValidationError):
            CreatePaperValidator(
                title="Test",
                authors=[{"affiliation": "MIT"}],
            )


class TestUpdatePaperValidator:
    """Tests for UpdatePaperValidator."""

    def test_valid_update(self):
        """Test valid paper update."""
        update = UpdatePaperValidator(title="New Title")
        assert update.title == "New Title"

    def test_partial_update(self):
        """Test partial update."""
        update = UpdatePaperValidator(year=2024)
        assert update.year == 2024
        assert update.title is None


class TestSearchPapersValidator:
    """Tests for SearchPapersValidator."""

    def test_valid_search(self):
        """Test valid search request."""
        search = SearchPapersValidator(query="machine learning")
        assert search.query == "machine learning"
        assert search.limit == 10

    def test_custom_limit(self):
        """Test custom limit."""
        search = SearchPapersValidator(query="test", limit=50)
        assert search.limit == 50

    def test_limit_range(self):
        """Test limit must be in range."""
        with pytest.raises(ValidationError):
            SearchPapersValidator(query="test", limit=0)

        with pytest.raises(ValidationError):
            SearchPapersValidator(query="test", limit=200)

    def test_workspace_id_validation(self):
        """Test workspace ID validation."""
        search = SearchPapersValidator(
            query="test",
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert search.workspace_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_workspace_id(self):
        """Test invalid workspace ID raises error."""
        with pytest.raises(ValidationError):
            SearchPapersValidator(query="test", workspace_id="invalid")


class TestPaperIdValidator:
    """Tests for PaperIdValidator."""

    def test_valid_uuid(self):
        """Test valid UUID passes."""
        validator = PaperIdValidator(paper_id="550e8400-e29b-41d4-a716-446655440000")
        assert validator.paper_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid(self):
        """Test invalid UUID raises error."""
        with pytest.raises(ValidationError):
            PaperIdValidator(paper_id="invalid")


# ============ Artifact Validators Tests ============

class TestCreateArtifactValidator:
    """Tests for CreateArtifactValidator."""

    def test_valid_artifact(self):
        """Test valid artifact creation."""
        artifact = CreateArtifactValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            type=ArtifactType.RESEARCH_IDEA,
            title="My Research Idea",
            content={"text": "This is a research idea"},
        )
        assert artifact.title == "My Research Idea"
        assert artifact.type == ArtifactType.RESEARCH_IDEA

    def test_workspace_id_validation(self):
        """Test workspace ID must be valid UUID."""
        with pytest.raises(ValidationError):
            CreateArtifactValidator(
                workspace_id="invalid",
                type=ArtifactType.RESEARCH_IDEA,
                content={"text": "test"},
            )

    def test_empty_content_raises_error(self):
        """Test empty content raises error."""
        with pytest.raises(ValidationError):
            CreateArtifactValidator(
                workspace_id="550e8400-e29b-41d4-a716-446655440000",
                type=ArtifactType.RESEARCH_IDEA,
                content={},
            )

    def test_skill_name_validation(self):
        """Test skill name validation."""
        artifact = CreateArtifactValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            type=ArtifactType.RESEARCH_IDEA,
            content={"text": "test"},
            created_by_skill="my-skill_v2",
        )
        assert artifact.created_by_skill == "my-skill_v2"

    def test_invalid_skill_name(self):
        """Test invalid skill name raises error."""
        with pytest.raises(ValidationError):
            CreateArtifactValidator(
                workspace_id="550e8400-e29b-41d4-a716-446655440000",
                type=ArtifactType.RESEARCH_IDEA,
                content={"text": "test"},
                created_by_skill="invalid skill!",
            )

    def test_parent_artifact_id_validation(self):
        """Test parent artifact ID validation."""
        artifact = CreateArtifactValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            type=ArtifactType.RESEARCH_IDEA,
            content={"text": "test"},
            parent_artifact_id="660e8400-e29b-41d4-a716-446655440000",
        )
        assert artifact.parent_artifact_id == "660e8400-e29b-41d4-a716-446655440000"

    def test_title_sanitization(self):
        """Test title is sanitized."""
        artifact = CreateArtifactValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            type=ArtifactType.RESEARCH_IDEA,
            title="  <b>Title</b>  ",
            content={"text": "test"},
        )
        assert artifact.title == "Title"


class TestUpdateArtifactValidator:
    """Tests for UpdateArtifactValidator."""

    def test_valid_update(self):
        """Test valid artifact update."""
        update = UpdateArtifactValidator(
            title="New Title",
            status=ArtifactStatus.APPROVED,
        )
        assert update.title == "New Title"
        assert update.status == ArtifactStatus.APPROVED

    def test_partial_update(self):
        """Test partial update."""
        update = UpdateArtifactValidator(content={"updated": True})
        assert update.content == {"updated": True}
        assert update.title is None

    def test_empty_content_raises_error(self):
        """Test empty content raises error."""
        with pytest.raises(ValidationError):
            UpdateArtifactValidator(content={})


class TestListArtifactsQueryValidator:
    """Tests for ListArtifactsQueryValidator."""

    def test_valid_query(self):
        """Test valid list query."""
        query = ListArtifactsQueryValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000"
        )
        assert query.limit == 50
        assert query.offset == 0

    def test_pagination_limits(self):
        """Test pagination limit validation."""
        query = ListArtifactsQueryValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            limit=200,
            offset=100,
        )
        assert query.limit == 200

        with pytest.raises(ValidationError):
            ListArtifactsQueryValidator(
                workspace_id="550e8400-e29b-41d4-a716-446655440000",
                limit=201,
            )

    def test_type_filter(self):
        """Test type filter."""
        query = ListArtifactsQueryValidator(
            workspace_id="550e8400-e29b-41d4-a716-446655440000",
            type=ArtifactType.ABSTRACT,
        )
        assert query.type == ArtifactType.ABSTRACT


class TestArtifactIdValidator:
    """Tests for ArtifactIdValidator."""

    def test_valid_uuid(self):
        """Test valid UUID passes."""
        validator = ArtifactIdValidator(artifact_id="550e8400-e29b-41d4-a716-446655440000")
        assert validator.artifact_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid(self):
        """Test invalid UUID raises error."""
        with pytest.raises(ValidationError):
            ArtifactIdValidator(artifact_id="invalid")


# ============ Enum Tests ============

class TestEnums:
    """Tests for various enum types."""

    def test_workspace_type_values(self):
        """Test WorkspaceType enum values."""
        assert WorkspaceType.SCI.value == "sci"
        assert WorkspaceType.THESIS.value == "thesis"
        assert WorkspaceType.PROPOSAL.value == "proposal"
        assert WorkspaceType.GRANT.value == "grant"
        assert WorkspaceType.LITERATURE_REVIEW.value == "literature_review"

    def test_paper_source_values(self):
        """Test PaperSource enum values."""
        assert PaperSource.MANUAL_UPLOAD.value == "manual_upload"
        assert PaperSource.SEMANTIC_SCHOLAR.value == "semantic_scholar"
        assert PaperSource.DOI_IMPORT.value == "doi_import"

    def test_artifact_type_values(self):
        """Test ArtifactType enum values."""
        assert ArtifactType.RESEARCH_IDEA.value == "research_idea"
        assert ArtifactType.METHODOLOGY.value == "methodology"
        assert ArtifactType.ABSTRACT.value == "abstract"

    def test_artifact_status_values(self):
        """Test ArtifactStatus enum values."""
        assert ArtifactStatus.DRAFT.value == "draft"
        assert ArtifactStatus.APPROVED.value == "approved"
        assert ArtifactStatus.ARCHIVED.value == "archived"
