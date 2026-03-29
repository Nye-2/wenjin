"""PubMed search tool for academic paper discovery."""

import logging
from typing import Any
from xml.etree import ElementTree

from src.integration.http_client import ServiceHttpClient

logger = logging.getLogger(__name__)

# PubMed API base URLs
EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_http = ServiceHttpClient(service_name="pubmed", timeout=30.0)


class PubMedTool:
    """Tool for searching academic papers on PubMed."""

    name = "pubmed_search"
    description = "Search for academic papers on PubMed by query. Returns paper metadata including title, authors, abstract, PMID, and URL."

    def __init__(self) -> None:
        """Initialize the PubMed tool."""
        self._base_url = EUTILS_BASE_URL
        self._email = "contact@guanlan.ai"  # NCBI requires email for API usage

    async def _fetch(self, url: str, params: dict[str, Any]) -> str | None:
        """Fetch data from URL with error handling.

        Args:
            url: URL to fetch.
            params: Query parameters.

        Returns:
            Response text or None on error.
        """
        try:
            response = await _http.get(url, params=params)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"PubMed API error for {url}: {e}")
            return None

    def _parse_paper(self, article_elem: ElementTree.Element) -> dict[str, Any] | None:
        """Parse a PubMed article XML element into a dictionary.

        Args:
            article_elem: XML element for a PubmedArticle.

        Returns:
            Parsed paper dictionary or None on error.
        """
        try:
            # Get MedlineCitation
            medline = article_elem.find("MedlineCitation")
            if medline is None:
                return None

            article = medline.find("Article")
            if article is None:
                return None

            # Title
            title_elem = article.find("ArticleTitle")
            title = title_elem.text if title_elem is not None and title_elem.text else "No title"

            # Authors
            authors = []
            author_list = article.find("AuthorList")
            if author_list is not None:
                for author in author_list.findall("Author"):
                    last_name = author.find("LastName")
                    fore_name = author.find("ForeName")
                    if last_name is not None and last_name.text:
                        name = last_name.text
                        if fore_name is not None and fore_name.text:
                            name = f"{fore_name.text} {name}"
                        authors.append(name)

            # Abstract
            abstract = ""
            abstract_elem = article.find("Abstract")
            if abstract_elem is not None:
                abstract_texts = []
                for text_elem in abstract_elem.findall("AbstractText"):
                    if text_elem.text:
                        label = text_elem.get("Label", "")
                        if label:
                            abstract_texts.append(f"{label}: {text_elem.text}")
                        else:
                            abstract_texts.append(text_elem.text)
                abstract = " ".join(abstract_texts)

            # PMID
            pmid_elem = medline.find("PMID")
            pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else None

            # Journal/Year
            year = None
            journal_elem = article.find("Journal")
            if journal_elem is not None:
                journal_issue = journal_elem.find("JournalIssue")
                if journal_issue is not None:
                    pub_date = journal_issue.find("PubDate")
                    if pub_date is not None:
                        year_elem = pub_date.find("Year")
                        if year_elem is not None and year_elem.text:
                            year = int(year_elem.text)

            return {
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "pmid": pmid,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                "year": year,
            }
        except Exception as e:
            logger.error(f"Error parsing PubMed article: {e}")
            return None

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search for papers on PubMed.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of paper dictionaries with title, authors, abstract, pmid, url.
            Returns empty list on error.
        """
        try:
            # Step 1: Search for PMIDs
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "email": self._email,
            }

            search_url = f"{self._base_url}/esearch.fcgi"
            search_text = await self._fetch(search_url, search_params)
            if not search_text:
                return []

            import json

            search_data = json.loads(search_text)
            id_list = search_data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return []

            # Step 2: Fetch paper details
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
                "email": self._email,
            }

            fetch_url = f"{self._base_url}/efetch.fcgi"
            fetch_text = await self._fetch(fetch_url, fetch_params)
            if not fetch_text:
                return []

            # Parse XML response
            root = ElementTree.fromstring(fetch_text)
            results = []

            for article_elem in root.findall(".//PubmedArticle"):
                paper = self._parse_paper(article_elem)
                if paper:
                    results.append(paper)

            return results

        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            return []
