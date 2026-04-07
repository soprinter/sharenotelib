"""SNIP-04: Raw Sharenote Minting & AuxPoW Event Helpers (Kind 35510).

Provides types and marshal/unmarshal functions for sharenote minting
events that package merged-mining block headers into verifiable payloads.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

KIND_SHARENOTE = 35510

Tags = List[List[str]]


@dataclass
class AuxBlock:
    block_hash: str = ""
    chain_id: str = ""
    height: int = 0
    solved: bool = False
    sharenote_label: str = ""


@dataclass
class Sharenote:
    header_hash: str = ""
    address: str = ""
    worker: str = ""
    agent: str = ""
    label: str = ""
    primary_chain_id: str = ""
    aux_blocks: List[AuxBlock] = field(default_factory=list)
    header_hex: str = ""


def marshal_tags(sn: Sharenote) -> Tags:
    """Convert a Sharenote into its tag representation."""
    if not sn.aux_blocks:
        raise ValueError("aux_blocks must not be empty")

    if sn.header_hex and sn.header_hash:
        validate_header_hash(sn)

    label = sn.label.lower()

    tags: Tags = [
        ["d", sn.header_hash],
        ["a", sn.address, sn.worker, sn.agent],
        ["z", label],
    ]

    # Primary chain first.
    primary_idx = -1
    for i, block in enumerate(sn.aux_blocks):
        if block.chain_id == sn.primary_chain_id:
            primary_idx = i
            break

    if primary_idx == -1:
        raise ValueError(f"primary chain {sn.primary_chain_id} not found in aux blocks")

    tags.append(_marshal_aux_block(sn.aux_blocks[primary_idx]))
    for i, block in enumerate(sn.aux_blocks):
        if i == primary_idx:
            continue
        tags.append(_marshal_aux_block(block))

    tags.append(["dd", sn.header_hex])
    return tags


def unmarshal_tags(tags: Tags) -> Sharenote:
    """Parse tags into a Sharenote."""
    sn = Sharenote()

    for tag in tags:
        if not tag:
            continue
        k = tag[0]

        if k == "d" and len(tag) >= 2:
            sn.header_hash = tag[1]
        elif k == "a" and len(tag) >= 4:
            sn.address = tag[1]
            sn.worker = tag[2]
            sn.agent = tag[3]
        elif k == "z" and len(tag) >= 2:
            sn.label = tag[1]
        elif k == "w" and len(tag) >= 6:
            sn.aux_blocks.append(AuxBlock(
                block_hash=tag[1],
                chain_id=tag[2],
                height=int(tag[3]),
                solved=tag[4].lower() == "true",
                sharenote_label=tag[5],
            ))
        elif k == "dd" and len(tag) >= 2:
            sn.header_hex = tag[1]

    if sn.aux_blocks:
        sn.primary_chain_id = sn.aux_blocks[0].chain_id

    return sn


def validate_header_hash(sn: Sharenote) -> None:
    """Check that double-SHA256 of header_hex matches header_hash."""
    if not sn.header_hex or not sn.header_hash:
        raise ValueError("both header_hex and header_hash are required for validation")

    header_bytes = bytes.fromhex(sn.header_hex)
    first = hashlib.sha256(header_bytes).digest()
    second = hashlib.sha256(first).digest()
    # Byte-reverse for block hash display format.
    computed = second[::-1].hex()
    if computed != sn.header_hash:
        raise ValueError(f"header hash mismatch: computed {computed}, got {sn.header_hash}")


def validate_label(label: str) -> None:
    """Check that label looks like a valid sharenote label (e.g. '34z10')."""
    import re
    if not re.match(r"^\d+z\d{1,2}$", label.lower()):
        raise ValueError(f"invalid sharenote label format: {label} (expected format like '34z10')")


def _marshal_aux_block(b: AuxBlock) -> List[str]:
    return [
        "w",
        b.block_hash,
        b.chain_id,
        str(b.height),
        str(b.solved).lower(),
        b.sharenote_label,
    ]
