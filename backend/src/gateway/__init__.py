"""Gateway package.

Avoid importing the FastAPI application at package import time. Callers that
need the ASGI app should import ``src.gateway.app`` explicitly.
"""

__all__: list[str] = []
