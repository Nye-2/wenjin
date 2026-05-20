"""V2 subagent type registry — only `searcher` and `react`.

Importing this package triggers @subagent decorators on the two subagents.
"""

from . import react as react  # noqa: F401
from . import searcher as searcher  # noqa: F401
from .react import ReactSubagent
from .searcher import SearcherSubagent

__all__ = ["SearcherSubagent", "ReactSubagent"]
