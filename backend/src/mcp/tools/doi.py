"""DOI resolution tool for academic metadata retrieval."""

import logging
from typing import Any

from src.integration.http_client import ServiceHttpClient

logger = logging.getLogger(__name__)

# DOI Content Negotiation API
DOI_API_URL = "https://doi.org"

_http = ServiceHttpClient(service_name="doi", timeout=10.0)


class DOITool:
    """Tool for resolving DOIs to metadata."""

    name = "doi_resolve"
    description = "Resolve a DOI (Digital Object Identifier) to retrieve metadata about the academic work."

    def __init__(self) -> None:
        """Initialize the DOI tool."""
        self._base_url = DOI_API_URL
        # Accept headers for content negotiation
        self._headers = {
            "Accept": "application/vnd.citationstyles.csl+json",
            "User-Agent": "AcademiaGPT (mailto:academiagpt@example.com)",
        }

    async def resolve(self, doi: str) -> dict[str, Any] | None:
        """Resolve a DOI to metadata.

        Args:
            doi: The DOI string to resolve (e.g., "10.1038/nature12373").

        Returns:
            Metadata dictionary or None if not found.
        """
        try:
            # Clean the DOI (remove 'doi:' prefix if present)
            doi = doi.strip()
            if doi.lower().startswith("doi:"):
                doi = doi[4:].strip()

            # Remove 'https://doi.org/' prefix if present
            if doi.lower().startswith("https://doi.org/"):
                doi = doi[16:]
            elif doi.lower().startswith("http://doi.org/"):
                doi = doi[15:]

            url = f"{self._base_url}/{doi}"

            response = await _http.get(url, headers=self._headers)

            if response.status_code == 404:
                logger.info(f"DOI not found: {doi}")
                return None

            if response.status_code == 406:
                # Content negotiation failed, try with different accept header
                alt_headers = {
                    "Accept": "application/json",
                    "User-Agent": "AcademiaGPT (mailto:academiagpt@example.com)",
                }
                response = await _http.get(url, headers=alt_headers)

            response.raise_for_status()

            data = response.json()

            # Normalize the response to a common format
            metadata = self._normalize_metadata(data)
            metadata["doi"] = doi

            return metadata

        except Exception as e:
            logger.error(f"DOI resolution error for {doi}: {e}")
            return None

    def _normalize_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize CSL-JSON or similar metadata to a common format.

        Args:
            data: Raw metadata from DOI content negotiation.

        Returns:
            Normalized metadata dictionary.
        """
        # Extract authors
        authors = []
        if "author" in data:
            for author in data["author"]:
                name_parts = []
                if "given" in author:
                    name_parts.append(author["given"])
                if "family" in author:
                    name_parts.append(author["family"])
                if name_parts:
                    authors.append(" ".join(name_parts))
                elif "literal" in author:
                    authors.append(author["literal"])

        # Extract year
        year = None
        if "published" in data:
            if "date-parts" in data["published"]:
                date_parts = data["published"]["date-parts"]
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]
        elif "issued" in data:
            if "date-parts" in data["issued"]:
                date_parts = data["issued"]["date-parts"]
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]

        # Extract container (journal/conference)
        container = None
        if "container-title" in data:
            container = data["container-title"]
            if isinstance(container, list):
                container = container[0] if container else None

        # Extract URL
        url = data.get("URL") or data.get("link")

        return {
            "title": data.get("title", ""),
            "authors": authors,
            "abstract": data.get("abstract", ""),
            "year": year,
            "container": container,  # Journal or conference name
            "url": url,
            "type": data.get("type", ""),
            "publisher": data.get("publisher", ""),
            "volume": data.get("volume"),
            "issue": data.get("issue"),
            "page": data.get("page"),
            "issn": data.get("ISSN"),
            "isbn": data.get("ISBN"),
        }
