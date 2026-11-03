"""Identity events: miner (NIP-SN kind 10520) and pool (kind 10521).

Both are replaceable events. A :class:`MinerIdentity` declares the chain
addresses a miner controls for payout discovery. A :class:`PoolIdentity`
declares a pool's profile, accepted chains with fees, payout schemes, and
policy -- its profile travels in ``content`` as a kind-0 style JSON object.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Dict, List, Mapping

from .errors import InvalidEvent
from .kinds import Kind, Tags, is_hex, tags_for_kind

__all__ = [
    "ChainAddress",
    "MinerIdentity",
    "PoolChain",
    "PayoutScheme",
    "PayoutThreshold",
    "PoolProfile",
    "PoolIdentity",
]


@dataclass(frozen=True)
class ChainAddress:
    """A ``(chain_id, address)`` binding a miner controls (a miner ``a`` tag)."""

    chain_id: str = ""
    address: str = ""


@dataclass(frozen=True)
class MinerIdentity:
    """A miner identity event (kind 10520): chain addresses and a payout hint."""

    KIND: ClassVar[int] = Kind.MINER_IDENTITY

    chains: List[ChainAddress] = field(default_factory=list)
    preferred_payout: str = ""

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN tags (NIP-SN A5).

        Raises if there are no chains, a chain is missing its id or address, or a
        chain id repeats.
        """
        if not self.chains:
            raise InvalidEvent("at least one chain address is required")
        seen: set = set()
        tags: Tags = []
        for chain in self.chains:
            if not chain.chain_id:
                raise InvalidEvent("chain_id is required")
            if not chain.address:
                raise InvalidEvent(f"address is required for chain {chain.chain_id}")
            if chain.chain_id in seen:
                raise InvalidEvent(f"duplicate chain ID: {chain.chain_id}")
            seen.add(chain.chain_id)
            tags.append(["a", chain.chain_id, chain.address])
        if self.preferred_payout:
            tags.append(["payout", self.preferred_payout])
        return tags

    def to_event(self) -> dict:
        """Return a Nostr event dict (``kind``, empty ``content``, ``tags``)."""
        return {"kind": int(self.KIND), "content": "", "tags": self.to_tags()}

    def validate(self) -> None:
        """Validate the miner identity (NIP-SN A5/A16).

        Requires at least one chain address; each chain ID MUST be valid hex and
        MUST NOT repeat; each address MUST be non-empty.
        """
        if not self.chains:
            raise InvalidEvent("miner identity needs at least one chain address")
        seen: set = set()
        for chain in self.chains:
            if not is_hex(chain.chain_id):
                raise InvalidEvent(f"chain ID {chain.chain_id!r} is not valid hex")
            if chain.chain_id in seen:
                raise InvalidEvent(f"duplicate chain ID: {chain.chain_id}")
            seen.add(chain.chain_id)
            if not chain.address:
                raise InvalidEvent("miner identity address is empty")

    @classmethod
    def from_tags(cls, tags: Tags) -> "MinerIdentity":
        """Parse miner identity tags. Raises if no valid ``a`` tag is present."""
        chains: List[ChainAddress] = []
        preferred_payout = ""
        for tag in tags:
            if not tag or len(tag) < 2:
                continue
            if tag[0] == "a" and len(tag) >= 3:
                chains.append(ChainAddress(chain_id=tag[1], address=tag[2]))
            elif tag[0] == "payout":
                preferred_payout = tag[1]
        if not chains:
            raise InvalidEvent("required tag 'a' with chain_id and address not found")
        return cls(chains=chains, preferred_payout=preferred_payout)

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "MinerIdentity":
        """Parse a kind-10520 Nostr event, validating its kind."""
        return cls.from_tags(tags_for_kind(event, cls.KIND))


@dataclass(frozen=True)
class PoolChain:
    """A pool's payout address and fee (basis points) on one chain."""

    chain_id: str = ""
    address: str = ""
    fee_bps: int = 0  #: fee in basis points (200 == 2.00%)


@dataclass(frozen=True)
class PayoutScheme:
    """A supported payout scheme and its trailing ``key:value`` parameters."""

    scheme: str = ""  #: one of "pps", "fpps", "pplns", "prop", "solo"
    params: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PayoutThreshold:
    """A minimum payout threshold (in the coin's base unit) for one chain."""

    chain_id: str = ""
    amount: int = 0


@dataclass(frozen=True)
class PoolProfile:
    """The pool's kind-0 style profile, carried in the event ``content``."""

    name: str = ""
    about: str = ""
    picture: str = ""
    website: str = ""


