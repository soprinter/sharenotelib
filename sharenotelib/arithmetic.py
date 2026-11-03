"""Z-unit arithmetic: density, difficulty, targets, and planning.

This module implements the :ref:`Z-Arithmetic <nip-sn>` of NIP-SN. A
:class:`Sharenote` is the exact unit of denominated proof-of-work. Its magnitude
is carried two ways:

* ``zbits`` -- the base-2 logarithm of its difficulty, a *display* float.
* ``exact_difficulty`` -- the exact linear difficulty as a
  :class:`fractions.Fraction`, present whenever the note is the product of
  exact-arithmetic aggregation.

Accounting-critical arithmetic (:func:`combine`, :func:`difference`,
:func:`scale`, :func:`ratio`) is performed entirely in exact
:class:`~fractions.Fraction` (and :class:`int`) space -- never with a ``float``
accumulator, which would silently drop micro-shares (NIP-SN A1). ``float`` is
exposed *only* through display helpers whose names say so
(:func:`difficulty_float`, :func:`difficulty_from_zbits`, :func:`human_hashrate`,
``probability_*``).

The discrete label ``NNZcc`` (e.g. ``"34Z10"``) is a *pricing bucket floor*; it
is derived for display and routing only and must never be used to verify a
target (NIP-SN A2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import floor, isfinite, log, log2, log10
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .errors import InvalidLabel, SharenoteError

__all__ = [
    # value type & coercion
    "Sharenote",
    "NoteInput",
    "ensure_note",
    "note_from_zbits",
    "note_from_label",
    "note_from_components",
    "note_from_centibits",
    # labels & components
    "format_label",
    "format_zbits_label",
    "zbits_from_components",
    "MIN_CENTS",
    "MAX_CENTS",
    # difficulty (exact + display)
    "resolve_difficulty",
    "difficulty_float",
    "difficulty_from_zbits",
    "zbits_from_difficulty",
    # exact arithmetic
    "combine",
    "difference",
    "scale",
    "ratio",
    "compare",
    # probability
    "probability_per_hash",
    "probability_from_zbits",
    "expected_hashes",
    "expected_hashes_from_zbits",
    "format_probability_display",
    # hashrate planning
    "required_hashrate",
    "required_hashrate_mean",
    "required_hashrate_quantile",
    "max_zbits_for_hashrate",
    "note_from_hashrate",
    "hashrate_range",
    "HashrateRange",
    # reliability
    "Reliability",
    "ReliabilityLevel",
    "reliability_levels",
    # estimates & plans
    "PrimaryMode",
    "Estimate",
    "estimate",
    "estimate_many",
    "Plan",
    "plan_from_hashrate",
    # targets & interop
    "target_for",
    "zbits_from_target",
    "note_from_nbits",
    "note_to_nbits",
    # hashrate formatting
    "parse_hashrate",
    "human_hashrate",
    "HumanHashrate",
    "HashrateUnit",
]

#: One centibit as a fraction of a Z-bit. Centibits are the two digits after the
#: ``Z`` separator in a label (truncated, never rounded).
_CENTIBIT_STEP: float = 0.01
_CENTIBITS_PER_ZBIT: int = 100

#: Inclusive bounds on the centibit component of a label.
MIN_CENTS: int = 0
MAX_CENTS: int = 99


# ---------------------------------------------------------------------------
# Reliability presets
# ---------------------------------------------------------------------------
class Reliability(str, Enum):
    """Named confidence presets for hashrate planning.

    Each level maps to a Poisson multiplier ``-ln(1 - confidence)``; the mean
    level has a multiplier of ``1`` and no confidence.
    """

    MEAN = "mean"
    USUALLY_90 = "usually_90"
    OFTEN_95 = "often_95"
    VERY_LIKELY_99 = "very_likely_99"
    ALMOST_999 = "almost_999"


@dataclass(frozen=True)
class ReliabilityLevel:
    """A reliability preset: its id, a human label, confidence, and multiplier."""

    id: Reliability
    label: str
    confidence: Optional[float]
    multiplier: float


_RELIABILITY_LEVELS: Mapping[Reliability, ReliabilityLevel] = {
    Reliability.MEAN: ReliabilityLevel(Reliability.MEAN, "On average", None, 1.0),
    Reliability.USUALLY_90: ReliabilityLevel(
        Reliability.USUALLY_90, "Usually (90%)", 0.90, 2.302585092994046
    ),
    Reliability.OFTEN_95: ReliabilityLevel(
        Reliability.OFTEN_95, "Often (95%)", 0.95, 2.995732273553991
    ),
    Reliability.VERY_LIKELY_99: ReliabilityLevel(
        Reliability.VERY_LIKELY_99, "Very likely (99%)", 0.99, 4.605170185988092
    ),
    Reliability.ALMOST_999: ReliabilityLevel(
        Reliability.ALMOST_999, "Almost certain (99.9%)", 0.999, 6.907755278982137
    ),
}


def reliability_levels() -> Tuple[ReliabilityLevel, ...]:
    """Return all defined reliability presets, in ascending confidence order."""
    return tuple(_RELIABILITY_LEVELS.values())


class PrimaryMode(str, Enum):
    """Which hashrate an :class:`Estimate` headlines: the mean or a quantile."""

    MEAN = "mean"
    QUANTILE = "quantile"


class HashrateUnit(str, Enum):
    """SI-prefixed hashrate units, in H/s."""

    HPS = "H/s"
    KHPS = "kH/s"
    MHPS = "MH/s"
    GHPS = "GH/s"
    THPS = "TH/s"
    PHPS = "PH/s"
    EHPS = "EH/s"
    ZHPS = "ZH/s"


# ---------------------------------------------------------------------------
# The Sharenote value type
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Sharenote:
    """An exact, denominated unit of proof-of-work.

    Construct one with :func:`note_from_zbits`, :func:`note_from_label`,
    :func:`note_from_components`, or :func:`ensure_note`. Instances are immutable
    and hashable.

    Examples
    --------
    >>> note = note_from_label("33Z53")
    >>> note.z, note.cents, note.label
    (33, 53, '33Z53')
    >>> note.scale(2).label
    '34Z53'
    """

    z: int
    cents: int
    zbits: float
    #: Exact linear difficulty, present when the note came from exact
    #: aggregation; ``None`` for notes parsed from a label/Z-bits, where it is
    #: derived on demand (see :func:`resolve_difficulty`).
    exact_difficulty: Optional[Fraction] = None

    @property
    def label(self) -> str:
        """The discrete denomination label, e.g. ``"33Z53"``."""
        return format_label(self.z, self.cents)

    def __str__(self) -> str:
        return self.label

    def difficulty(self) -> Fraction:
        """The exact linear difficulty of this note (NIP-SN accounting value)."""
        return resolve_difficulty(self)

    def probability_per_hash(self) -> float:
        """Display probability that a single random hash meets this note."""
        return probability_from_zbits(self.zbits)

    def expected_hashes(self) -> float:
        """Display estimate of the hashes needed, on average, to meet this note."""
        return expected_hashes_from_zbits(self.zbits)

    def required_hashrate(
        self,
        seconds: float,
        *,
        multiplier: Optional[float] = None,
        reliability: Union[Reliability, float, None] = None,
    ) -> float:
        """Hashrate (H/s) needed to meet this note within ``seconds``."""
        return required_hashrate(
            self, seconds, multiplier=multiplier, reliability=reliability
        )

    def target(self) -> int:
        """The 256-bit integer target this note's difficulty corresponds to."""
        return target_for(self)

    def to_nbits(self) -> str:
        """Encode this note's target in Bitcoin compact ``nBits`` hex."""
        return note_to_nbits(self)

    def combine(self, *others: "NoteInput") -> "Sharenote":
        """Exactly aggregate this note with ``others`` (linear difficulty sum)."""
        return combine(self, *others)

    def difference(self, other: "NoteInput") -> "Sharenote":
        """Exactly subtract ``other`` from this note, clamping at ``0Z00``."""
        return difference(self, other)

    def scale(self, factor: float) -> "Sharenote":
        """Exactly multiply this note's difficulty by ``factor``."""
        return scale(self, factor)

    def ratio(self, other: "NoteInput") -> float:
        """Display ratio of this note's difficulty to ``other``'s."""
        return ratio(self, other)


