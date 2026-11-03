"""NIP-SN event kinds and shared Nostr-event helpers.

NIP-SN defines one family of Nostr event kinds that carry Sharenote identity,
telemetry, pool accounting, and raw merged-mining proofs. :class:`Kind` is the
single source of truth for those kind numbers; the event dataclasses in the
sibling modules reference it through their ``KIND`` class attribute.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Any, List, Mapping

from .errors import InvalidEvent

_HEX_RE = re.compile(r"[0-9a-fA-F]+")

__all__ = ["Kind", "Tags", "tags_for_kind", "is_hex", "is_32_byte_hex", "parse_int"]

#: A Nostr tag set: a list of string lists, as it appears on an event.
Tags = List[List[str]]


def is_hex(value: str) -> bool:
    """Report whether ``value`` is a non-empty, even-length hex string.

    Mirrors Go's ``hex.DecodeString`` acceptance (and the JS/Python SDKs): an
    empty string, an odd number of digits, or a non-hex character all fail, so
    chain IDs such as ``"15"``/``"2a"`` pass while ``"xz"`` does not (NIP-SN
    A5/A16).
    """
    if not isinstance(value, str) or not value or len(value) % 2 != 0:
        return False
    # A regex (not bytes.fromhex, which silently ignores ASCII whitespace) so a
    # value like "1 5" is rejected, matching Go's hex.DecodeString exactly.
    return _HEX_RE.fullmatch(value) is not None


def is_32_byte_hex(value: str) -> bool:
    """Report whether ``value`` is exactly 64 hex characters (a 32-byte key)."""
    return isinstance(value, str) and len(value) == 64 and is_hex(value)


def parse_int(value: Any, field: str) -> int:
    """Parse a tag value into an ``int``, raising :class:`InvalidEvent` if malformed.

    Tag values arrive as strings off the wire; a non-numeric one is a structural
    event error, so this raises :class:`~sharenotelib.errors.InvalidEvent` rather
    than letting a bare :class:`ValueError` escape a ``from_tags`` parser.
    """
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidEvent(f"{field} must be an integer, got {value!r}") from exc


class Kind(IntEnum):
    """The NIP-SN Nostr event kinds.

    Members compare equal to their plain ``int`` value, so they can be used
    anywhere a kind number is expected (``event["kind"] == Kind.INVOICE``).
    """

    MINER_IDENTITY = 10520
    POOL_IDENTITY = 10521
    INVOICE = 35500
    SETTLED_INVOICE = 35501
    HASHRATE = 35502
    PENDING_SHARE = 35503
    FINALIZED_SHARE = 35504
    SHARE_PAYMENT = 35505
    RAW_SHARENOTE = 35510
    OPERATOR_MESSAGE = 35515


def tags_for_kind(event: Mapping[str, Any], *expected: int) -> Tags:
    """Validate ``event['kind']`` and return the event's tags.

    ``expected`` is one or more acceptable kind numbers. Raises
    :class:`~sharenotelib.errors.InvalidEvent` if the event's kind is not one of
    them, or if ``tags`` is present but not a list.
    """
    kind = event.get("kind")
    if kind not in expected:
        allowed = ", ".join(str(int(k)) for k in expected)
        raise InvalidEvent(f"expected event kind in ({allowed}), got {kind!r}")
    tags = event.get("tags")
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise InvalidEvent("event 'tags' must be a list of string lists")
    return tags
