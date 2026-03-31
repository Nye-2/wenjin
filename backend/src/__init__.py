"""Wenjin backend package.

Keep package import side-effect free so tests and scripts can import individual
modules without bootstrapping the full gateway application.
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
