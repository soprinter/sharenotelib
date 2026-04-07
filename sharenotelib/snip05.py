"""SNIP-05: Sharenote Identity Event Helpers (Kinds 10520-10521).

Provides types and marshal/unmarshal functions for miner identity
events (Kind 10520) and pool identity events (Kind 10521).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

KIND_MINER_IDENTITY = 10520
KIND_POOL_IDENTITY = 10521

Tags = List[List[str]]


# --- Miner Identity (Kind 35520) ---


@dataclass
class ChainAddress:
    chain_id: str = ""
    address: str = ""


@dataclass
class MinerIdentity:
    chains: List[ChainAddress] = field(default_factory=list)
    preferred_payout: str = ""


def marshal_miner_tags(m: MinerIdentity) -> Tags:
    """Convert a MinerIdentity into its tag representation."""
    if not m.chains:
        raise ValueError("at least one chain address is required")

    seen: set = set()
    tags: Tags = []

    for c in m.chains:
        if not c.chain_id:
            raise ValueError("chain_id is required")
        if not c.address:
            raise ValueError(f"address is required for chain {c.chain_id}")
        if c.chain_id in seen:
            raise ValueError(f"duplicate chain ID: {c.chain_id}")
        seen.add(c.chain_id)
        tags.append(["a", c.chain_id, c.address])

    if m.preferred_payout:
        tags.append(["payout", m.preferred_payout])

    return tags


def unmarshal_miner_tags(tags: Tags) -> MinerIdentity:
    """Parse tags into a MinerIdentity."""
    m = MinerIdentity()
    for tag in tags:
        if not tag or len(tag) < 2:
            continue
        if tag[0] == "a" and len(tag) >= 3:
            m.chains.append(ChainAddress(chain_id=tag[1], address=tag[2]))
        elif tag[0] == "payout":
            m.preferred_payout = tag[1]

    if not m.chains:
        raise ValueError("required tag 'a' with chain_id and address not found")
    return m


# --- Pool Identity (Kind 35521) ---


@dataclass
class PoolChain:
    chain_id: str = ""
    address: str = ""
    fee_bps: int = 0  # fee in basis points (200 = 2.00%)


@dataclass
class PayoutScheme:
    scheme: str = ""  # "pps", "fpps", "pplns", "prop", "solo"
    params: List[str] = field(default_factory=list)  # key:value pairs


@dataclass
class PayoutThreshold:
    chain_id: str = ""
    amount: int = 0  # minimum payout in satoshis


@dataclass
class PoolProfile:
    name: str = ""
    about: str = ""
    picture: str = ""
    website: str = ""


@dataclass
class PoolIdentity:
    profile: PoolProfile = field(default_factory=PoolProfile)
    chains: List[PoolChain] = field(default_factory=list)
    payouts: List[PayoutScheme] = field(default_factory=list)
    min_sharenote: str = ""
    thresholds: List[PayoutThreshold] = field(default_factory=list)


def marshal_pool_tags(p: PoolIdentity) -> Tags:
    """Convert a PoolIdentity into its tag representation."""
    if not p.chains:
        raise ValueError("at least one chain is required")
    if not p.payouts:
        raise ValueError("at least one payout scheme is required")

    seen: set = set()
    tags: Tags = []

    for c in p.chains:
        if not c.chain_id:
            raise ValueError("chain_id is required")
        if not c.address:
            raise ValueError(f"address is required for chain {c.chain_id}")
        if c.fee_bps < 0:
            raise ValueError(f"fee must be non-negative for chain {c.chain_id}")
        if c.chain_id in seen:
            raise ValueError(f"duplicate chain ID: {c.chain_id}")
        seen.add(c.chain_id)
        tags.append(["a", c.chain_id, c.address, str(c.fee_bps)])

    for ps in p.payouts:
        if not ps.scheme:
            raise ValueError("payout scheme is required")
        tag = ["payout", ps.scheme] + ps.params
        tags.append(tag)

    if p.min_sharenote:
        tags.append(["sharenote", p.min_sharenote])

    for th in p.thresholds:
        tags.append(["threshold", th.chain_id, str(th.amount)])

    return tags


def marshal_pool_content(p: PoolIdentity) -> str:
    """Marshal the pool profile to a JSON content string."""
    prof = p.profile
    if not prof.name and not prof.about and not prof.picture and not prof.website:
        return ""
    d: Dict[str, str] = {}
    if prof.name:
        d["name"] = prof.name
    if prof.about:
        d["about"] = prof.about
    if prof.picture:
        d["picture"] = prof.picture
    if prof.website:
        d["website"] = prof.website
    return json.dumps(d, separators=(",", ":"))


def unmarshal_pool_tags(tags: Tags) -> PoolIdentity:
    """Parse tags into a PoolIdentity (without profile)."""
    p = PoolIdentity()
    for tag in tags:
        if not tag or len(tag) < 2:
            continue
        k = tag[0]
        if k == "a" and len(tag) >= 4:
            try:
                fee = int(tag[3])
            except ValueError:
                fee = 0
            p.chains.append(PoolChain(chain_id=tag[1], address=tag[2], fee_bps=fee))
        elif k == "payout":
            ps = PayoutScheme(scheme=tag[1])
            if len(tag) > 2:
                ps.params = tag[2:]
            p.payouts.append(ps)
        elif k == "sharenote":
            p.min_sharenote = tag[1]
        elif k == "threshold" and len(tag) >= 3:
            try:
                amt = int(tag[2])
            except ValueError:
                amt = 0
            p.thresholds.append(PayoutThreshold(chain_id=tag[1], amount=amt))

    if not p.chains:
        raise ValueError("required tag 'a' with chain and address not found")
    return p


def unmarshal_pool_content(content: str, p: PoolIdentity) -> None:
    """Parse the JSON content string into the pool profile."""
    if not content:
        return
    d = json.loads(content)
    p.profile.name = d.get("name", "")
    p.profile.about = d.get("about", "")
    p.profile.picture = d.get("picture", "")
    p.profile.website = d.get("website", "")


# --- Backwards-compatible aliases ---

# Keep the simple Identity type as an alias for single-chain miner use.
Identity = ChainAddress


def marshal_tags(ident: Identity) -> Tags:
    """Marshal a single ChainAddress as a miner identity event."""
    return marshal_miner_tags(MinerIdentity(chains=[ident]))


def unmarshal_tags(tags: Tags) -> Identity:
    """Unmarshal tags into the first ChainAddress (miner identity)."""
    m = unmarshal_miner_tags(tags)
    return m.chains[0]
