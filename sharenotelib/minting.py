"""Raw Sharenote / AuxPoW minting events (NIP-SN kind 35510).

When a note is minted, the broadcasting agent publishes the unparsed block
header (hex-encoded, in the ``dd`` tag) alongside one or more auxiliary-chain
``w`` entries -- the primary chain first. Validators hash the ``dd`` hex to
confirm it yields the ``HeaderHash`` in ``d``; the denomination label in ``z``
is a floor only and never verifies a target (NIP-SN A2/A14).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, List, Mapping

from .arithmetic import target_for
from .errors import InvalidEvent, InvalidLabel
from .kinds import Kind, Tags, parse_int, tags_for_kind

__all__ = [
    "AuxBlock",
    "RawSharenote",
    "validate_header_hash",
    "validate_raw_event",
    "validate_label",
]

_LABEL_PATTERN = re.compile(r"^\d+z\d{1,2}$")


@dataclass(frozen=True)
class AuxBlock:
    """One auxiliary-chain entry of a merged-mining proof (a ``w`` tag)."""

    block_hash: str = ""
    chain_id: str = ""
    height: int = 0
    solved: bool = False
    sharenote_label: str = ""

    def to_tag(self) -> List[str]:
        """Serialise to a six-element ``w`` tag."""
        return [
            "w",
            self.block_hash,
            self.chain_id,
            str(self.height),
            str(self.solved).lower(),
            self.sharenote_label,
        ]

    @classmethod
    def from_tag(cls, tag: List[str]) -> "AuxBlock":
        """Parse a six-element ``w`` tag into an :class:`AuxBlock`."""
        return cls(
            block_hash=tag[1],
            chain_id=tag[2],
            height=parse_int(tag[3], "branch height"),
            solved=tag[4].lower() == "true",
            sharenote_label=tag[5],
        )


@dataclass(frozen=True)
class RawSharenote:
    """A raw Sharenote minting event (kind 35510).

    ``aux_blocks`` must be non-empty; the entry whose ``chain_id`` matches
    ``primary_chain_id`` is serialised first (NIP-SN A14).
    """

    KIND: ClassVar[int] = Kind.RAW_SHARENOTE

    header_hash: str = ""
    address: str = ""
    worker: str = ""
    agent: str = ""
    label: str = ""
    primary_chain_id: str = ""
    aux_blocks: List[AuxBlock] = field(default_factory=list)
    header_hex: str = ""

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN tags, primary chain first and ``dd`` last.

        If both ``header_hex`` and ``header_hash`` are set, the header hash is
        verified before serialising. Raises if ``aux_blocks`` is empty or the
        primary chain is absent.
        """
        if not self.aux_blocks:
            raise InvalidEvent("aux_blocks must not be empty")
        if self.header_hex and self.header_hash:
            _verify_header_double_sha256(self)

        primary_index = next(
            (i for i, b in enumerate(self.aux_blocks) if b.chain_id == self.primary_chain_id),
            -1,
        )
        if primary_index == -1:
            raise InvalidEvent(
                f"primary chain {self.primary_chain_id} not found in aux blocks"
            )

        tags: Tags = [
            ["d", self.header_hash],
            ["a", self.address, self.worker, self.agent],
            ["z", self.label.lower()],
            self.aux_blocks[primary_index].to_tag(),
        ]
        for i, block in enumerate(self.aux_blocks):
            if i != primary_index:
                tags.append(block.to_tag())
        tags.append(["dd", self.header_hex])
        return tags

    def to_event(self) -> dict:
        """Return a Nostr event dict (``kind``, empty ``content``, ``tags``)."""
        return {"kind": int(self.KIND), "content": "", "tags": self.to_tags()}

    @classmethod
    def from_tags(cls, tags: Tags) -> "RawSharenote":
        """Parse minting tags into a :class:`RawSharenote`."""
        values: dict = {}
        aux_blocks: List[AuxBlock] = []
        for tag in tags:
            if not tag:
                continue
            key = tag[0]
            if key == "d" and len(tag) >= 2:
                values["header_hash"] = tag[1]
            elif key == "a" and len(tag) >= 4:
                values["address"] = tag[1]
                values["worker"] = tag[2]
                values["agent"] = tag[3]
            elif key == "z" and len(tag) >= 2:
                values["label"] = tag[1]
            elif key == "w" and len(tag) >= 6:
                aux_blocks.append(AuxBlock.from_tag(tag))
            elif key == "dd" and len(tag) >= 2:
                values["header_hex"] = tag[1]
        if aux_blocks:
            values["primary_chain_id"] = aux_blocks[0].chain_id
        return cls(aux_blocks=aux_blocks, **values)

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "RawSharenote":
        """Parse a kind-35510 Nostr event, validating its kind."""
        return cls.from_tags(tags_for_kind(event, cls.KIND))


