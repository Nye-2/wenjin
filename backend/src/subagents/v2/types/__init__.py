"""V2 subagent type registry population.

Importing this package triggers all @subagent decorators, populating REGISTRY
with the 5 V1 subagent types. Import this package (or import any subagent from
it) before calling REGISTRY.get() to ensure all types are available.
"""

from . import clusterer as clusterer
from . import critical_writer as critical_writer
from . import outliner as outliner
from . import scholar_searcher as scholar_searcher
from . import web_searcher as web_searcher
from .clusterer import Clusterer
from .critical_writer import CriticalWriter
from .outliner import Outliner
from .scholar_searcher import ScholarSearcher
from .web_searcher import WebSearcher

__all__ = [
    "ScholarSearcher",
    "WebSearcher",
    "Clusterer",
    "CriticalWriter",
    "Outliner",
]
