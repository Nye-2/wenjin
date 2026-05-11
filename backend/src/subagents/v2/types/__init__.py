"""V2 subagent type registry — only `searcher` and `react`.

Importing this package triggers @subagent decorators on the two subagents.
"""

from . import searcher as searcher  # noqa: F401
from . import react as react  # noqa: F401
from .searcher import SearcherSubagent
from .react import ReactSubagent

__all__ = ["SearcherSubagent", "ReactSubagent"]
