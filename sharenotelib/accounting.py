"""Pool accounting events: invoices and miner payout shares.

Covers the NIP-SN accounting kinds signed by a pool:

* :class:`Invoice` -- Unpaid (35500) and Settled (35501) block invoices.
* :class:`Share` -- Pending (35503), Finalized (35504), and paid Share Payment
  (35505) per-miner payout slices.

Block anchors use ``blake2b-256``: :func:`height_hash` of the block height, and
a ``ShareID`` derived from height, address, and (for pending) the first worker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional

from .errors import InvalidEvent, SharenoteError
from .kinds import Kind, Tags, is_32_byte_hex, parse_int, tags_for_kind

__all__ = [
    "Transaction",
    "Invoice",
    "Share",
    "height_hash",
    "pending_share_id",
    "finalized_share_id",
]


def _blake2b_256_hex(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def height_hash(height: int) -> str:
    """Return the ``HeightHash``: ``blake2b-256`` hex of the height integer."""
    return _blake2b_256_hex(str(height).encode())


def pending_share_id(height: int, address: str, worker: str) -> str:
    """Return the pending ``ShareID`` = ``Hash(height, address, worker)`` (kind 35503)."""
    return _blake2b_256_hex(f"{height}/{address}/{worker}".encode())


def finalized_share_id(height: int, address: str) -> str:
    """Return the consolidated ``ShareID`` = ``Hash(height, address)``.

    Used by both Finalized Share (35504) and Share Payment (35505).
    """
    return _blake2b_256_hex(f"{height}/{address}".encode())


@dataclass(frozen=True)
class Transaction:
    """An on-chain settlement transaction (the ``x`` tag)."""

    txid: str = ""
    confirmed: bool = False
    block_height: int = 0
    block_hash: str = ""

    def to_tag(self) -> List[str]:
        """Serialise to an ``x`` tag: short form unconfirmed, full form confirmed."""
        if self.confirmed:
            return ["x", self.txid, str(self.block_height), self.block_hash]
        return ["x", self.txid]

    @classmethod
    def from_tag(cls, tag: List[str]) -> "Transaction":
        """Parse an ``x`` tag; the full form marks the transaction confirmed."""
        tx = cls(txid=tag[1])
        if len(tag) >= 4 and tag[3]:
            try:
                tx = cls(
                    txid=tag[1],
                    confirmed=True,
                    block_height=int(tag[2]),
                    block_hash=tag[3],
                )
            except ValueError:
                tx = cls(txid=tag[1])
        return tx


@dataclass(frozen=True)
class Invoice:
    """A block invoice: Unpaid (kind 35500) or Settled (kind 35501).

    The same fields serve both kinds; the Settled form additionally carries a
    confirmed settlement :class:`Transaction`.
    """

    height_hash: str = ""
    block_hash: str = ""
    height: int = 0
    amount: int = 0
    workers: int = 0
    shares: str = ""
    tx: Optional[Transaction] = None

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN invoice tags."""
        tags: Tags = [
            ["d", self.height_hash],
            ["b", self.block_hash],
            ["height", str(self.height)],
            ["amount", str(self.amount)],
            ["workers", str(self.workers)],
        ]
        if self.shares:
            tags.append(["shares", self.shares])
        if self.tx is not None:
            tags.append(self.tx.to_tag())
        return tags

    def to_event(self, kind: int = Kind.INVOICE) -> dict:
        """Return a Nostr event dict for ``kind`` (35500 or 35501)."""
        return {"kind": int(kind), "content": "", "tags": self.to_tags()}

    def validate(self, kind: int = Kind.INVOICE) -> None:
        """Validate the invoice (NIP-SN A7/A8).

        Checks ``height > 0``, that ``height_hash`` matches the height, that
        ``block_hash`` is a 32-byte hex key, and ``amount > 0``. For a Settled
        invoice (35501) also requires a confirmed full-form settlement
        transaction.
        """
        if self.height <= 0:
            raise InvalidEvent("height must be greater than zero")
        expected = height_hash(self.height)
        if self.height_hash != expected:
            raise InvalidEvent(
                f"height hash mismatch: expected {expected}, got {self.height_hash}"
            )
        if not is_32_byte_hex(self.block_hash):
            raise InvalidEvent("block hash must be a 32-byte hex key")
        if self.amount <= 0:
            raise InvalidEvent("amount must be positive")
        if int(kind) == int(Kind.SETTLED_INVOICE):
            if self.tx is None or not self.tx.confirmed:
                raise InvalidEvent(
                    "settled invoice requires a confirmed settlement transaction"
                )

    @classmethod
    def from_tags(cls, tags: Tags) -> "Invoice":
        """Parse invoice tags into an :class:`Invoice`."""
        values: dict = {}
        tx: Optional[Transaction] = None
        for tag in tags:
            if len(tag) < 2:
                continue
            key, value = tag[0], tag[1]
            if key == "d":
                values["height_hash"] = value
            elif key == "b":
                values["block_hash"] = value
            elif key == "height":
                values["height"] = parse_int(value, "height")
            elif key == "amount":
                values["amount"] = parse_int(value, "amount")
            elif key == "workers":
                values["workers"] = parse_int(value, "workers")
            elif key == "shares":
                values["shares"] = value
            elif key == "x":
                tx = Transaction.from_tag(tag)
        return cls(tx=tx, **values)

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "Invoice":
        """Parse a kind-35500/35501 Nostr event, validating its kind."""
        return cls.from_tags(tags_for_kind(event, Kind.INVOICE, Kind.SETTLED_INVOICE))


