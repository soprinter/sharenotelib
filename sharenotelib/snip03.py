"""SNIP-03: Pool Accounting Event Helpers (Kinds 35500-35505).

Provides types and marshal/unmarshal functions for pool invoices
and miner payout share events.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

KIND_INVOICE = 35500
KIND_SETTLED_INVOICE = 35501
KIND_PENDING_SHARE = 35503
KIND_FINALIZED_SHARE = 35504
KIND_SHARE_PAYMENT = 35505

Tags = List[List[str]]


def _blake2b_256_hex(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def compute_height_hash(height: int) -> str:
    return _blake2b_256_hex(str(height).encode())


def compute_pending_share_id(height: int, address: str, worker: str) -> str:
    return _blake2b_256_hex(f"{height}/{address}/{worker}".encode())


def compute_payment_share_id(height: int, address: str) -> str:
    return _blake2b_256_hex(f"{height}/{address}".encode())


@dataclass
class Transaction:
    txid: str = ""
    confirmed: bool = False
    block_height: int = 0
    block_hash: str = ""


@dataclass
class Invoice:
    height_hash: str = ""
    block_hash: str = ""
    height: int = 0
    amount: int = 0
    workers: int = 0
    shares: str = ""
    tx: Optional[Transaction] = None


@dataclass
class Share:
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


# --- Invoice ---

def marshal_invoice_tags(inv: Invoice) -> Tags:
    tags: Tags = [
        ["d", inv.height_hash],
        ["b", inv.block_hash],
        ["height", str(inv.height)],
        ["amount", str(inv.amount)],
        ["workers", str(inv.workers)],
    ]
    if inv.shares:
        tags.append(["shares", inv.shares])
    if inv.tx is not None:
        tags.append(_marshal_tx(inv.tx))
    return tags


def unmarshal_invoice_tags(tags: Tags) -> Invoice:
    inv = Invoice()
    for tag in tags:
        if len(tag) < 2:
            continue
        k, v = tag[0], tag[1]
        if k == "d":
            inv.height_hash = v
        elif k == "b":
            inv.block_hash = v
        elif k == "height":
            inv.height = int(v)
        elif k == "amount":
            inv.amount = int(v)
        elif k == "workers":
            inv.workers = int(v)
        elif k == "shares":
            inv.shares = v
        elif k == "x":
            inv.tx = _unmarshal_tx(tag)
    return inv


# --- Share ---

def marshal_share_tags(s: Share) -> Tags:
    tags: Tags = [
        ["d", s.share_id],
        ["a", s.address],
        ["h", s.height_hash],
        ["b", s.block_hash],
    ]
    if s.chain_id:
        tags.append(["chain", s.chain_id])

    tags.append(["workers"] + s.workers)
    tags.append(["height", str(s.height)])
    tags.append(["amount", str(s.amount)])

    if s.shares:
        share_tag = ["shares", s.shares]
        if s.share_count > 0:
            share_tag.append(str(s.share_count))
        tags.append(share_tag)

    if s.total_shares:
        total_tag = ["totalshares", s.total_shares]
        if s.total_share_count > 0:
            total_tag.append(str(s.total_share_count))
        tags.append(total_tag)

    tags.append(["timestamp", str(s.timestamp)])

    if s.fee:
        tags.append(["fee", str(s.fee)])
    if s.est_payment_height:
        tags.append(["eph", str(s.est_payment_height)])

    for eid in s.sharenote_event_ids:
        if eid.strip():
            tags.append(["sn", eid])

    if s.tx is not None:
        tags.append(_marshal_tx(s.tx))

    return tags


def unmarshal_share_tags(tags: Tags) -> Share:
    s = Share()
    for tag in tags:
        if len(tag) < 2:
            continue
        k, v = tag[0], tag[1]
        if k == "d":
            s.share_id = v
        elif k == "a":
            s.address = v
        elif k == "h":
            s.height_hash = v
        elif k == "b":
            s.block_hash = v
        elif k == "chain":
            s.chain_id = v
        elif k == "workers":
            s.workers = tag[1:]
        elif k == "height":
            s.height = int(v)
        elif k == "amount":
            s.amount = int(v)
        elif k == "shares":
            s.shares = v
            if len(tag) >= 3:
                s.share_count = int(tag[2])
        elif k == "totalshares":
            s.total_shares = v
            if len(tag) >= 3:
                s.total_share_count = int(tag[2])
        elif k == "timestamp":
            s.timestamp = int(v)
        elif k == "fee":
            s.fee = int(v)
        elif k == "eph":
            s.est_payment_height = int(v)
        elif k == "sn":
            s.sharenote_event_ids.extend(tag[1:])
        elif k == "x":
            s.tx = _unmarshal_tx(tag)
    return s


# --- Validation ---

def validate_invoice(inv: Invoice) -> None:
    if inv.height <= 0:
        raise ValueError("height must be greater than zero")
    expected = compute_height_hash(inv.height)
    if inv.height_hash != expected:
        raise ValueError(f"height hash mismatch: expected {expected}, got {inv.height_hash}")
    if inv.amount <= 0:
        raise ValueError("amount must be positive")


def validate_share(s: Share, kind: int) -> None:
    if s.height <= 0:
        raise ValueError("height must be greater than zero")
    expected = compute_height_hash(s.height)
    if s.height_hash != expected:
        raise ValueError(f"height hash mismatch: expected {expected}, got {s.height_hash}")
    if not s.workers:
        raise ValueError("at least one worker is required")

    if kind == KIND_PENDING_SHARE:
        expected_id = compute_pending_share_id(s.height, s.address, s.workers[0])
    elif kind in (KIND_FINALIZED_SHARE, KIND_SHARE_PAYMENT):
        expected_id = compute_payment_share_id(s.height, s.address)
    else:
        raise ValueError(f"unknown share kind: {kind}")

    if s.share_id != expected_id:
        raise ValueError(f"shareID mismatch: expected {expected_id}, got {s.share_id}")


# --- Transaction helpers ---

def _marshal_tx(tx: Transaction) -> List[str]:
    if tx.confirmed:
        return ["x", tx.txid, str(tx.block_height), tx.block_hash]
    return ["x", tx.txid]


def _unmarshal_tx(tag: List[str]) -> Transaction:
    tx = Transaction(txid=tag[1])
    if len(tag) >= 4 and tag[3]:
        try:
            tx.block_height = int(tag[2])
            tx.block_hash = tag[3]
            tx.confirmed = True
        except ValueError:
            pass
    return tx