def _verify_header_double_sha256(note: RawSharenote) -> None:
    """A14 clause 1: the byte-reversed double-SHA256 of ``header_hex`` == ``header_hash``.

    Both fields are required. Raises :class:`~sharenotelib.errors.InvalidEvent`
    on a mismatch.
    """
    if not note.header_hex or not note.header_hash:
        raise InvalidEvent("both header_hex and header_hash are required for validation")
    header_bytes = bytes.fromhex(note.header_hex)
    first = hashlib.sha256(header_bytes).digest()
    second = hashlib.sha256(first).digest()
    computed = second[::-1].hex()
    if computed != note.header_hash:
        raise InvalidEvent(
            f"header hash mismatch: computed {computed}, got {note.header_hash}"
        )


def validate_header_hash(note: RawSharenote) -> None:
    """Verify a Raw Sharenote header against both clauses of NIP-SN A14.

    **Clause 1:** the byte-reversed double-SHA256 of ``header_hex`` MUST equal
    ``header_hash`` (``d``). **Clause 2:** that hash, read as a big-endian 256-bit
    integer, MUST clear the leading-zero bound implied by the denomination label
    ``z`` -- i.e. ``int(header_hash, 16) <= target_for(label)``. Clause 2 is
    checked only when a ``label`` is present (a raw header carries one; the
    bare-hash helper callers do not). Raises
    :class:`~sharenotelib.errors.InvalidEvent` on either failure.
    """
    _verify_header_double_sha256(note)
    if note.label:
        if int(note.header_hash, 16) > target_for(note.label):
            raise InvalidEvent(
                "header hash does not clear the leading-zero bound implied by z (A14 clause 2)"
            )


def validate_raw_event(event: Mapping[str, Any], *, primary_chain_id: str = "") -> RawSharenote:
    """Validate a kind-35510 event against the full NIP-SN A14 rule set.

    Operates on the raw event so the tag-ordering and arity constraints a parsed
    :class:`RawSharenote` would normalise away are still enforced: ``z`` lowercase,
    every ``w`` entry carrying exactly six elements, at least one ``w`` branch,
    and ``dd`` as the last tag. When ``primary_chain_id`` is supplied (the
    out-of-band primary identity) it MUST be present among the branches and MUST
    be the first one. Finally the header is verified with
    :func:`validate_header_hash` (A14 clauses 1 and 2). Returns the parsed
    :class:`RawSharenote` on success; raises
    :class:`~sharenotelib.errors.InvalidEvent` otherwise.
    """
    tags = tags_for_kind(event, Kind.RAW_SHARENOTE)

    z_tag = next((t for t in tags if t and t[0] == "z"), None)
    if z_tag is None or len(z_tag) < 2:
        raise InvalidEvent("raw sharenote is missing its 'z' denomination tag")
    if z_tag[1] != z_tag[1].lower():
        raise InvalidEvent("raw sharenote 'z' denomination must be lowercase")

    w_tags = [t for t in tags if t and t[0] == "w"]
    if not w_tags:
        raise InvalidEvent("raw sharenote needs at least one 'w' branch")
    for w_tag in w_tags:
        if len(w_tag) != 6:
            raise InvalidEvent("each raw sharenote 'w' entry must have exactly six elements")

    non_empty = [t for t in tags if t]
    if not non_empty or non_empty[-1][0] != "dd":
        raise InvalidEvent("raw sharenote 'dd' tag must be the last tag")

    note = RawSharenote.from_tags(tags)

    if primary_chain_id:
        chain_ids = [b.chain_id for b in note.aux_blocks]
        if primary_chain_id not in chain_ids:
            raise InvalidEvent(
                f"declared primary chain {primary_chain_id} is absent from the branches"
            )
        if note.aux_blocks[0].chain_id != primary_chain_id:
            raise InvalidEvent(
                f"primary chain {primary_chain_id} must be the first 'w' branch"
            )

    validate_header_hash(note)
    return note


def validate_label(label: str) -> None:
    """Check that ``label`` matches the sharenote label shape, e.g. ``"34z10"``."""
    if not _LABEL_PATTERN.match(label.lower()):
        raise InvalidLabel(
            f"invalid sharenote label format: {label} (expected format like '34z10')"
        )
