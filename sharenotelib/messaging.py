"""Operator messaging events (NIP-SN kind 35515, optional).

An encrypted operator<->miner direct message, addressable by a conversation
thread. ``content`` is an opaque ciphertext (NIP-44, or legacy NIP-04): this SDK
carries it verbatim and performs **no** encryption or decryption. A consumer
that does not implement operator messaging should ignore the kind (NIP-SN A17).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Optional

from .errors import InvalidEvent
from .kinds import Kind, Tags, tags_for_kind

__all__ = ["OperatorMessage"]


@dataclass(frozen=True)
class OperatorMessage:
    """An operator messaging event (kind 35515).

    ``content`` holds the already-encrypted payload. ``counterparty`` (the ``p``
    tag) and ``thread_id`` (the ``d`` tag) are both required; the chain context
    (``a`` tag) and ``subject`` are optional.
    """

    KIND: ClassVar[int] = Kind.OPERATOR_MESSAGE

    counterparty: str
    thread_id: str
    content: str = ""
    chain_id: str = ""
    address: str = ""
    subject: str = ""

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN tags. Raises if the ``p`` or ``d`` value is missing."""
        if not self.counterparty:
            raise InvalidEvent("operator message requires a counterparty (p tag)")
        if not self.thread_id:
            raise InvalidEvent("operator message requires a thread id (d tag)")
        tags: Tags = [
            ["p", self.counterparty],
            ["d", self.thread_id],
        ]
        if self.chain_id or self.address:
            tags.append(["a", self.chain_id, self.address])
        if self.subject:
            tags.append(["subject", self.subject])
        return tags

    def to_event(self) -> dict:
        """Return a Nostr event dict carrying ``content`` as the ciphertext."""
        return {"kind": int(self.KIND), "content": self.content, "tags": self.to_tags()}

    @classmethod
    def from_tags(cls, tags: Tags, *, content: str = "") -> "OperatorMessage":
        """Parse messaging tags. Requires exactly one ``p`` and one ``d`` (A17)."""
        counterparty: Optional[str] = None
        thread_id: Optional[str] = None
        chain_id = ""
        address = ""
        subject = ""
        p_count = 0
        d_count = 0
        for tag in tags:
            if not tag or len(tag) < 2:
                continue
            key = tag[0]
            if key == "p":
                counterparty = tag[1]
                p_count += 1
            elif key == "d":
                thread_id = tag[1]
                d_count += 1
            elif key == "a":
                chain_id = tag[1]
                address = tag[2] if len(tag) >= 3 else ""
            elif key == "subject":
                subject = tag[1]
        if p_count != 1 or counterparty is None:
            raise InvalidEvent("operator message must carry exactly one 'p' tag")
        if d_count != 1 or thread_id is None:
            raise InvalidEvent("operator message must carry exactly one 'd' tag")
        return cls(
            counterparty=counterparty,
            thread_id=thread_id,
            content=content,
            chain_id=chain_id,
            address=address,
            subject=subject,
        )

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "OperatorMessage":
        """Parse a kind-35515 Nostr event, validating its kind and carrying content."""
        tags = tags_for_kind(event, cls.KIND)
        content = event.get("content", "")
        return cls.from_tags(tags, content=content if isinstance(content, str) else "")
