"""Hashrate telemetry events (NIP-SN kind 35502).

A miner streams live per-farm and per-worker hashrate metrics. All data travels
in tags to keep high-frequency broadcasts small, so ``content`` is the empty
string. The event carries no ``d`` tag; as an addressable event with the empty
coordinate, a miner's latest telemetry replaces its prior snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, List, Mapping, Optional

from .errors import InvalidEvent
from .kinds import Kind, Tags, parse_int, tags_for_kind

__all__ = ["Worker", "Telemetry"]

_WORKER_PREFIX = "w:"


@dataclass(frozen=True)
class Worker:
    """One worker's telemetry sub-fields (the ``w:<name>`` tag)."""

    name: str
    hashrate: str = ""           #: ``h:`` EMA-adjusted hashrate (H/s)
    sharenote: str = ""          #: ``sn:`` minimum difficulty actively assigned
    mean_sharenote: str = ""     #: ``msn:`` Mean Sharenote achieved
    accepted: int = 0            #: ``csn:`` count of accepted sharenotes
    rejected: int = 0            #: ``crsn:`` count of rejected sharenotes
    mean_time_sec: str = ""      #: ``mt:`` mean seconds between accepted shares
    last_accepted_unix: int = 0  #: ``lsn:`` unix time of the last valid share
    user_agent: str = ""         #: ``ua:`` mining software user-agent

    def to_tag(self) -> Optional[List[str]]:
        """Serialise this worker to its ``["w:<name>", "k:v", ...]`` tag.

        Returns ``None`` when the worker has no (non-whitespace) name.
        """
        name = self.name.strip()
        if not name:
            return None
        tag = [f"{_WORKER_PREFIX}{name}"]
        if self.hashrate:
            tag.append(f"h:{self.hashrate}")
        if self.sharenote:
            tag.append(f"sn:{self.sharenote}")
        if self.mean_sharenote:
            tag.append(f"msn:{self.mean_sharenote}")
        tag.append(f"csn:{self.accepted}")
        if self.rejected > 0:
            tag.append(f"crsn:{self.rejected}")
        if self.mean_time_sec:
            tag.append(f"mt:{self.mean_time_sec}")
        if self.last_accepted_unix:
            tag.append(f"lsn:{self.last_accepted_unix}")
        if self.user_agent:
            tag.append(f"ua:{self.user_agent}")
        return tag

    @classmethod
    def from_tag(cls, tag: List[str]) -> Optional["Worker"]:
        """Parse a ``["w:<name>", ...]`` tag into a :class:`Worker` (or ``None``)."""
        if not tag or not tag[0].startswith(_WORKER_PREFIX):
            return None
        name = tag[0][len(_WORKER_PREFIX):]
        if not name:
            return None
        fields: dict = {}
        for item in tag[1:]:
            key, _, value = item.partition(":")
            if not value:
                continue
            if key == "h":
                fields["hashrate"] = value
            elif key == "sn":
                fields["sharenote"] = value
            elif key == "msn":
                fields["mean_sharenote"] = value
            elif key == "csn":
                fields["accepted"] = parse_int(value, "csn")
            elif key == "crsn":
                fields["rejected"] = parse_int(value, "crsn")
            elif key == "mt":
                fields["mean_time_sec"] = value
            elif key == "lsn":
                fields["last_accepted_unix"] = parse_int(value, "lsn")
            elif key == "ua":
                fields["user_agent"] = value
        return cls(name=name, **fields)


@dataclass(frozen=True)
class Telemetry:
    """A hashrate telemetry event (kind 35502).

    Exactly one of ``total_hashrate`` (the aggregate ``all`` tag) or
    ``hashrate`` (the single-worker ``h`` tag) should be set.
    """

    KIND: ClassVar[int] = Kind.HASHRATE

    address: str
    total_hashrate: str = ""
    hashrate: str = ""
    mean_sharenote: str = ""
    workers: List[Worker] = field(default_factory=list)

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN tags. Raises if ``address`` is missing."""
        if not self.address:
            raise InvalidEvent("telemetry requires an address")
        tags: Tags = [["a", self.address]]
        if self.total_hashrate:
            tag = ["all", self.total_hashrate]
            if self.mean_sharenote:
                tag.append(f"msn:{self.mean_sharenote}")
            tags.append(tag)
        elif self.hashrate:
            tag = ["h", self.hashrate]
            if self.mean_sharenote:
                tag.append(f"msn:{self.mean_sharenote}")
            tags.append(tag)
        # Worker tags are sorted alphabetically by name for determinism
        # (NIP-SN A15 SHOULD, decision D6).
        for worker in sorted(self.workers, key=lambda w: w.name):
            worker_tag = worker.to_tag()
            if worker_tag:
                tags.append(worker_tag)
        return tags

    def to_event(self) -> dict:
        """Return a Nostr event dict (``kind``, empty ``content``, ``tags``)."""
        return {"kind": int(self.KIND), "content": "", "tags": self.to_tags()}

    def validate(self) -> None:
        """Validate the telemetry event (NIP-SN A15).

        Requires an ``a`` address, exactly one of the aggregate ``all``
        (``total_hashrate``) or single ``h`` (``hashrate``) hashrate, and a
        hashrate on every worker.
        """
        if not self.address:
            raise InvalidEvent("telemetry requires an address")
        if bool(self.total_hashrate) == bool(self.hashrate):
            raise InvalidEvent(
                "telemetry needs exactly one of a total ('all') or single ('h') hashrate"
            )
        for worker in self.workers:
            if not worker.hashrate:
                raise InvalidEvent(f"worker {worker.name!r} is missing its hashrate")

    @classmethod
    def from_tags(cls, tags: Tags) -> "Telemetry":
        """Parse telemetry tags. Raises if the required ``a`` tag is absent."""
        address = ""
        total_hashrate = ""
        hashrate = ""
        mean_sharenote = ""
        workers: List[Worker] = []
        for tag in tags:
            if not tag:
                continue
            key = tag[0]
            if key == "a" and len(tag) >= 2:
                address = tag[1]
            elif key == "all" and len(tag) >= 2:
                total_hashrate = tag[1]
                mean_sharenote = _inline_msn(tag[2:]) or mean_sharenote
            elif key == "h" and len(tag) >= 2:
                hashrate = tag[1]
                if not mean_sharenote:
                    mean_sharenote = _inline_msn(tag[2:])
            elif key.startswith(_WORKER_PREFIX):
                worker = Worker.from_tag(tag)
                if worker is not None:
                    workers.append(worker)
        if not address:
            raise InvalidEvent("telemetry is missing its required 'a' (address) tag")
        return cls(
            address=address,
            total_hashrate=total_hashrate,
            hashrate=hashrate,
            mean_sharenote=mean_sharenote,
            workers=workers,
        )

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "Telemetry":
        """Parse a kind-35502 Nostr event, validating its kind."""
        return cls.from_tags(tags_for_kind(event, cls.KIND))


def _inline_msn(fields: List[str]) -> str:
    for item in fields:
        if item.startswith("msn:"):
            return item[4:]
    return ""
