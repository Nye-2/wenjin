"""Imports concrete workspace feature handlers for decorator registration."""

from . import patent  # noqa: F401
from . import proposal  # noqa: F401
from . import sci  # noqa: F401
from . import software_copyright
from . import thesis  # noqa: F401

__all__ = ["patent", "proposal", "sci", "software_copyright", "thesis"]
