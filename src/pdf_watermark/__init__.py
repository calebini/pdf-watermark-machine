"""Reusable PDF personalization API, independent of the CLI."""

from .core import Options, Result, WatermarkError, personalize

__all__ = ["Options", "Result", "WatermarkError", "personalize"]
