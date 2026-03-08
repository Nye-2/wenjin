"""PDF extraction service for TOC-based literature navigation.

This module provides functionality to extract table of contents, metadata,
and section content from PDF documents using PyMuPDF (fitz).
"""

from typing import Optional

import fitz  # PyMuPDF


class PDFExtractor:
    """Service for extracting content and structure from PDF documents.

    Features:
    - TOC (Table of Contents) extraction
    - Metadata extraction (title, authors, page count)
    - Section content extraction by page range
    - PDF splitting into sections based on TOC
    """

    def extract_toc(self, pdf_path: str) -> list[dict]:
        """Extract table of contents from a PDF document.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of TOC entries, each containing:
                - title: Section title
                - page: Page number (1-indexed)
                - level: Nesting level (1 for top-level, 2+ for nested)

        Raises:
            FileNotFoundError: If the PDF file does not exist.
        """
        toc_entries: list[dict] = []

        with fitz.open(pdf_path) as doc:
            raw_toc = doc.get_toc()

            for entry in raw_toc:
                # fitz TOC format: [level, title, page]
                level, title, page = entry
                toc_entries.append({
                    "title": title,
                    "page": page,
                    "level": level,
                })

        return toc_entries

    def extract_metadata(self, pdf_path: str) -> dict:
        """Extract metadata from a PDF document.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Dictionary containing:
                - title: Document title (empty string if not found)
                - authors: Author names (empty string if not found)
                - page_count: Total number of pages

        Raises:
            FileNotFoundError: If the PDF file does not exist.
        """
        with fitz.open(pdf_path) as doc:
            metadata = doc.metadata

            return {
                "title": metadata.get("title", "") or "",
                "authors": metadata.get("author", "") or "",
                "page_count": doc.page_count,
            }

    def extract_section_content(
        self,
        pdf_path: str,
        page_start: int,
        page_end: Optional[int] = None,
    ) -> str:
        """Extract text content from a page range.

        Args:
            pdf_path: Path to the PDF file.
            page_start: Starting page number (1-indexed).
            page_end: Ending page number (1-indexed, inclusive).
                     If None, only extracts page_start.

        Returns:
            Combined text content from the specified pages.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            IndexError: If page numbers are out of range.
        """
        # If no end page specified, extract only the start page
        if page_end is None:
            page_end = page_start

        content_parts: list[str] = []

        with fitz.open(pdf_path) as doc:
            # Convert to 0-indexed for internal use
            start_idx = max(0, page_start - 1)
            end_idx = min(doc.page_count - 1, page_end - 1)

            for page_idx in range(start_idx, end_idx + 1):
                page = doc.load_page(page_idx)
                content_parts.append(page.get_text())

        return "\n".join(content_parts)

    def split_into_sections(
        self,
        pdf_path: str,
        toc: list[dict],
    ) -> list[dict]:
        """Split PDF into sections based on table of contents.

        Args:
            pdf_path: Path to the PDF file.
            toc: Table of contents from extract_toc().

        Returns:
            List of sections, each containing:
                - title: Section title
                - page_start: Starting page number
                - page_end: Ending page number
                - content: Text content of the section
                - level: Nesting level

        Raises:
            FileNotFoundError: If the PDF file does not exist.
        """
        if not toc:
            return []

        sections: list[dict] = []

        with fitz.open(pdf_path) as doc:
            total_pages = doc.page_count

            for i, entry in enumerate(toc):
                page_start = entry["page"]

                # Determine page_end: next section's page - 1, or end of document
                if i + 1 < len(toc):
                    next_page = toc[i + 1]["page"]
                    page_end = next_page - 1
                else:
                    page_end = total_pages

                # Ensure page_end doesn't exceed total pages
                page_end = min(page_end, total_pages)

                # Extract content for this section
                content = self._extract_pages_content(doc, page_start, page_end)

                sections.append({
                    "title": entry["title"],
                    "page_start": page_start,
                    "page_end": page_end,
                    "content": content,
                    "level": entry["level"],
                })

        return sections

    def _extract_pages_content(
        self,
        doc: fitz.Document,
        page_start: int,
        page_end: int,
    ) -> str:
        """Extract text content from pages without opening a new document handle.

        Args:
            doc: Open fitz Document.
            page_start: Starting page number (1-indexed).
            page_end: Ending page number (1-indexed, inclusive).

        Returns:
            Combined text content from the specified pages.
        """
        content_parts: list[str] = []

        # Convert to 0-indexed for internal use
        start_idx = max(0, page_start - 1)
        end_idx = min(doc.page_count - 1, page_end - 1)

        for page_idx in range(start_idx, end_idx + 1):
            page = doc.load_page(page_idx)
            content_parts.append(page.get_text())

        return "\n".join(content_parts)
