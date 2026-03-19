"""Paper validators for paper-related endpoints.

This module provides Pydantic models for validating paper
creation, update, and query parameters.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import sanitize_html, sanitize_string, validate_uuid


class PaperSource(StrEnum):
    """Valid paper source types."""

    MANUAL_UPLOAD = "manual_upload"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    DOI_IMPORT = "doi_import"
    PDF_UPLOAD = "pdf_upload"
    BIBTEX_IMPORT = "bibtex_import"


class AuthorValidator(BaseModel):
    """Validator for author information."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=500)]
    affiliation: Annotated[str, Field(max_length=200)] | None = None
    email: str | None = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Sanitize author name."""
        sanitized = sanitize_string(v, max_length=500)
        if not sanitized:
            raise ValueError("Author name cannot be empty")
        return sanitize_html(sanitized)

    @field_validator("affiliation")
    @classmethod
    def sanitize_affiliation(cls, v: str | None) -> str | None:
        """Sanitize affiliation field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=200))

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        """Validate email format if provided."""
        if v is None:
            return None
        import re
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        if not email_pattern.match(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class PaperCreatePayloadValidator(BaseModel):
    """Shared validator for paper creation payload fields."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=1, max_length=1000)]
    authors: list[dict[str, Any]] = Field(default_factory=list)
    doi: Annotated[str, Field(max_length=100)] | None = None
    year: int | None = Field(None, ge=1800, le=2100)
    venue: Annotated[str, Field(max_length=500)] | None = None
    abstract: Annotated[str, Field(max_length=50000)] | None = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        """Sanitize paper title."""
        sanitized = sanitize_string(v, max_length=1000)
        if not sanitized:
            raise ValueError("Paper title cannot be empty or whitespace only")
        return sanitize_html(sanitized)

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate authors list."""
        if not v:
            return []
        validated_authors = []
        for author in v:
            if not isinstance(author, dict):
                raise ValueError("Each author must be a dictionary")
            if "name" not in author:
                raise ValueError("Each author must have a 'name' field")
            # Validate individual author
            author_validator = AuthorValidator.model_validate(author)
            validated_authors.append(author_validator.model_dump())
        return validated_authors

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str | None) -> str | None:
        """Validate DOI format if provided."""
        if v is None:
            return None
        import re
        # DOI format: 10.xxxx/xxxxx
        doi_pattern = re.compile(r"^10\.\d{4,}/.+$")
        sanitized = sanitize_string(v, max_length=100)
        if sanitized and not doi_pattern.match(sanitized):
            raise ValueError("Invalid DOI format (expected: 10.xxxx/xxxxx)")
        return sanitized

    @field_validator("venue")
    @classmethod
    def sanitize_venue(cls, v: str | None) -> str | None:
        """Sanitize venue field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=500))

    @field_validator("abstract")
    @classmethod
    def sanitize_abstract(cls, v: str | None) -> str | None:
        """Sanitize abstract field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=50000))


class CreatePaperValidator(PaperCreatePayloadValidator):
    """Validator for paper creation requests."""

    workspace_id: str
    file_path: Annotated[str, Field(max_length=1000)] | None = None
    source: PaperSource = PaperSource.MANUAL_UPLOAD
    external_ids: dict[str, str] | None = None
    citation_count: int | None = Field(None, ge=0)
    reference_count: int | None = Field(None, ge=0)

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID."""
        return validate_uuid(v)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str | None) -> str | None:
        """Validate file path."""
        if v is None:
            return None
        # Basic path sanitization - no directory traversal
        if ".." in v:
            raise ValueError("File path cannot contain '..'")
        return sanitize_string(v, max_length=1000)

    @field_validator("external_ids")
    @classmethod
    def validate_external_ids(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """Validate external IDs dictionary."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("External IDs must be a dictionary")
        # Ensure all keys and values are strings
        return {str(k): str(val) for k, val in v.items()}


class UpdatePaperValidator(BaseModel):
    """Validator for paper update requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    authors: list[dict[str, Any]] | None = None
    year: int | None = Field(None, ge=1800, le=2100)
    venue: Annotated[str, Field(max_length=500)] | None = None
    abstract: Annotated[str, Field(max_length=50000)] | None = None
    citation_count: int | None = Field(None, ge=0)
    reference_count: int | None = Field(None, ge=0)

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str | None) -> str | None:
        """Sanitize paper title."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=1000)
        if not sanitized:
            raise ValueError("Paper title cannot be empty or whitespace only")
        return sanitize_html(sanitized)

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Validate authors list."""
        if v is None:
            return None
        validated_authors = []
        for author in v:
            if not isinstance(author, dict):
                raise ValueError("Each author must be a dictionary")
            if "name" not in author:
                raise ValueError("Each author must have a 'name' field")
            author_validator = AuthorValidator.model_validate(author)
            validated_authors.append(author_validator.model_dump())
        return validated_authors

    @field_validator("venue")
    @classmethod
    def sanitize_venue(cls, v: str | None) -> str | None:
        """Sanitize venue field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=500))

    @field_validator("abstract")
    @classmethod
    def sanitize_abstract(cls, v: str | None) -> str | None:
        """Sanitize abstract field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=50000))


class SearchPapersValidator(BaseModel):
    """Validator for paper search requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: Annotated[str, Field(min_length=1, max_length=500)]
    workspace_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Sanitize search query."""
        sanitized = sanitize_string(v, max_length=500)
        if not sanitized:
            raise ValueError("Search query cannot be empty")
        return sanitize_html(sanitized)

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str | None) -> str | None:
        """Validate workspace ID if provided."""
        if v is None:
            return None
        return validate_uuid(v)


class PaperIdValidator(BaseModel):
    """Validator for paper ID path parameters."""

    paper_id: str

    @field_validator("paper_id")
    @classmethod
    def validate_paper_id(cls, v: str) -> str:
        """Validate paper ID is a valid UUID."""
        return validate_uuid(v)
