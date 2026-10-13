"""Optional web adapter. The analytical engine remains independent of HTTP."""

from .app import create_app

__all__ = ["create_app"]
