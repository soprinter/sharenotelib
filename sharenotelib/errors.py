"""Exception hierarchy for :mod:`sharenotelib`.

Every error raised by this package is a :class:`SharenoteError`, which derives
from the built-in :class:`ValueError` so existing ``except ValueError`` handlers
keep working. More specific subclasses let callers distinguish *why* an input
was rejected without string-matching messages.
"""

from __future__ import annotations

__all__ = ["SharenoteError", "InvalidLabel", "InvalidEvent"]


class SharenoteError(ValueError):
    """Base class for every error raised by :mod:`sharenotelib`."""


class InvalidLabel(SharenoteError):
    """A denomination label or Z-unit value could not be parsed or is invalid."""


class InvalidEvent(SharenoteError):
    """A Nostr event (kind, content, or tags) failed structural validation."""
