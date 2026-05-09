"""read_documents_meta and read_library_meta tools — read workspace room metadata."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool


def make_read_documents_meta(deps):
    """Return a read_documents_meta tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def read_documents_meta(kind: Optional[str] = None) -> dict:
        """Read metadata for documents in this workspace (no content).

        Returns a list of documents with id, name, kind, and version.
        Does NOT return document content — use this for an overview.

        Args:
            kind: Optional document kind filter (e.g. "draft", "outline").
        """
        docs = await deps.documents_service.list(deps.workspace_id)
        result = []
        for d in docs:
            doc_kind = getattr(d, "kind", None)
            if kind is not None and doc_kind != kind:
                continue
            result.append(
                {
                    "id": d.id,
                    "name": getattr(d, "name", None),
                    "kind": doc_kind,
                    "version": getattr(d, "version", None),
                }
            )
        return {"documents": result}

    return read_documents_meta


def make_read_library_meta(deps):
    """Return a read_library_meta tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def read_library_meta(item_type: Optional[str] = None) -> dict:
        """Read metadata for library items in this workspace (no full text).

        Returns a list of items with id, title, year, and item_type.

        Args:
            item_type: Optional item type filter (e.g. "paper", "book").
        """
        items = await deps.library_service.list(deps.workspace_id)
        result = []
        for item in items:
            i_type = getattr(item, "item_type", None)
            if item_type is not None and i_type != item_type:
                continue
            result.append(
                {
                    "id": item.id,
                    "title": getattr(item, "title", None),
                    "year": getattr(item, "year", None),
                    "item_type": i_type,
                }
            )
        return {"items": result}

    return read_library_meta
