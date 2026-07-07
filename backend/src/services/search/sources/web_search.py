"""Public web search source backed by DuckDuckGo's HTML endpoint."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from src.services.search.base import SearchResult
from src.services.search.registry import register_search_source

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEOUT_SECONDS = 12.0
MAX_WEB_RESULTS = 10

_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(?P<snippet>.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
        trust_env=False,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            )
        },
    )


class WebSearchSource:
    """Searches the public web and returns snippet-level evidence."""

    name = "web_search"

    def __init__(
        self,
        *,
        client_factory: Callable[[], AbstractAsyncContextManager[Any]] | None = None,
    ) -> None:
        self._client_factory = client_factory or _default_client_factory

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]:
        normalized_query = " ".join(str(query or "").split()).strip()
        if not normalized_query:
            return []
        normalized_limit = max(1, min(int(limit or MAX_WEB_RESULTS), MAX_WEB_RESULTS))

        async with self._client_factory() as client:
            response = await client.get(
                DUCKDUCKGO_HTML_URL,
                params={"q": normalized_query},
            )
            response.raise_for_status()

        return _parse_duckduckgo_html_results(
            response.text,
            query=normalized_query,
            limit=normalized_limit,
        )


def _parse_duckduckgo_html_results(
    text: str,
    *,
    query: str,
    limit: int,
) -> list[SearchResult]:
    matches = list(_RESULT_LINK_RE.finditer(text or ""))
    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for index, match in enumerate(matches):
        if len(results) >= limit:
            break

        title = _clean_html(match.group("title"))
        url = _decode_duckduckgo_href(match.group("href"))
        if not title or not url:
            continue

        title_key = re.sub(r"\W+", "", title.lower())
        url_key = url.rstrip("/")
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)

        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        snippet_match = _SNIPPET_RE.search(text, match.end(), next_start)
        snippet = _clean_html(snippet_match.group("snippet")) if snippet_match else ""

        results.append(
            SearchResult(
                title=title,
                abstract=snippet or None,
                url=url,
                external_id=url,
                source=WebSearchSource.name,
                raw={
                    "source": WebSearchSource.name,
                    "evidence_level": "web_search_result_snippet",
                    "retrieval_query": query,
                    "rank": len(results) + 1,
                },
            )
        )

    return results


def _clean_html(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value or "")
    return " ".join(html.unescape(without_tags).split()).strip()


def _decode_duckduckgo_href(value: str) -> str:
    href = html.unescape(str(value or "").strip())
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    uddg = parse_qs(parsed.query).get("uddg")
    if uddg and uddg[0]:
        return unquote(uddg[0])
    return href


register_search_source(WebSearchSource.name, WebSearchSource)
