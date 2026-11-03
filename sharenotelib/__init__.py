"""sharenotelib -- the reference Python SDK for Sharenote (NIP-SN).

The public API is organised around three domains:

* **Z-unit arithmetic** (:mod:`sharenotelib.arithmetic`): the exact
  density/difficulty/target maths and the :class:`Sharenote` value type.
  Accounting paths use :class:`fractions.Fraction`; ``float`` is exposed only
  through display helpers.
* **NIP-SN events** -- builders and parsers that validate the kind and required
  tags: :class:`Telemetry` (35502, :mod:`~sharenotelib.telemetry`),
  :class:`Invoice`/:class:`Share` (35500-35505, :mod:`~sharenotelib.accounting`),
  :class:`RawSharenote` (35510, :mod:`~sharenotelib.minting`), and
  :class:`OperatorMessage` (35515, :mod:`~sharenotelib.messaging`).
* **Identity** (:mod:`sharenotelib.identity`): :class:`MinerIdentity` (10520)
  and :class:`PoolIdentity` (10521).

Everything below is re-exported flat from the top-level package.
"""

from __future__ import annotations

from .__about__ import __version__
from .arithmetic import (
    MAX_CENTS,
    MIN_CENTS,
    Estimate,
    HashrateRange,
    HashrateUnit,
    HumanHashrate,
    NoteInput,
    Plan,
    PrimaryMode,
    Reliability,
    ReliabilityLevel,
    Sharenote,
    combine,
    compare,
    difference,
    difficulty_float,
    difficulty_from_zbits,
    ensure_note,
    estimate,
    estimate_many,
    expected_hashes,
    expected_hashes_from_zbits,
    format_label,
    format_probability_display,
    format_zbits_label,
    hashrate_range,
    human_hashrate,
    max_zbits_for_hashrate,
    note_from_centibits,
    note_from_components,
    note_from_hashrate,
    note_from_label,
    note_from_nbits,
    note_from_zbits,
    note_to_nbits,
    parse_hashrate,
    plan_from_hashrate,
    probability_from_zbits,
    probability_per_hash,
    ratio,
    reliability_levels,
    required_hashrate,
    required_hashrate_mean,
    required_hashrate_quantile,
    resolve_difficulty,
    scale,
    target_for,
    zbits_from_components,
    zbits_from_difficulty,
    zbits_from_target,
)
from .accounting import (
    Invoice,
    Share,
    Transaction,
    finalized_share_id,
    height_hash,
    pending_share_id,
)
from .errors import InvalidEvent, InvalidLabel, SharenoteError
from .identity import (
    ChainAddress,
    MinerIdentity,
    PayoutScheme,
    PayoutThreshold,
    PoolChain,
    PoolIdentity,
    PoolProfile,
)
from .kinds import Kind
from .messaging import OperatorMessage
from .minting import (
    AuxBlock,
    RawSharenote,
    validate_header_hash,
    validate_label,
    validate_raw_event,
)
from .telemetry import Telemetry, Worker

__all__ = [
    "__version__",
    # errors
    "SharenoteError",
    "InvalidLabel",
    "InvalidEvent",
    # kinds
    "Kind",
    # arithmetic: value type & coercion
    "Sharenote",
    "NoteInput",
    "ensure_note",
    "note_from_zbits",
    "note_from_label",
    "note_from_components",
    "note_from_centibits",
    # arithmetic: labels & components
    "format_label",
    "format_zbits_label",
    "zbits_from_components",
    "MIN_CENTS",
    "MAX_CENTS",
    # arithmetic: difficulty (exact + display)
    "resolve_difficulty",
    "difficulty_float",
    "difficulty_from_zbits",
    "zbits_from_difficulty",
    # arithmetic: exact arithmetic
    "combine",
    "difference",
    "scale",
    "ratio",
    "compare",
    # arithmetic: probability
    "probability_per_hash",
    "probability_from_zbits",
    "expected_hashes",
    "expected_hashes_from_zbits",
    "format_probability_display",
    # arithmetic: hashrate planning
    "required_hashrate",
    "required_hashrate_mean",
    "required_hashrate_quantile",
    "max_zbits_for_hashrate",
    "note_from_hashrate",
    "hashrate_range",
    "HashrateRange",
    # arithmetic: reliability
    "Reliability",
    "ReliabilityLevel",
    "reliability_levels",
    # arithmetic: estimates & plans
    "PrimaryMode",
    "Estimate",
    "estimate",
    "estimate_many",
    "Plan",
    "plan_from_hashrate",
    # arithmetic: targets & interop
    "target_for",
    "zbits_from_target",
    "note_from_nbits",
    "note_to_nbits",
    # arithmetic: hashrate formatting
    "parse_hashrate",
    "human_hashrate",
    "HumanHashrate",
    "HashrateUnit",
    # telemetry (35502)
    "Telemetry",
    "Worker",
    # accounting (35500/35501/35503/35504/35505)
    "Invoice",
    "Share",
    "Transaction",
    "height_hash",
    "pending_share_id",
    "finalized_share_id",
    # minting (35510)
    "RawSharenote",
    "AuxBlock",
    "validate_header_hash",
    "validate_raw_event",
    "validate_label",
    # identity (10520/10521)
    "MinerIdentity",
    "ChainAddress",
    "PoolIdentity",
    "PoolChain",
    "PayoutScheme",
    "PayoutThreshold",
    "PoolProfile",
    # messaging (35515)
    "OperatorMessage",
]
