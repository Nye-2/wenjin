"""V2 subagent type registry.

Importing this package triggers @subagent decorators.
"""

from . import prism as prism  # noqa: F401
from . import react as react  # noqa: F401
from . import sandbox as sandbox  # noqa: F401
from . import searcher as searcher  # noqa: F401
from .prism import PrismSelectionOptimizerSubagent
from .react import ReactSubagent
from .sandbox import SandboxPythonSubagent
from .searcher import SearcherSubagent

__all__ = [
    "SearcherSubagent",
    "ReactSubagent",
    "PrismSelectionOptimizerSubagent",
    "SandboxPythonSubagent",
]