@dataclass(frozen=True)
class Share:
    """A miner payout slice: Pending (35503), Finalized (35504), or Payment (35505)."""

    share_id: str = ""
    address: str = ""
    height_hash: str = ""
    block_hash: str = ""
    chain_id: str = ""
    workers: List[str] = field(default_factory=list)
    height: int = 0
    amount: int = 0
    shares: str = ""
    share_count: int = 0
    total_shares: str = ""
    total_share_count: int = 0
    timestamp: int = 0
    fee: int = 0
    est_payment_height: int = 0
    sharenote_event_ids: List[str] = field(default_factory=list)
    tx: Optional[Transaction] = None

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN share tags."""
        tags: Tags = [
            ["d", self.share_id],
            ["a", self.address],
            ["h", self.height_hash],
            ["b", self.block_hash],
        ]
        if self.chain_id:
            tags.append(["chain", self.chain_id])
        tags.append(["workers", *self.workers])
        tags.append(["height", str(self.height)])
        tags.append(["amount", str(self.amount)])
        if self.shares:
            share_tag = ["shares", self.shares]
            if self.share_count > 0:
                share_tag.append(str(self.share_count))
            tags.append(share_tag)
        if self.total_shares:
            total_tag = ["totalshares", self.total_shares]
            if self.total_share_count > 0:
                total_tag.append(str(self.total_share_count))
            tags.append(total_tag)
        tags.append(["timestamp", str(self.timestamp)])
        if self.fee:
            tags.append(["fee", str(self.fee)])
        if self.est_payment_height:
            tags.append(["eph", str(self.est_payment_height)])
        for event_id in self.sharenote_event_ids:
            if event_id.strip():
                tags.append(["sn", event_id])
        if self.tx is not None:
            tags.append(self.tx.to_tag())
        return tags

    def to_event(self, kind: int = Kind.PENDING_SHARE) -> dict:
        """Return a Nostr event dict for ``kind`` (35503/35504/35505)."""
        return {"kind": int(kind), "content": "", "tags": self.to_tags()}

    def expected_id(self, kind: int) -> str:
        """Return the ``ShareID`` this share must carry for ``kind`` (NIP-SN A10)."""
        k = int(kind)
        if k == int(Kind.PENDING_SHARE):
            if not self.workers:
                raise InvalidEvent("a pending share requires at least one worker")
            return pending_share_id(self.height, self.address, self.workers[0])
        if k in (int(Kind.FINALIZED_SHARE), int(Kind.SHARE_PAYMENT)):
            return finalized_share_id(self.height, self.address)
        raise SharenoteError(f"unknown share kind: {kind}")

    def validate(self, kind: int) -> None:
        """Validate the share against ``kind`` (NIP-SN A9/A10/A13).

        Checks ``height > 0``, the ``HeightHash``, that ``block_hash`` is a
        32-byte hex key, at least one worker, and that the ``ShareID`` equals the
        kind's expected hash. A Share Payment (35505) additionally MUST carry a
        ``chain`` tag and a confirmed full-form settlement transaction (A13/D5).
        """
        if self.height <= 0:
            raise InvalidEvent("height must be greater than zero")
        expected = height_hash(self.height)
        if self.height_hash != expected:
            raise InvalidEvent(
                f"height hash mismatch: expected {expected}, got {self.height_hash}"
            )
        if not is_32_byte_hex(self.block_hash):
            raise InvalidEvent("block hash must be a 32-byte hex key")
        if not self.workers:
            raise InvalidEvent("at least one worker is required")
        expected_id = self.expected_id(kind)
        if self.share_id != expected_id:
            raise InvalidEvent(
                f"shareID mismatch: expected {expected_id}, got {self.share_id}"
            )
        if int(kind) == int(Kind.SHARE_PAYMENT):
            if not self.chain_id:
                raise InvalidEvent("share payment requires a chain tag (A13)")
            if self.tx is None or not self.tx.confirmed:
                raise InvalidEvent(
                    "share payment requires a confirmed full-form settlement (A13)"
                )

    @classmethod
    def from_tags(cls, tags: Tags) -> "Share":
        """Parse share tags into a :class:`Share`."""
        values: dict = {}
        workers: List[str] = []
        event_ids: List[str] = []
        tx: Optional[Transaction] = None
        for tag in tags:
            if len(tag) < 2:
                continue
            key, value = tag[0], tag[1]
            if key == "d":
                values["share_id"] = value
            elif key == "a":
                values["address"] = value
            elif key == "h":
                values["height_hash"] = value
            elif key == "b":
                values["block_hash"] = value
            elif key == "chain":
                values["chain_id"] = value
            elif key == "workers":
                workers = list(tag[1:])
            elif key == "height":
                values["height"] = parse_int(value, "height")
            elif key == "amount":
                values["amount"] = parse_int(value, "amount")
            elif key == "shares":
                values["shares"] = value
                if len(tag) >= 3:
                    values["share_count"] = parse_int(tag[2], "share count")
            elif key == "totalshares":
                values["total_shares"] = value
                if len(tag) >= 3:
                    values["total_share_count"] = parse_int(tag[2], "total share count")
            elif key == "timestamp":
                values["timestamp"] = parse_int(value, "timestamp")
            elif key == "fee":
                values["fee"] = parse_int(value, "fee")
            elif key == "eph":
                values["est_payment_height"] = parse_int(value, "eph")
            elif key == "sn":
                event_ids.extend(tag[1:])
            elif key == "x":
                tx = Transaction.from_tag(tag)
        return cls(workers=workers, sharenote_event_ids=event_ids, tx=tx, **values)

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "Share":
        """Parse a kind-35503/35504/35505 Nostr event, validating its kind."""
        return cls.from_tags(
            tags_for_kind(
                event, Kind.PENDING_SHARE, Kind.FINALIZED_SHARE, Kind.SHARE_PAYMENT
            )
        )
