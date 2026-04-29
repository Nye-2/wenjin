"""Paper extraction service for Two-Tier extraction pipeline.

This service implements the Two-Tier extraction architecture:
- Tier 1: Engineering extraction (GROBID, PyMuPDF) - instant
- Tier 2: LLM extraction (Haiku, Qwen-Turbo) - seconds

The service handles:
- PDF text and TOC extraction using PyMuPDF
- Structured data extraction and storage
- Section-based navigation support
- Caching to avoid re-processing
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.literature.extraction.pdf_extractor import PDFExtractor
from src.database import Paper, PaperExtraction, PaperSection

logger = logging.getLogger(__name__)

type JsonObject = dict[str, Any]
type TOCEntry = dict[str, Any]
type AcademicEntity = dict[str, str]
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)[\s\.\-:]+(.+)$")


def _coerce_toc_entries(value: object) -> list[TOCEntry]:
    """Normalize a serialized TOC payload into dict entries."""
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _message_content_to_text(content: object) -> str:
    """Convert LangChain message content payloads into a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


class ExtractionError(Exception):
    """Base exception for extraction errors."""
    pass


class FileNotFoundError(ExtractionError):
    """Raised when the PDF file is not found."""
    pass


class ExtractionService:
    """Service for extracting structured data from paper PDFs.

    This service provides the Two-Tier extraction pipeline:
    - Tier 1 (Engineering): Fast extraction using PyMuPDF/GROBID
    - Tier 2 (LLM): Enhanced extraction using LLM models

    All extractions are cached in the database to avoid re-processing.
    """

    # Extraction tier constants
    TIER_ENGINEERING = 1
    TIER_LLM = 2

    # Extraction types
    TYPE_METADATA = "metadata"
    TYPE_FULL_TEXT = "full_text"
    TYPE_TOC = "toc"
    TYPE_SECTIONS = "sections"

    EXTRACTION_MODEL_ENV_KEY = "LLM_EXTRACTION_MODEL"

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self.pdf_extractor = PDFExtractor()
        self._tier2_model_id = self._resolve_tier2_model_id()

    def _resolve_tier2_model_id(self) -> str:
        """Resolve Tier 2 extraction model from env-backed routing."""
        from src.models.router import route_model

        requested = os.environ.get(self.EXTRACTION_MODEL_ENV_KEY, "").strip() or None
        try:
            return route_model(
                requested_model=requested,
                preferred_categories=("llm",),
                allowed_categories=("llm",),
                require_tools=False,
                require_vision=False,
            )
        except Exception:
            logger.warning(
                "Failed to route Tier 2 extraction model (env %s=%s), fallback to default alias",
                self.EXTRACTION_MODEL_ENV_KEY,
                requested or "",
                exc_info=True,
            )
            return "default"

    def _resolve_preprocessed_dir(self, file_path: str) -> Path:
        source = Path(file_path)
        return source.parent / "_preprocessed" / source.stem

    def _load_preprocessed_markdown_documents(self, file_path: str) -> list[str]:
        """Load OCR-generated markdown docs saved by upload preprocessor."""
        preprocessed_dir = self._resolve_preprocessed_dir(file_path)
        if not preprocessed_dir.is_dir():
            return []

        markdown_paths: list[Path] = []
        manifest_path = preprocessed_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                raw_paths = payload.get("markdown_paths")
                if isinstance(raw_paths, list):
                    for item in raw_paths:
                        candidate = Path(str(item or ""))
                        if not candidate.is_absolute():
                            candidate = preprocessed_dir / str(item or "")
                        if candidate.is_file():
                            markdown_paths.append(candidate)
            except Exception:
                logger.warning(
                    "Failed to parse preprocess manifest for %s",
                    file_path,
                    exc_info=True,
                )

        if not markdown_paths:
            markdown_paths = sorted(preprocessed_dir.glob("doc_*.md"))

        documents: list[str] = []
        for path in markdown_paths:
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                logger.warning("Failed to read preprocessed markdown: %s", path, exc_info=True)
                continue
            if text:
                documents.append(text)
        return documents

    def _split_markdown_into_sections(self, markdown_text: str) -> list[dict[str, Any]]:
        """Split markdown text into heading-scoped sections."""
        text = str(markdown_text or "").strip()
        if not text:
            return []

        matches = list(_MARKDOWN_HEADING_RE.finditer(text))
        if not matches:
            return [
                {
                    "title": "Document",
                    "page_start": 1,
                    "page_end": 1,
                    "content": text,
                    "level": 1,
                    "number": "1",
                }
            ]

        sections: list[dict[str, Any]] = []
        for index, match in enumerate(matches):
            raw_title = str(match.group(2) or "").strip()
            if not raw_title:
                continue

            level = len(str(match.group(1) or "#"))
            heading_number: str | None = None
            heading_title = raw_title
            numbered_match = _NUMBERED_HEADING_RE.match(raw_title)
            if numbered_match:
                heading_number = str(numbered_match.group(1) or "").strip() or None
                heading_title = str(numbered_match.group(2) or "").strip() or raw_title

            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if not content:
                continue

            sections.append(
                {
                    "title": heading_title,
                    "page_start": 1,
                    "page_end": 1,
                    "content": content,
                    "level": max(level, 1),
                    "number": heading_number,
                }
            )

        return sections or [
            {
                "title": "Document",
                "page_start": 1,
                "page_end": 1,
                "content": text,
                "level": 1,
                "number": "1",
            }
        ]

    def _build_toc_from_sections(
        self,
        sections: list[dict[str, Any]],
    ) -> list[TOCEntry]:
        toc: list[TOCEntry] = []
        for index, section in enumerate(sections, 1):
            entry: TOCEntry = {
                "title": str(section.get("title") or "").strip() or f"Section {index}",
                "page": int(section.get("page_start") or 1),
                "level": int(section.get("level") or 1),
            }
            number = str(section.get("number") or "").strip()
            if number:
                entry["number"] = number
            toc.append(entry)
        return toc

    def _build_section_mapping(
        self,
        toc: list[TOCEntry],
        sections: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for index, section in enumerate(sections):
            section_path = self._generate_section_path(index, toc)
            mapping[section_path] = {
                "title": str(section.get("title") or ""),
                "content": str(section.get("content") or ""),
                "level": int(section.get("level") or 1),
                "page_start": int(section.get("page_start") or 1),
                "page_end": int(section.get("page_end") or 1),
            }
        return mapping

    async def extract_paper(
        self,
        paper_id: str,
        file_path: str,
        tier: int = 1,
    ) -> PaperExtraction:
        """Extract structured data from a paper PDF.

        Args:
            paper_id: UUID of the paper
            file_path: Path to the PDF file
            tier: Extraction tier (1=engineering, 2=LLM)

        Returns:
            PaperExtraction record with extracted data

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ExtractionError: If extraction fails
        """
        start_time = time.time()

        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Check for existing extraction at this tier
        existing = await self.get_extraction(paper_id, tier)
        if existing:
            logger.info(
                "Found existing %s extraction for paper %s",
                f"Tier {tier}",
                paper_id,
            )
            return existing

        try:
            if tier == self.TIER_ENGINEERING:
                extraction = await self._extract_tier1(paper_id, file_path)
            elif tier == self.TIER_LLM:
                extraction = await self._extract_tier2(paper_id, file_path)
            else:
                raise ExtractionError(f"Invalid extraction tier: {tier}")

            # Record processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            extraction.processing_time_ms = processing_time_ms

            await self.db.commit()
            await self.db.refresh(extraction)

            logger.info(
                "Completed Tier %d extraction for paper %s in %dms",
                tier,
                paper_id,
                processing_time_ms,
            )

            return extraction

        except Exception as e:
            await self.db.rollback()
            logger.error("Extraction failed for paper %s: %s", paper_id, e)
            raise ExtractionError(f"Extraction failed: {e}") from e

    async def _extract_tier1(
        self,
        paper_id: str,
        file_path: str,
    ) -> PaperExtraction:
        """Perform Tier 1 (Engineering) extraction.

        Uses PyMuPDF for fast extraction of:
        - Metadata (title, authors, page count)
        - Table of Contents
        - Full text content

        Args:
            paper_id: UUID of the paper
            file_path: Path to the PDF file

        Returns:
            PaperExtraction record with Tier 1 data
        """
        # Extract metadata
        metadata = self.pdf_extractor.extract_metadata(file_path)
        markdown_documents = self._load_preprocessed_markdown_documents(file_path)

        if markdown_documents:
            full_text = "\n\n".join(markdown_documents)
            sections = self._split_markdown_into_sections(full_text)
            toc = self._build_toc_from_sections(sections)
            model_used = "layout_parsing_markdown"
        else:
            # Fallback: parse directly from PDF
            toc = self.pdf_extractor.extract_toc(file_path)
            sections = self.pdf_extractor.split_into_sections(file_path, toc)
            full_text = "\n\n".join(
                f"## {s['title']}\n{s['content']}"
                for s in sections
            ) if sections else ""
            model_used = "pymupdf"

        # Build structured data
        structured_data = {
            "metadata": metadata,
            "toc": toc,
            "full_text": full_text,
            "section_count": len(sections),
            "page_count": metadata.get("page_count", 0),
            "sections": self._build_section_mapping(toc, sections),
            "text_source": "markdown" if markdown_documents else "pdf",
        }
        if markdown_documents:
            structured_data["markdown_docs_count"] = len(markdown_documents)

        # Create extraction record
        extraction = PaperExtraction(
            paper_id=paper_id,
            tier=self.TIER_ENGINEERING,
            extraction_type=self.TYPE_FULL_TEXT,
            structured_data=structured_data,
            model_used=model_used,
        )
        self.db.add(extraction)

        return extraction

    async def _extract_tier2(
        self,
        paper_id: str,
        file_path: str,
    ) -> PaperExtraction:
        """Perform Tier 2 (LLM) extraction.

        Uses LLM models (Haiku, Qwen-Turbo) for enhanced extraction:
        - Improved metadata extraction
        - Section summarization
        - Key concepts extraction
        - Citation context extraction

        This tier depends on Tier 1 extraction being available.

        Args:
            paper_id: UUID of the paper
            file_path: Path to the PDF file

        Returns:
            PaperExtraction record with Tier 2 data
        """
        # Get Tier 1 extraction as base
        tier1 = await self.get_extraction(paper_id, self.TIER_ENGINEERING)
        if not tier1:
            # Run Tier 1 first if not available
            tier1 = await self._extract_tier1(paper_id, file_path)

        base_data = (
            dict(tier1.structured_data)
            if isinstance(tier1.structured_data, dict)
            else {}
        )
        full_text_value = base_data.get("full_text", "")
        full_text = full_text_value if isinstance(full_text_value, str) else ""
        toc = _coerce_toc_entries(base_data.get("toc", []))

        # LLM-based extraction (graceful — failures produce empty fields)
        section_summaries: dict[str, str] = {}
        key_concepts: list[str] = []
        entities: list[AcademicEntity] = []

        if full_text:
            try:
                section_summaries = await self._extract_section_summaries(
                    full_text, toc,
                )
            except Exception:
                logger.warning(
                    "Section summary extraction failed for paper %s",
                    paper_id,
                )

            try:
                key_concepts = await self._extract_key_concepts(full_text)
            except Exception:
                logger.warning(
                    "Key concept extraction failed for paper %s",
                    paper_id,
                )

            try:
                entities = await self._extract_entities(full_text)
            except Exception:
                logger.warning(
                    "Entity extraction failed for paper %s",
                    paper_id,
                )

        # Enhanced structured data
        enhanced_data = {
            **base_data,
            "llm_enhanced": True,
            "section_summaries": section_summaries,
            "key_concepts": key_concepts,
            "entities": entities,
        }

        # Create extraction record
        extraction = PaperExtraction(
            paper_id=paper_id,
            tier=self.TIER_LLM,
            extraction_type=self.TYPE_FULL_TEXT,
            structured_data=enhanced_data,
            model_used=self._tier2_model_id,
        )
        self.db.add(extraction)

        return extraction

    # ------------------------------------------------------------------
    # Tier 2 LLM helper methods
    # ------------------------------------------------------------------

    def _get_llm(self) -> BaseChatModel | None:
        """Get LLM instance for Tier 2 extraction.

        Attempts to create the configured fast extraction model via the
        project's ``create_chat_model`` factory. Returns ``None`` when no
        LLM can be created, allowing callers to degrade gracefully.
        """
        try:
            from src.models.factory import create_chat_model

            return create_chat_model(self._tier2_model_id, temperature=0)
        except Exception:
            logger.warning(
                "No LLM available for Tier 2 extraction with model %s",
                self._tier2_model_id,
                exc_info=True,
            )
            return None

    async def _extract_section_summaries(
        self,
        full_text: str,
        toc: list[TOCEntry],
    ) -> dict[str, str]:
        """Generate 2-3 sentence summaries for each section using LLM.

        For every entry in *toc* that can be located in *full_text*,
        the LLM is asked for a brief summary of the surrounding text
        (up to 4 000 characters).

        Returns:
            A mapping from section title to summary string.
            Empty dict if the LLM is unavailable.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._get_llm()
        if not llm:
            return {}

        summaries: dict[str, str] = {}
        for entry in toc:
            title = entry.get("title", "")
            if not title:
                continue
            idx = full_text.find(title)
            if idx < 0:
                continue
            section_text = full_text[idx : idx + 4000]

            try:
                response = await llm.ainvoke([
                    SystemMessage(
                        content=(
                            "You are an academic paper analyzer. Generate a "
                            "concise 2-3 sentence summary of the following "
                            "paper section. Respond ONLY with the summary, "
                            "no prefixes."
                        ),
                    ),
                    HumanMessage(
                        content=f"Section: {title}\n\nContent:\n{section_text}",
                    ),
                ])
                response_text = _message_content_to_text(response.content).strip()
                if response_text:
                    summaries[title] = response_text
            except Exception:
                logger.debug("Failed to summarize section: %s", title)

        return summaries

    async def _extract_key_concepts(self, full_text: str) -> list[str]:
        """Extract 10-20 key concepts from the paper.

        Uses the first 8 000 characters (typically abstract, introduction,
        and methodology) to identify the most important terms.

        Returns:
            A list of concept strings, or an empty list on failure.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._get_llm()
        if not llm:
            return []

        text_sample = full_text[:8000]

        response = await llm.ainvoke([
            SystemMessage(
                content=(
                    "You are an academic paper analyzer. Extract 10-20 key "
                    "concepts, terms, and techniques from this paper. Return "
                    'ONLY a JSON array of strings, e.g. ["concept1", '
                    '"concept2"].'
                ),
            ),
            HumanMessage(content=text_sample),
        ])
        response_text = _message_content_to_text(response.content).strip()

        try:
            concepts = json.loads(response_text)
            if isinstance(concepts, list):
                return [str(c) for c in concepts[:20]]
        except (json.JSONDecodeError, ValueError):
            # Fallback: parse as newline-separated list
            lines = [
                line.strip().strip("-").strip("\u2022").strip()
                for line in response_text.split("\n")
                if line.strip()
            ]
            return lines[:20]

        return []

    async def _extract_entities(self, full_text: str) -> list[AcademicEntity]:
        """Extract academic entities: methods, datasets, baselines, metrics.

        Returns:
            A list of dicts with ``type`` and ``name`` keys, or an empty
            list on failure.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._get_llm()
        if not llm:
            return []

        text_sample = full_text[:8000]

        response = await llm.ainvoke([
            SystemMessage(
                content=(
                    "You are an academic paper analyzer. Extract academic "
                    "entities from this paper.\n"
                    "Return ONLY a JSON array of objects with \"type\" and "
                    "\"name\" fields.\n"
                    'Types: "method", "dataset", "baseline", "metric", '
                    '"tool", "theory"\n'
                    "Example: "
                    '[{"type": "method", "name": "Transformer"}, '
                    '{"type": "dataset", "name": "ImageNet"}]'
                ),
            ),
            HumanMessage(content=text_sample),
        ])
        response_text = _message_content_to_text(response.content).strip()

        try:
            entities = json.loads(response_text)
            if isinstance(entities, list):
                return [
                    {"type": str(e["type"]), "name": str(e["name"])}
                    for e in entities
                    if isinstance(e, dict) and "type" in e and "name" in e
                ][:30]
        except (json.JSONDecodeError, ValueError):
            pass

        return []

    async def extract_sections(
        self,
        paper_id: str,
        workspace_id: str,
        file_path: str,
    ) -> list[PaperSection]:
        """Extract paper sections for index-based navigation.

        This method extracts all sections from a paper PDF and stores
        them in the database for precise section-level retrieval.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace (for isolation)
            file_path: Path to the PDF file

        Returns:
            List of PaperSection records

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ExtractionError: If extraction fails
        """
        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Check for existing sections
        existing = await self._get_existing_sections(paper_id, workspace_id)
        if existing:
            logger.info(
                "Found %d existing sections for paper %s in workspace %s",
                len(existing),
                paper_id,
                workspace_id,
            )
            return existing

        try:
            markdown_documents = self._load_preprocessed_markdown_documents(file_path)
            if markdown_documents:
                full_text = "\n\n".join(markdown_documents)
                raw_sections = self._split_markdown_into_sections(full_text)
                toc = self._build_toc_from_sections(raw_sections)
            else:
                # Extract TOC and sections using PDFExtractor
                toc = self.pdf_extractor.extract_toc(file_path)
                raw_sections = self.pdf_extractor.split_into_sections(file_path, toc)

            # Create PaperSection records
            paper_sections: list[PaperSection] = []
            for idx, raw_section in enumerate(raw_sections):
                # Generate section path (e.g., "1", "1.1", "1.1.1")
                section_path = self._generate_section_path(idx, toc)

                paper_section = PaperSection(
                    paper_id=paper_id,
                    workspace_id=workspace_id,
                    section_title=raw_section["title"],
                    section_path=section_path,
                    page_start=raw_section["page_start"],
                    page_end=raw_section["page_end"],
                    content=raw_section["content"],
                    level=raw_section["level"],
                )
                paper_sections.append(paper_section)
                self.db.add(paper_section)

            await self.db.commit()

            # Refresh all sections
            for paper_section in paper_sections:
                await self.db.refresh(paper_section)

            logger.info(
                "Extracted %d sections for paper %s in workspace %s",
                len(paper_sections),
                paper_id,
                workspace_id,
            )

            return paper_sections

        except Exception as e:
            await self.db.rollback()
            logger.error("Section extraction failed for paper %s: %s", paper_id, e)
            raise ExtractionError(f"Section extraction failed: {e}") from e

    def _generate_section_path(self, index: int, toc: list[TOCEntry]) -> str:
        """Generate hierarchical section path.

        Creates paths like "1", "1.1", "1.1.1" based on TOC structure.

        Args:
            index: Index of the section in the sections list
            toc: Table of contents with level information

        Returns:
            Section path string
        """
        if not toc or index >= len(toc):
            return str(index + 1)

        # Track section counters at each level
        counters: dict[int, int] = {}
        result_parts: list[str] = []

        for i in range(index + 1):
            level = toc[i]["level"]

            # Reset counters for deeper levels when we go to a higher level
            for lvl in range(level + 1, max(counters.keys(), default=0) + 1):
                counters.pop(lvl, None)

            # Increment counter for this level
            counters[level] = counters.get(level, 0) + 1

            # Build path for the target index
            if i == index:
                for lvl in range(1, level + 1):
                    result_parts.append(str(counters.get(lvl, 1)))

        return ".".join(result_parts) if result_parts else str(index + 1)

    async def get_or_extract(
        self,
        paper: Paper,
        workspace_id: str,
        tier: int = 1,
    ) -> tuple[PaperExtraction | None, list[PaperSection]]:
        """Get existing extraction or create new one (with caching).

        This is the main entry point for extraction. It checks for
        existing extractions and only processes if necessary.

        Args:
            paper: Paper model instance
            workspace_id: UUID of the workspace
            tier: Extraction tier (1=engineering, 2=LLM)

        Returns:
            Tuple of (PaperExtraction or None, list of PaperSections)
        """
        extraction = None
        sections = []

        # Get or create extraction
        if paper.file_path:
            try:
                extraction = await self.extract_paper(
                    str(paper.id),
                    paper.file_path,
                    tier=tier,
                )
            except ExtractionError as e:
                logger.warning("Extraction failed for paper %s: %s", paper.id, e)

            # Get or create sections
            try:
                sections = await self.extract_sections(
                    str(paper.id),
                    workspace_id,
                    paper.file_path,
                )
            except ExtractionError as e:
                logger.warning("Section extraction failed for paper %s: %s", paper.id, e)

        return extraction, sections

    async def get_extraction(
        self,
        paper_id: str,
        tier: int | None = None,
    ) -> PaperExtraction | None:
        """Get existing extraction for a paper.

        Args:
            paper_id: UUID of the paper
            tier: Extraction tier filter (optional)

        Returns:
            Latest PaperExtraction if found, None otherwise
        """
        query = select(PaperExtraction).where(
            PaperExtraction.paper_id == paper_id
        )

        if tier is not None:
            query = query.where(PaperExtraction.tier == tier)

        query = query.order_by(PaperExtraction.created_at.desc())

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_existing_sections(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[PaperSection]:
        """Get existing sections for a paper in a workspace.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace

        Returns:
            List of PaperSection records
        """
        result = await self.db.execute(
            select(PaperSection)
            .where(and_(
                PaperSection.paper_id == paper_id,
                PaperSection.workspace_id == workspace_id,
            ))
            .order_by(PaperSection.page_start)
        )
        return list(result.scalars().all())

    async def get_sections(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[PaperSection]:
        """Get sections for a paper in a workspace.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace

        Returns:
            List of PaperSection records
        """
        return await self._get_existing_sections(paper_id, workspace_id)

    async def get_section_by_path(
        self,
        paper_id: str,
        workspace_id: str,
        section_path: str,
    ) -> PaperSection | None:
        """Get a specific section by its path.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace
            section_path: Section path (e.g., "1.2.3")

        Returns:
            PaperSection if found, None otherwise
        """
        result = await self.db.execute(
            select(PaperSection).where(and_(
                PaperSection.paper_id == paper_id,
                PaperSection.workspace_id == workspace_id,
                PaperSection.section_path == section_path,
            ))
        )
        return result.scalar_one_or_none()

    async def delete_extractions(
        self,
        paper_id: str,
        tier: int | None = None,
    ) -> int:
        """Delete extractions for a paper.

        Args:
            paper_id: UUID of the paper
            tier: Extraction tier filter (optional, deletes all if not specified)

        Returns:
            Number of extractions deleted
        """
        query = select(PaperExtraction).where(
            PaperExtraction.paper_id == paper_id
        )
        if tier is not None:
            query = query.where(PaperExtraction.tier == tier)

        result = await self.db.execute(query)
        extractions = result.scalars().all()

        count = 0
        for extraction in extractions:
            await self.db.delete(extraction)
            count += 1

        await self.db.commit()
        return count

    async def delete_sections(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> int:
        """Delete sections for a paper in a workspace.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace

        Returns:
            Number of sections deleted
        """
        result = await self.db.execute(
            select(PaperSection).where(and_(
                PaperSection.paper_id == paper_id,
                PaperSection.workspace_id == workspace_id,
            ))
        )
        sections = result.scalars().all()

        count = 0
        for section in sections:
            await self.db.delete(section)
            count += 1

        await self.db.commit()
        return count

    async def refresh_extraction(
        self,
        paper_id: str,
        file_path: str,
        tier: int = 1,
    ) -> PaperExtraction:
        """Force re-extraction of a paper.

        Deletes existing extraction and creates a new one.

        Args:
            paper_id: UUID of the paper
            file_path: Path to the PDF file
            tier: Extraction tier (1=engineering, 2=LLM)

        Returns:
            New PaperExtraction record
        """
        # Delete existing extraction
        await self.delete_extractions(paper_id, tier)

        # Create new extraction
        return await self.extract_paper(paper_id, file_path, tier)
