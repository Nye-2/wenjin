"""All concrete search sources -- importing this package auto-registers them."""

from src.services.search.sources import curated_academic as _curated  # noqa: F401
from src.services.search.sources import semantic_scholar as _ss  # noqa: F401
