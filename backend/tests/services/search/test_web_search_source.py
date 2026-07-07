import pytest

from src.services.search.sources.web_search import WebSearchSource


_DUCK_HTML = """
<html>
  <body>
    <h2 class="result__title">
      <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopenai.com%2F&amp;rut=abc">OpenAI | Research &amp; Deployment</a>
    </h2>
    <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopenai.com%2F&amp;rut=abc">Creating safe and beneficial AI.</a>
    <h2 class="result__title">
      <a rel="nofollow" class="result__a" href="https://example.edu/paper">Example Paper</a>
    </h2>
    <a class="result__snippet" href="https://example.edu/paper">A paper-like result with a stable URL.</a>
  </body>
</html>
"""


class _FakeResponse:
    status_code = 200
    text = _DUCK_HTML

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, *, params: dict[str, object]) -> _FakeResponse:
        self.calls.append({"url": url, "params": params})
        return _FakeResponse()


@pytest.mark.asyncio
async def test_web_search_source_parses_duckduckgo_html_results() -> None:
    client = _FakeClient()
    source = WebSearchSource(client_factory=lambda: client)

    results = await source.search("OpenAI official website", limit=2)

    assert client.calls == [
        {
            "url": "https://html.duckduckgo.com/html/",
            "params": {"q": "OpenAI official website"},
        }
    ]
    assert [item.title for item in results] == [
        "OpenAI | Research & Deployment",
        "Example Paper",
    ]
    assert results[0].url == "https://openai.com/"
    assert results[0].abstract == "Creating safe and beneficial AI."
    assert results[0].source == "web_search"
    assert results[0].raw["evidence_level"] == "web_search_result_snippet"