@dataclass(frozen=True)
class PoolIdentity:
    """A pool identity event (kind 10521): profile, chains, schemes, and policy."""

    KIND: ClassVar[int] = Kind.POOL_IDENTITY

    profile: PoolProfile = field(default_factory=PoolProfile)
    chains: List[PoolChain] = field(default_factory=list)
    payouts: List[PayoutScheme] = field(default_factory=list)
    min_sharenote: str = ""
    thresholds: List[PayoutThreshold] = field(default_factory=list)

    def to_tags(self) -> Tags:
        """Serialise to NIP-SN tags (NIP-SN A6).

        Raises if there are no chains, no payout schemes, a chain is malformed, a
        fee is negative, a chain id repeats, or a scheme is empty.
        """
        if not self.chains:
            raise InvalidEvent("at least one chain is required")
        if not self.payouts:
            raise InvalidEvent("at least one payout scheme is required")
        seen: set = set()
        tags: Tags = []
        for chain in self.chains:
            if not chain.chain_id:
                raise InvalidEvent("chain_id is required")
            if not chain.address:
                raise InvalidEvent(f"address is required for chain {chain.chain_id}")
            if chain.fee_bps < 0:
                raise InvalidEvent(f"fee must be non-negative for chain {chain.chain_id}")
            if chain.chain_id in seen:
                raise InvalidEvent(f"duplicate chain ID: {chain.chain_id}")
            seen.add(chain.chain_id)
            tags.append(["a", chain.chain_id, chain.address, str(chain.fee_bps)])
        for payout in self.payouts:
            if not payout.scheme:
                raise InvalidEvent("payout scheme is required")
            tags.append(["payout", payout.scheme, *payout.params])
        if self.min_sharenote:
            tags.append(["sharenote", self.min_sharenote])
        for threshold in self.thresholds:
            tags.append(["threshold", threshold.chain_id, str(threshold.amount)])
        return tags

    def to_content(self) -> str:
        """Serialise the profile to a compact JSON ``content`` string (or ``""``)."""
        profile = self.profile
        fields = {
            "name": profile.name,
            "about": profile.about,
            "picture": profile.picture,
            "website": profile.website,
        }
        present = {key: value for key, value in fields.items() if value}
        if not present:
            return ""
        return json.dumps(present, separators=(",", ":"))

    def to_event(self) -> dict:
        """Return a Nostr event dict with the profile JSON as ``content``."""
        return {"kind": int(self.KIND), "content": self.to_content(), "tags": self.to_tags()}

    def validate(self) -> None:
        """Validate the pool identity (NIP-SN A6/A16).

        Requires at least one chain (valid hex ID, non-negative fee, no duplicate
        IDs, non-empty address) and at least one payout scheme; a ``pplns`` scheme
        MUST carry an ``n:<window>`` parameter.
        """
        if not self.chains:
            raise InvalidEvent("pool identity needs at least one chain")
        seen: set = set()
        for chain in self.chains:
            if not is_hex(chain.chain_id):
                raise InvalidEvent(f"chain ID {chain.chain_id!r} is not valid hex")
            if chain.chain_id in seen:
                raise InvalidEvent(f"duplicate chain ID: {chain.chain_id}")
            seen.add(chain.chain_id)
            if not chain.address:
                raise InvalidEvent("pool identity address is empty")
            if chain.fee_bps < 0:
                raise InvalidEvent(f"fee must be non-negative for chain {chain.chain_id}")
        if not self.payouts:
            raise InvalidEvent("pool identity needs at least one payout scheme")
        for payout in self.payouts:
            if payout.scheme == "pplns" and not any(
                param.startswith("n:") for param in payout.params
            ):
                raise InvalidEvent(
                    "pplns payout scheme must carry an n:<window> parameter"
                )

    @classmethod
    def from_tags(cls, tags: Tags) -> "PoolIdentity":
        """Parse pool identity tags (without the profile). Raises if no ``a`` tag."""
        chains: List[PoolChain] = []
        payouts: List[PayoutScheme] = []
        min_sharenote = ""
        thresholds: List[PayoutThreshold] = []
        for tag in tags:
            if not tag or len(tag) < 2:
                continue
            key = tag[0]
            if key == "a" and len(tag) >= 4:
                try:
                    fee = int(tag[3])
                except ValueError:
                    fee = 0
                chains.append(PoolChain(chain_id=tag[1], address=tag[2], fee_bps=fee))
            elif key == "payout":
                payouts.append(PayoutScheme(scheme=tag[1], params=list(tag[2:])))
            elif key == "sharenote":
                min_sharenote = tag[1]
            elif key == "threshold" and len(tag) >= 3:
                try:
                    amount = int(tag[2])
                except ValueError:
                    amount = 0
                thresholds.append(PayoutThreshold(chain_id=tag[1], amount=amount))
        if not chains:
            raise InvalidEvent("required tag 'a' with chain and address not found")
        return cls(
            chains=chains,
            payouts=payouts,
            min_sharenote=min_sharenote,
            thresholds=thresholds,
        )

    @classmethod
    def from_content(cls, content: str) -> PoolProfile:
        """Parse a profile JSON ``content`` string into a :class:`PoolProfile`."""
        if not content:
            return PoolProfile()
        data: Dict[str, Any] = json.loads(content)
        return PoolProfile(
            name=data.get("name", ""),
            about=data.get("about", ""),
            picture=data.get("picture", ""),
            website=data.get("website", ""),
        )

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> "PoolIdentity":
        """Parse a kind-10521 Nostr event (tags and profile), validating its kind."""
        tags = tags_for_kind(event, cls.KIND)
        identity = cls.from_tags(tags)
        content = event.get("content", "")
        if isinstance(content, str) and content:
            return replace(identity, profile=cls.from_content(content))
        return identity