#: Anything that :func:`ensure_note` accepts as a note.
NoteInput = Union[str, Sharenote, Tuple[int, int], Mapping[str, int], int, float]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_LABEL_DECIMAL = re.compile(r"^(\d+(?:\.\d+)?)Z$")
_LABEL_STANDARD = re.compile(r"^(\d+)Z(?:(\d{1,2})(?:CZ)?)?$")
_LABEL_DOTTED = re.compile(r"^(\d+)\.(\d{1,2})Z$")
_HASHRATE_STRING_PATTERN = re.compile(
    r"^([+-]?(?:\d+(?:[_,]?\d+)*(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z\/\s-]+)?$"
)

_HASHRATE_PREFIX_EXPONENT: Mapping[str, int] = {
    "": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6, "Z": 7,
}
_HASHRATE_UNITS: Sequence[Tuple[HashrateUnit, int]] = (
    (HashrateUnit.HPS, 0),
    (HashrateUnit.KHPS, 1),
    (HashrateUnit.MHPS, 2),
    (HashrateUnit.GHPS, 3),
    (HashrateUnit.THPS, 4),
    (HashrateUnit.PHPS, 5),
    (HashrateUnit.EHPS, 6),
    (HashrateUnit.ZHPS, 7),
)


def _assert_finite(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise SharenoteError(f"{field} must be a finite number")


def _clamp_cents(value: int) -> int:
    if not isinstance(value, (int, float)):
        raise SharenoteError("cents must be numeric")
    rounded = int(round(value))
    if rounded < MIN_CENTS:
        return MIN_CENTS
    if rounded > MAX_CENTS:
        return MAX_CENTS
    return rounded


def _label_components_from_zbits(zbits: float) -> Tuple[int, int]:
    z = floor(zbits)
    fractional = zbits - z
    # The +1e-9 pricing floor matches NIP-SN step 2 and the cross-SDK vectors.
    raw_cents = int((fractional / _CENTIBIT_STEP) + 1e-9)
    return int(max(0, z)), _clamp_cents(raw_cents)


def _note_from_components(z: int, cents: int) -> Sharenote:
    normalized_z = int(z)
    normalized_cents = _clamp_cents(cents)
    zbits = zbits_from_components(normalized_z, normalized_cents)
    return Sharenote(z=normalized_z, cents=normalized_cents, zbits=zbits)


def _note_from_zbits_with_exact(zbits: float, exact: Fraction) -> Sharenote:
    _assert_finite(zbits, "zbits")
    if zbits < 0:
        raise SharenoteError("zbits must be non-negative")
    z, cents = _label_components_from_zbits(zbits)
    return Sharenote(z=z, cents=cents, zbits=zbits, exact_difficulty=exact)


def _log2_of_fraction(value: Fraction) -> float:
    """``log2`` of an exact rational without overflowing ``float64``.

    Every difficulty is a dyadic rational, so ``log2(num) - log2(den)`` is exact
    in the denominator term and avoids converting a possibly-huge rational to a
    float. :func:`math.log2` handles arbitrarily large integers natively.
    """
    if value <= 0:
        raise SharenoteError("difficulty must be > 0")
    return log2(value.numerator) - log2(value.denominator)


def _collect_notes(args: Sequence["NoteInput"]) -> List["NoteInput"]:
    """Accept either several note arguments or a single iterable of notes."""
    if len(args) == 1:
        only = args[0]
        if isinstance(only, (Sharenote, str, Mapping)):
            return [only]
        if isinstance(only, tuple) and len(only) == 2 and all(
            isinstance(e, int) and not isinstance(e, bool) for e in only
        ):
            return [only]
        if isinstance(only, (int, float)):
            return [only]
        if isinstance(only, Iterable):
            return list(only)
        return [only]
    return list(args)


# ---------------------------------------------------------------------------
# Construction & coercion
# ---------------------------------------------------------------------------
def format_label(z: int, cents: int) -> str:
    """Format a label from integer bits and centibits, e.g. ``"33Z53"``."""
    return f"{int(z)}Z{_clamp_cents(cents):02d}"


def format_zbits_label(zbits: float, precision: int = 8) -> str:
    """Format a *continuous* Z-bit label for display, e.g. ``"33.53000000Z"``."""
    return f"{zbits:.{precision}f}Z"


def zbits_from_components(z: int, cents: int) -> float:
    """Return the continuous Z-bits for integer bits ``z`` and centibits ``cents``."""
    if not isinstance(z, int) or z < 0:
        raise SharenoteError("z must be a non-negative integer")
    return z + _clamp_cents(cents) * _CENTIBIT_STEP


def note_from_components(z: int, cents: int) -> Sharenote:
    """Build a note from integer bits ``z`` and centibits ``cents`` (clamped 0-99)."""
    return _note_from_components(z, cents)


def note_from_centibits(centibits: int) -> Sharenote:
    """Build a note from a total centibit count, e.g. ``3353`` -> ``"33Z53"``."""
    if not isinstance(centibits, (int, float)) or isinstance(centibits, bool):
        raise SharenoteError("centibits must be numeric")
    if centibits < 0:
        raise SharenoteError("centibits must be non-negative")
    z = int(centibits) // _CENTIBITS_PER_ZBIT
    cents = int(centibits) % _CENTIBITS_PER_ZBIT
    return _note_from_components(z, cents)


def note_from_zbits(zbits: float) -> Sharenote:
    """Build a note from a continuous Z-bit value.

    The float precision of ``zbits`` is preserved; the label is derived by
    truncation (NIP-SN §Discrete Denomination Class).
    """
    _assert_finite(zbits, "zbits")
    if zbits < 0:
        raise SharenoteError("zbits must be non-negative")
    z, cents = _label_components_from_zbits(zbits)
    return Sharenote(z=z, cents=cents, zbits=zbits)


def note_from_label(label: str) -> Sharenote:
    """Parse a denomination label into a note.

    Accepts the canonical ``"33Z53"`` form, a dotted ``"33.53Z"``, a decimal
    ``"33.537812Z"`` (preserving precision), and whitespace/``CZ`` variants.
    Raises :class:`~sharenotelib.errors.InvalidLabel` on anything else.
    """
    cleaned = label.strip().upper().replace(" ", "")
    if match := _LABEL_STANDARD.match(cleaned):
        z = int(match.group(1))
        cents = int(match.group(2)) if match.group(2) else 0
        return _note_from_components(z, cents)
    if match := _LABEL_DOTTED.match(cleaned):
        z = int(match.group(1))
        cents = int(match.group(2).ljust(2, "0")[:2])
        return _note_from_components(z, cents)
    if match := _LABEL_DECIMAL.match(cleaned):
        return note_from_zbits(float(match.group(1)))
    raise InvalidLabel(f"unrecognised Sharenote label: {label!r}")


def ensure_note(value: NoteInput) -> Sharenote:
    """Coerce any supported input into a :class:`Sharenote`.

    Accepts an existing :class:`Sharenote` (returned as-is), a label string, a
    numeric Z-bit value, a ``(z, cents)`` tuple, or a ``{"z": ..., "cents": ...}``
    mapping. Raises :class:`~sharenotelib.errors.SharenoteError` on bad input.
    """
    if isinstance(value, Sharenote):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        _assert_finite(numeric, "zbits")
        if numeric < 0:
            raise SharenoteError("zbits must be non-negative")
        return note_from_zbits(numeric)
    if isinstance(value, str):
        return note_from_label(value)
    if isinstance(value, tuple) and len(value) == 2:
        return _note_from_components(int(value[0]), int(value[1]))
    if isinstance(value, Mapping):
        if "z" in value and "cents" in value:
            return _note_from_components(int(value["z"]), int(value["cents"]))
        raise SharenoteError("mapping must contain 'z' and 'cents'")
    raise SharenoteError(f"unsupported note input: {type(value).__name__}")


# ---------------------------------------------------------------------------
# Difficulty (exact + display)
# ---------------------------------------------------------------------------
def resolve_difficulty(note: NoteInput) -> Fraction:
    """Return the exact linear difficulty of ``note`` as a :class:`~fractions.Fraction`.

    This is the accounting-safe magnitude. If the note already carries an exact
    difficulty (from aggregation) it is returned verbatim; otherwise the note's
    ``2 ** zbits`` difficulty is converted to the exact dyadic rational it
    represents. Use this -- never :func:`difficulty_float` -- when summing or
    slicing shares (NIP-SN A1).
    """
    resolved = ensure_note(note)
    if resolved.exact_difficulty is not None:
        return resolved.exact_difficulty
    return Fraction(difficulty_from_zbits(resolved.zbits))


def difficulty_float(note: NoteInput) -> float:
    """Return a note's linear difficulty as a display ``float`` (lossy).

    Do not accumulate this value; use :func:`resolve_difficulty` for accounting.
    """
    resolved = ensure_note(note)
    if resolved.exact_difficulty is not None:
        return float(resolved.exact_difficulty)
    return difficulty_from_zbits(resolved.zbits)


def difficulty_from_zbits(zbits: float) -> float:
    """Display difficulty ``2 ** zbits`` as a ``float``."""
    return 2.0 ** zbits


def zbits_from_difficulty(difficulty: float) -> float:
    """Recover continuous Z-bits from a ``float`` difficulty (display inverse)."""
    if not isfinite(difficulty) or difficulty <= 0:
        raise SharenoteError("difficulty must be > 0")
    return log2(difficulty)


# ---------------------------------------------------------------------------
# Exact arithmetic (accounting-safe)
# ---------------------------------------------------------------------------
def combine(*notes: NoteInput) -> Sharenote:
    """Aggregate notes by summing their difficulty in exact linear space.

    Pass notes as separate arguments or as a single iterable. Summation uses
    :class:`~fractions.Fraction` so no micro-share is lost to float rounding, and
    the result is order-independent (NIP-SN A1). The returned note carries the
    exact total as its ``exact_difficulty``.

    >>> combine("1Z00", "1Z00").label
    '2Z00'
    """
    items = _collect_notes(notes)
    if not items:
        raise SharenoteError("combine requires at least one note")
    total = Fraction(0)
    for note in items:
        total += resolve_difficulty(note)
    if total <= 0:
        return note_from_zbits(0.0)
    zbits = _log2_of_fraction(total)
    if zbits < 0:
        return note_from_zbits(0.0)
    return _note_from_zbits_with_exact(zbits, total)


def difference(minuend: NoteInput, subtrahend: NoteInput) -> Sharenote:
    """Subtract ``subtrahend`` from ``minuend`` in exact linear space.

    Clamps to ``0Z00`` when the result is zero or negative (NIP-SN subtract).
    """
    diff = resolve_difficulty(minuend) - resolve_difficulty(subtrahend)
    if diff <= 0:
        return note_from_zbits(0.0)
    return _note_from_zbits_with_exact(_log2_of_fraction(diff), diff)


def scale(note: NoteInput, factor: float) -> Sharenote:
    """Multiply a note's difficulty by ``factor`` using exact arithmetic.

    ``factor == 0`` yields ``0Z00``. A positive ``factor`` that drives the
    difficulty below one hash produces negative Z-bits and is rejected -- there
    is deliberately no sub-unit clamp, matching the Go/JS SDKs and the shared
    conformance vectors.
    """
    _assert_finite(factor, "factor")
    if factor < 0:
        raise SharenoteError("factor must be >= 0")
    if factor == 0:
        return note_from_zbits(0.0)
    exact = resolve_difficulty(note) * Fraction(factor)
    if exact <= 0:
        return note_from_zbits(0.0)
    return _note_from_zbits_with_exact(_log2_of_fraction(exact), exact)


def ratio(numerator: NoteInput, denominator: NoteInput) -> float:
    """Return the display ratio of two notes' difficulties.

    The quotient of two exact rationals, returned as a ``float``. Raises if the
    denominator has zero difficulty.
    """
    num = resolve_difficulty(numerator)
    den = resolve_difficulty(denominator)
    if den <= 0:
        raise SharenoteError("division by a zero-difficulty note")
    # Divide in exact rational space and round to float64 exactly ONCE, matching
    # Go's ``big.Rat.Quo(...).Float64()``. ``num / den`` stays exact in
    # ``Fraction`` space; the single ``float()`` is the only rounding. Never
    # ``float(num) / float(den)`` -- collapsing the operands first double-rounds
    # and drifts by a ULP when an operand's exact difficulty is not itself
    # float-representable (e.g. an aggregated note).
    return float(num / den)


def compare(a: NoteInput, b: NoteInput) -> int:
    """Order two notes by denomination.

    Returns a negative, zero, or positive ``int`` when ``a`` sorts before, with,
    or after ``b`` -- comparing integer bits first, then centibits.
    """
    note_a = ensure_note(a)
    note_b = ensure_note(b)
    if note_a.z != note_b.z:
        return note_a.z - note_b.z
    return note_a.cents - note_b.cents


# ---------------------------------------------------------------------------
# Probability
# ---------------------------------------------------------------------------
def probability_from_zbits(zbits: float) -> float:
    """Display probability ``2 ** -zbits`` that a random hash meets a note."""
    _assert_finite(zbits, "zbits")
    return 2.0 ** (-zbits)


def probability_per_hash(note: NoteInput) -> float:
    """Display probability that a single random hash meets ``note``."""
    return probability_from_zbits(ensure_note(note).zbits)


def expected_hashes_from_zbits(zbits: float) -> float:
    """Display estimate of the hashes needed, on average, to meet ``zbits``."""
    return 1.0 / probability_from_zbits(zbits)


def expected_hashes(note: NoteInput) -> float:
    """Display estimate of the hashes needed, on average, to meet ``note``."""
    return expected_hashes_from_zbits(ensure_note(note).zbits)


def format_probability_display(zbits: float, precision: int = 8) -> str:
    """Format a probability as ``"1 / 2^<zbits>"`` for display."""
    _assert_finite(zbits, "zbits")
    return f"1 / 2^{zbits:.{precision}f}"


# ---------------------------------------------------------------------------
# Multiplier resolution shared by hashrate helpers
# ---------------------------------------------------------------------------
def _reliability_level(reliability: Union[Reliability, str]) -> ReliabilityLevel:
    try:
        key = (
            reliability
            if isinstance(reliability, Reliability)
            else Reliability(reliability)
        )
    except ValueError as exc:
        raise SharenoteError(f"unknown reliability level: {reliability!r}") from exc
    return _RELIABILITY_LEVELS[key]


def _resolve_multiplier(
    multiplier: Optional[float],
    reliability: Union[Reliability, float, None],
) -> Tuple[float, Optional[float]]:
    """Return ``(multiplier, quantile)``; keyword multiplier wins over reliability."""
    if multiplier is not None:
        _assert_finite(multiplier, "multiplier")
        if multiplier <= 0:
            raise SharenoteError("multiplier must be > 0")
        return float(multiplier), None
    if isinstance(reliability, (str, Reliability)):
        level = _reliability_level(reliability)
        return level.multiplier, level.confidence
    if isinstance(reliability, (int, float)) and not isinstance(reliability, bool):
        q = float(reliability)
        if q <= 0 or q >= 1:
            raise SharenoteError("confidence must be in (0, 1)")
        return -log(1 - q), q
    return 1.0, None


# ---------------------------------------------------------------------------
# Hashrate planning
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HashrateRange:
    """Inclusive lower / exclusive upper hashrate bound mapping to a note."""

    minimum: float
    maximum: float

    def human(
        self, precision: Optional[int] = None
    ) -> Tuple["HumanHashrate", "HumanHashrate"]:
        """Format both bounds as :class:`HumanHashrate`."""
        return (
            human_hashrate(self.minimum, precision=precision),
            human_hashrate(self.maximum, precision=precision),
        )


def required_hashrate(
    note: NoteInput,
    seconds: float,
    *,
    multiplier: Optional[float] = None,
    reliability: Union[Reliability, float, None] = None,
) -> float:
    """Hashrate (H/s) needed to meet ``note`` within ``seconds``.

    Supply either an explicit ``multiplier`` or a ``reliability`` (a
    :class:`Reliability` preset or a confidence in ``(0, 1)``); the multiplier
    takes precedence. With neither, the mean-time hashrate is returned.
    """
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    factor, _ = _resolve_multiplier(multiplier, reliability)
    return expected_hashes_from_zbits(ensure_note(note).zbits) * factor / seconds


def required_hashrate_mean(note: NoteInput, seconds: float) -> float:
    """Mean-time hashrate (H/s) to meet ``note`` within ``seconds``."""
    return required_hashrate(note, seconds, multiplier=1.0)


def required_hashrate_quantile(
    note: NoteInput, seconds: float, confidence: float
) -> float:
    """Hashrate (H/s) to meet ``note`` within ``seconds`` at a given confidence."""
    if confidence <= 0 or confidence >= 1:
        raise SharenoteError("confidence must be in (0, 1)")
    return required_hashrate(note, seconds, reliability=confidence)


def max_zbits_for_hashrate(
    hashrate: float, seconds: float, multiplier: float = 1.0
) -> float:
    """Largest Z-bits a given hashrate can meet within ``seconds``."""
    _assert_finite(hashrate, "hashrate")
    _assert_finite(seconds, "seconds")
    _assert_finite(multiplier, "multiplier")
    if hashrate <= 0 or seconds <= 0 or multiplier <= 0:
        raise SharenoteError("hashrate, seconds, and multiplier must be > 0")
    return log2(hashrate * seconds / multiplier)


def note_from_hashrate(
    hashrate: Union[float, int, str],
    seconds: float,
    *,
    multiplier: Optional[float] = None,
    reliability: Union[Reliability, float, None] = None,
) -> Sharenote:
    """Build the note a given hashrate can reach within ``seconds``.

    ``hashrate`` may be a number (H/s) or a human string such as ``"5 GH/s"``.
    """
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    numeric = parse_hashrate(hashrate)
    if numeric <= 0:
        raise SharenoteError("hashrate must be > 0")
    factor, _ = _resolve_multiplier(multiplier, reliability)
    return note_from_zbits(max_zbits_for_hashrate(numeric, seconds, factor))


def hashrate_range(
    note: NoteInput,
    seconds: float,
    *,
    multiplier: Optional[float] = None,
    reliability: Union[Reliability, float, None] = None,
) -> HashrateRange:
    """Return the ``[min, max)`` hashrate window that maps to ``note``."""
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    resolved = ensure_note(note)
    factor, _ = _resolve_multiplier(multiplier, reliability)
    lower = expected_hashes_from_zbits(resolved.zbits) * factor / seconds
    upper = expected_hashes_from_zbits(resolved.zbits + _CENTIBIT_STEP) * factor / seconds
    return HashrateRange(minimum=lower, maximum=upper)


# ---------------------------------------------------------------------------
# Targets & interop
# ---------------------------------------------------------------------------
def target_for(note: NoteInput) -> int:
    """Return the 256-bit integer target a note's difficulty corresponds to."""
    resolved = ensure_note(note)
    integer_bits = floor(resolved.zbits)
    base_exponent = 256 - integer_bits
    if base_exponent < 0:
        raise SharenoteError("z too large; target would underflow")
    fractional = resolved.zbits - integer_bits
    # Round the 48-bit scale factor half-away-from-zero to match Go
    # (``math.Round``) and JS (``Math.round``); Python's built-in ``round`` is
    # banker's rounding (half-to-even), which produced a 1-ULP-low target on
    # exact-half scale factors. The factor is in ``(2**47, 2**48]``, where
    # ``0.5`` is an exact multiple of the ULP, so ``floor(x + 0.5)`` is an exact
    # round-half-up with no representation hazard.
    scale_factor = floor(2.0 ** (-fractional) * (1 << 48) + 0.5)
    return ((1 << base_exponent) * scale_factor) >> 48


def zbits_from_target(target: int) -> float:
    """Recover continuous Z-bits from a raw 256-bit target.

    The mathematical inverse of :func:`target_for`: ``zbits = 256 - log2(T)``.
    Used for continuous-ledger accounting so pools can measure physical entropy
    without truncation loss.
    """
    if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
        raise SharenoteError("target must be a positive integer")
    val = float(target)
    if not isfinite(val) or val <= 0:
        raise SharenoteError("target overflows float64")
    zbits = 256 - log2(val)
    if not isfinite(zbits) or zbits < 0:
        raise SharenoteError("target produces invalid zbits")
    return zbits


def note_from_nbits(hex_string: str) -> Sharenote:
    """Build a note from a Bitcoin compact ``nBits`` hex string (8 hex chars)."""
    cleaned = hex_string.strip().lower().removeprefix("0x")
    if not re.fullmatch(r"[0-9a-f]{8}", cleaned):
        raise InvalidLabel("nBits must be an 8-character hex string")
    value = int(cleaned, 16)
    exponent = value >> 24
    mantissa = value & 0xFFFFFF
    if mantissa == 0:
        raise InvalidLabel("mantissa must be non-zero")
    log2_target = log2(mantissa) + 8 * (exponent - 3)
    return note_from_zbits(256 - log2_target)


def _target_to_compact(target: int) -> int:
    if target <= 0:
        raise SharenoteError("target must be positive")
    exponent = (target.bit_length() + 7) // 8
    if exponent <= 3:
        mantissa = target << (8 * (3 - exponent))
    else:
        mantissa = target >> (8 * (exponent - 3))
    mantissa &= 0xFFFFFF
    if mantissa & 0x00800000:
        mantissa >>= 8
        exponent += 1
    if exponent > 0xFF:
        raise SharenoteError("target exponent overflow")
    return (exponent << 24) | mantissa


def note_to_nbits(note: NoteInput) -> str:
    """Encode a note's target in Bitcoin compact ``nBits`` hex (8 chars)."""
    return f"{_target_to_compact(target_for(note)):08x}"


# ---------------------------------------------------------------------------
# Hashrate formatting
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HumanHashrate:
    """A hashrate scaled into a readable unit, with its display string."""

    value: float
    unit: HashrateUnit
    display: str
    exponent: int


def _resolve_hashrate_unit(unit: Union[str, HashrateUnit, None]) -> int:
    if unit is None:
        return 0
    if isinstance(unit, HashrateUnit):
        return next(exp for u, exp in _HASHRATE_UNITS if u is unit)
    normalized = re.sub(r"[_\-\s]+", "", unit.upper())
    normalized = normalized.replace("HPS", "H/S").replace("HS", "H/S")
    if not normalized.endswith("/S") and "H" in normalized:
        normalized = f"{normalized}/S"
    normalized = normalized.replace("/S/S", "/S")
    match = re.fullmatch(r"([KMGTPEZ]?)(H)/S", normalized)
    if not match:
        raise SharenoteError(f"unrecognised hashrate unit: {unit!r}")
    return _HASHRATE_PREFIX_EXPONENT[match.group(1)]


def parse_hashrate(value: Union[float, int, str]) -> float:
    """Parse a hashrate into H/s.

    Accepts a number (returned as a float) or a human string such as
    ``"5 GH/s"``, ``"12.5 MH/s"``, or ``"5 gh"``. Raises on negative or
    unparseable input.
    """
    if isinstance(value, bool):
        raise SharenoteError("unsupported hashrate input")
    if isinstance(value, (int, float)):
        numeric = float(value)
        _assert_finite(numeric, "hashrate")
        if numeric < 0:
            raise SharenoteError("hashrate must be >= 0")
        return numeric
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise SharenoteError("hashrate string must not be empty")
        match = _HASHRATE_STRING_PATTERN.match(trimmed)
        if not match:
            raise SharenoteError(f"unrecognised hashrate format: {value!r}")
        magnitude = float(match.group(1).replace("_", "").replace(",", ""))
        _assert_finite(magnitude, "hashrate")
        if magnitude < 0:
            raise SharenoteError("hashrate must be >= 0")
        unit_raw = match.group(2).strip() if match.group(2) else None
        return magnitude * (10 ** (_resolve_hashrate_unit(unit_raw) * 3))
    raise SharenoteError("unsupported hashrate input")


def human_hashrate(hashrate: float, *, precision: Optional[int] = None) -> HumanHashrate:
    """Scale a hashrate into a readable SI unit with a display string."""
    _assert_finite(hashrate, "hashrate")
    if hashrate <= 0:
        return HumanHashrate(0.0, HashrateUnit.HPS, "0 H/s", 0)
    unit_index = min(len(_HASHRATE_UNITS) - 1, max(0, int(log10(hashrate) // 3)))
    unit, exponent = _HASHRATE_UNITS[unit_index]
    scaled = hashrate / (10 ** (exponent * 3))
    if not isfinite(scaled):
        scaled = hashrate
    if precision is not None:
        text = f"{scaled:.{max(0, precision)}f} {unit.value}"
    elif scaled >= 100:
        text = f"{scaled:.0f} {unit.value}"
    elif scaled >= 10:
        text = f"{scaled:.1f} {unit.value}"
    else:
        text = f"{scaled:.2f} {unit.value}"
    return HumanHashrate(value=scaled, unit=unit, display=text, exponent=exponent)


# ---------------------------------------------------------------------------
# Estimates & plans
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Estimate:
    """A report-ready snapshot of a note's planning figures for a time window."""

    note: Sharenote
    label: str
    zbits: float
    seconds: float
    probability_per_hash: float
    probability_display: str
    expected_hashes: float
    required_hashrate_mean: float
    required_hashrate_quantile: float
    required_hashrate_primary: float
    required_hashrate_human: HumanHashrate
    multiplier: float
    quantile: Optional[float]
    primary_mode: PrimaryMode


@dataclass(frozen=True)
class Plan:
    """An :class:`Estimate` paired with the input hashrate it was planned from."""

    note: Sharenote
    estimate: Estimate
    seconds: float
    input_hashrate: float
    input_hashrate_human: HumanHashrate


def estimate(
    note: NoteInput,
    seconds: float,
    *,
    multiplier: Optional[float] = None,
    reliability: Union[Reliability, float, None] = None,
    primary_mode: Optional[PrimaryMode] = None,
    probability_precision: int = 8,
) -> Estimate:
    """Build an :class:`Estimate` for ``note`` over a ``seconds`` window.

    When a ``reliability``/``confidence`` is given the headline hashrate defaults
    to that quantile; otherwise it is the mean. ``primary_mode`` can force the
    choice, falling back to the mean if no quantile is available.
    """
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    resolved = ensure_note(note)
    factor, quantile = _resolve_multiplier(multiplier, reliability)

    mean = required_hashrate_mean(resolved, seconds)
    quantile_hashrate = required_hashrate(resolved, seconds, multiplier=factor)

    if primary_mode is None:
        mode = PrimaryMode.QUANTILE if quantile is not None else PrimaryMode.MEAN
    else:
        mode = primary_mode
        if mode is PrimaryMode.QUANTILE and quantile is None:
            mode = PrimaryMode.MEAN
    primary = quantile_hashrate if mode is PrimaryMode.QUANTILE else mean

    return Estimate(
        note=resolved,
        label=resolved.label,
        zbits=resolved.zbits,
        seconds=seconds,
        probability_per_hash=probability_per_hash(resolved),
        probability_display=format_probability_display(
            resolved.zbits, probability_precision
        ),
        expected_hashes=expected_hashes_from_zbits(resolved.zbits),
        required_hashrate_mean=mean,
        required_hashrate_quantile=quantile_hashrate,
        required_hashrate_primary=primary,
        required_hashrate_human=human_hashrate(primary),
        multiplier=factor,
        quantile=quantile,
        primary_mode=mode,
    )


def estimate_many(
    notes: Iterable[NoteInput], seconds: float, **kwargs: object
) -> List[Estimate]:
    """Build an :class:`Estimate` for each note, sharing the same options."""
    return [estimate(note, seconds, **kwargs) for note in notes]  # type: ignore[arg-type]


def plan_from_hashrate(
    hashrate: Union[float, int, str],
    seconds: float,
    *,
    multiplier: Optional[float] = None,
    reliability: Union[Reliability, float, None] = None,
    primary_mode: Optional[PrimaryMode] = None,
    probability_precision: int = 8,
) -> Plan:
    """Plan the note a hashrate can reach in ``seconds`` and estimate it.

    ``hashrate`` may be a number (H/s) or a human string such as ``"5 GH/s"``.
    """
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    numeric = parse_hashrate(hashrate)
    if numeric <= 0:
        raise SharenoteError("hashrate must be > 0")

    note = note_from_hashrate(
        numeric, seconds, multiplier=multiplier, reliability=reliability
    )
    est = estimate(
        note,
        seconds,
        multiplier=multiplier,
        reliability=reliability,
        primary_mode=primary_mode,
        probability_precision=probability_precision,
    )
    return Plan(
        note=note,
        estimate=est,
        seconds=seconds,
        input_hashrate=numeric,
        input_hashrate_human=human_hashrate(numeric),
    )
