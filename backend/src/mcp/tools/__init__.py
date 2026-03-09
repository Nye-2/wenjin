"""Academic MCP tools for searching papers and resolving DOIs."""

from src.mcp.tools.arxiv import ArxivTool
from src.mcp.tools.doi import DOITool
from src.mcp.tools.pubmed import PubMedTool

__all__ = ["ArxivTool", "PubMedTool", "DOITool"]
