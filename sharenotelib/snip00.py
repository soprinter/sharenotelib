"""
SNIP-0000 — Core Z Arithmetic and Hashrate Conversion.

This module implements the foundational mathematics described in
`sharenote-snip.md` (see SNIP-0000 in §9) and exposes the public helpers
that the rest of the Sharenote Python toolkit builds upon.
"""

from __future__ import annotations

SNIP_0000_IMPLEMENTATION = {
    "id": "SNIP-0000",
    "title": "Core Z Arithmetic and Hashrate Conversion",
    "status": "stable",
    "summary": (
        "Implements canonical note encoding, probability maths, and hashrate "
        "planning for the Sharenote proof-of-work format."
    ),
    "specification": "../../sharenote-snip.md",
}

import re
from dataclasses import dataclass
from enum import Enum
from math import floor, isfinite, log, log2
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

CENT_BIT_STEP: float = 0.01
CONTINUOUS_EXPONENT_STEP: float = CENT_BIT_STEP  # backward compatibility alias
MIN_CENTS: int = 0
MAX_CENTS: int = 99

class ReliabilityId(str, Enum):
    MEAN = "mean"
    USUALLY_90 = "usually_90"
    OFTEN_95 = "often_95"
    VERY_LIKELY_99 = "very_likely_99"
    ALMOST_999 = "almost_999"


@dataclass(frozen=True)
class ReliabilityLevel:
    id: ReliabilityId
    label: str
    confidence: float | None
    multiplier: float


@dataclass(frozen=True)
class Sharenote:
    z: int
    cents: int
    bits: float
    _label_override: Optional[str] = None

    @property
    def label(self) -> str:
        if self._label_override is not None:
            return self._label_override
        return format_label(self.z, self.cents)


class SharenoteError(ValueError):
    """Raised when note parsing or maths receive invalid input."""


_RELIABILITY_LEVELS: Mapping[ReliabilityId, ReliabilityLevel] = {
    ReliabilityId.MEAN: ReliabilityLevel(ReliabilityId.MEAN, "On average", None, 1.0),
    ReliabilityId.USUALLY_90: ReliabilityLevel(
        ReliabilityId.USUALLY_90, "Usually (90%)", 0.90, 2.302585092994046
    ),
    ReliabilityId.OFTEN_95: ReliabilityLevel(
        ReliabilityId.OFTEN_95, "Often (95%)", 0.95, 2.995732273553991
    ),
    ReliabilityId.VERY_LIKELY_99: ReliabilityLevel(
        ReliabilityId.VERY_LIKELY_99, "Very likely (99%)", 0.99, 4.605170185988092
    ),
    ReliabilityId.ALMOST_999: ReliabilityLevel(
        ReliabilityId.ALMOST_999, "Almost certain (99.9%)", 0.999, 6.907755278982137
    ),
}

LabelInput = Union[str, Sharenote, Tuple[int, int], Mapping[str, int]]

@dataclass(frozen=True)
class HumanHashrate:
    value: float
    unit: "HashrateUnit"
    display: str
    exponent: int


class PrimaryMode(str, Enum):
    MEAN = "mean"
    QUANTILE = "quantile"


class HashrateUnit(str, Enum):
    HPS = "H/s"
    KHPS = "kH/s"
    MHPS = "MH/s"
    GHPS = "GH/s"
    THPS = "TH/s"
    PHPS = "PH/s"
    EHPS = "EH/s"
    ZHPS = "ZH/s"


@dataclass(frozen=True)
class HashrateDescriptor:
    value: float
    unit: HashrateUnit | None = None


HashrateValue = Union[float, int, HashrateDescriptor]
HashrateParseInput = Union[HashrateValue, str]


@dataclass(frozen=True)
class BillEstimate:
    sharenote: Sharenote
    label: str
    bits: float
    seconds_target: float
    probability_per_hash: float
    probability_display: str
    expected_hashes: float
    required_hashrate_mean: float
    required_hashrate_quantile: float
    required_hashrate_primary: float
    required_hashrate_human: HumanHashrate
    multiplier: float
    quantile: float | None
    primary_mode: PrimaryMode


@dataclass(frozen=True)
class SharenotePlan:
    sharenote: Sharenote
    bill: BillEstimate
    seconds_target: float
    input_hashrate_hps: float
    input_hashrate_human: HumanHashrate

_LABEL_DECIMAL = re.compile(r"^(\d+(?:\.\d+)?)Z$")
_LABEL_STANDARD = re.compile(r"^(\d+)Z(?:(\d{1,2})(?:CZ)?)?$")
_LABEL_DOTTED = re.compile(r"^(\d+)\.(\d{1,2})Z$")
_HASHRATE_STRING_PATTERN = re.compile(
    r"^([+-]?(?:\d+(?:[_,]?\d+)*(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z\/\s-]+)?$"
)

_HASHRATE_PREFIX_EXPONENT: Mapping[str, int] = {
    "": 0,
    "K": 1,
    "M": 2,
    "G": 3,
    "T": 4,
    "P": 5,
    "E": 6,
    "Z": 7,
}

_PREFIX_TO_UNIT: Mapping[str, HashrateUnit] = {
    "": HashrateUnit.HPS,
    "K": HashrateUnit.KHPS,
    "M": HashrateUnit.MHPS,
    "G": HashrateUnit.GHPS,
    "T": HashrateUnit.THPS,
    "P": HashrateUnit.PHPS,
    "E": HashrateUnit.EHPS,
    "Z": HashrateUnit.ZHPS,
}

_HASHRATE_UNIT_EXPONENT: Mapping[HashrateUnit, int] = {
    HashrateUnit.HPS: 0,
    HashrateUnit.KHPS: 1,
    HashrateUnit.MHPS: 2,
    HashrateUnit.GHPS: 3,
    HashrateUnit.THPS: 4,
    HashrateUnit.PHPS: 5,
    HashrateUnit.EHPS: 6,
    HashrateUnit.ZHPS: 7,
}


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


def _get_reliability_level(reliability: ReliabilityId | str) -> ReliabilityLevel:
    try:
        key = reliability if isinstance(reliability, ReliabilityId) else ReliabilityId(reliability)
    except ValueError as exc:  # pragma: no cover - invalid enum conversion
        raise SharenoteError(f"unknown reliability level: {reliability}") from exc
    try:
        return _RELIABILITY_LEVELS[key]
    except KeyError as exc:  # pragma: no cover - safeguard
        raise SharenoteError(f"unknown reliability level: {reliability}") from exc


def _normalize_hashrate_unit_string(raw: str) -> str:
    normalized = re.sub(r"[_\-\s]+", "", raw.upper())
    normalized = normalized.replace("HPS", "H/S")
    normalized = normalized.replace("HS", "H/S")
    if not normalized.endswith("/S") and "H" in normalized:
        normalized = f"{normalized}/S"
    normalized = normalized.replace("/S/S", "/S")
    return normalized


def _resolve_hashrate_unit(unit: str | HashrateUnit | None) -> tuple[int, HashrateUnit]:
    if unit is None:
        return 0, HashrateUnit.HPS

    if isinstance(unit, HashrateUnit):
        exponent = _HASHRATE_UNIT_EXPONENT[unit]
        return exponent, unit

    normalized = _normalize_hashrate_unit_string(unit)
    match = re.fullmatch(r"([KMGTPEZ]?)(H)/S", normalized)
    if not match:
        raise SharenoteError(f"unrecognised hashrate unit: '{unit}'")
    prefix = match.group(1)
    try:
        exponent = _HASHRATE_PREFIX_EXPONENT[prefix]
        canonical = _PREFIX_TO_UNIT[prefix]
    except KeyError as exc:  # pragma: no cover - invalid prefix
        raise SharenoteError(f"unsupported hashrate prefix: '{prefix}'") from exc
    return exponent, canonical


def normalize_hashrate_value(value: HashrateValue) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        _assert_finite(numeric, "hashrate")
        if numeric < 0:
            raise SharenoteError("hashrate must be >= 0")
        return numeric
    if isinstance(value, HashrateDescriptor):
        _assert_finite(value.value, "hashrate value")
        if value.value < 0:
            raise SharenoteError("hashrate must be >= 0")
        exponent, _ = _resolve_hashrate_unit(value.unit)
        return float(value.value) * (10 ** (exponent * 3))
    raise SharenoteError("unsupported hashrate input")


def parse_hashrate(value: HashrateParseInput) -> float:
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise SharenoteError("hashrate string must not be empty")
        match = _HASHRATE_STRING_PATTERN.match(trimmed)
        if not match:
            raise SharenoteError(f"unrecognised hashrate format: '{value}'")
        magnitude = float(match.group(1).replace("_", "").replace(",", ""))
        _assert_finite(magnitude, "hashrate")
        if magnitude < 0:
            raise SharenoteError("hashrate must be >= 0")
        unit_raw = match.group(2).strip() if match.group(2) else None
        exponent, _ = _resolve_hashrate_unit(unit_raw)
        return magnitude * (10 ** (exponent * 3))
    return normalize_hashrate_value(value)


def format_label(z: int, cents: int) -> str:
    return f"{int(z)}Z{_clamp_cents(cents):02d}"


def format_bits_label(bits: float, precision: int = 8) -> str:
    return f"{bits:.{precision}f}Z"


def bits_from_components(z: int, cents: int) -> float:
    if not isinstance(z, int) or z < 0:
        raise SharenoteError("z must be a non-negative integer")
    cents_norm = _clamp_cents(cents)
    return z + cents_norm * CENT_BIT_STEP


def note_from_components(z: int, cents: int, bits_override: float | None = None) -> Sharenote:
    normalized_z = int(z)
    normalized_cents = _clamp_cents(cents)
    bits = bits_override if bits_override is not None else bits_from_components(normalized_z, normalized_cents)
    return Sharenote(z=normalized_z, cents=normalized_cents, bits=bits)


def note_from_bits(bits: float) -> Sharenote:
    _assert_finite(bits, "bits")
    if bits < 0:
        raise SharenoteError("bits must be non-negative")
    z = floor(bits)
    fractional = bits - z
    raw_cents = int((fractional / CENT_BIT_STEP) + 1e-9)
    cents = _clamp_cents(raw_cents)
    return note_from_components(int(z), cents)


def difficulty_from_bits(bits: float) -> float:
    return 2.0 ** bits


def difficulty_from_note(note: LabelInput) -> float:
    return difficulty_from_bits(ensure_note(note).bits)


def bits_from_difficulty(difficulty: float) -> float:
    if not isfinite(difficulty) or difficulty <= 0:
        raise SharenoteError("difficulty must be > 0")
    return log2(difficulty)


def _normalise_mapping(raw: Mapping[str, int]) -> Tuple[int, int]:
    if "z" in raw and "cents" in raw:
        return int(raw["z"]), int(raw["cents"])
    raise SharenoteError("mapping must contain 'z' and 'cents'")


def ensure_note(value: LabelInput) -> Sharenote:
    if isinstance(value, Sharenote):
        return value
    if isinstance(value, str):
        z, cents = parse_label(value)
        return note_from_components(z, cents)
    if isinstance(value, tuple) and len(value) == 2:
        return note_from_components(int(value[0]), int(value[1]))
    if isinstance(value, Mapping):
        z, cents = _normalise_mapping(value)
        return note_from_components(z, cents)
    raise SharenoteError("unsupported note input")


def parse_label(label: str) -> Tuple[int, int]:
    cleaned = label.strip().upper().replace(" ", "")

    if match := _LABEL_STANDARD.match(cleaned):
        z = int(match.group(1))
        cents = int(match.group(2)) if match.group(2) else 0
        return z, _clamp_cents(cents)

    if match := _LABEL_DOTTED.match(cleaned):
        z = int(match.group(1))
        decimals = match.group(2).ljust(2, "0")[:2]
        cents = int(decimals)
        return z, _clamp_cents(cents)

    if match := _LABEL_DECIMAL.match(cleaned):
        bits = float(match.group(1))
        converted = note_from_bits(bits)
        return converted.z, converted.cents

    raise SharenoteError(f"unrecognised Sharenote label: '{label}'")


def probability_from_bits(bits: float) -> float:
    _assert_finite(bits, "bits")
    return 2.0 ** (-bits)


def probability_per_hash(note: LabelInput) -> float:
    resolved = ensure_note(note)
    return probability_from_bits(resolved.bits)


def expected_hashes(bits: float) -> float:
    return 1.0 / probability_from_bits(bits)


def expected_hashes_for_note(note: LabelInput) -> float:
    resolved = ensure_note(note)
    return expected_hashes(resolved.bits)


def required_hashrate(
    note: LabelInput,
    seconds: float,
    *,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
) -> float:
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")

    resolved_multiplier = 1.0
    if multiplier is not None:
        _assert_finite(multiplier, "multiplier")
        if multiplier <= 0:
            raise SharenoteError("multiplier must be greater than zero")
        resolved_multiplier = multiplier
    elif reliability is not None:
        if isinstance(reliability, (str, ReliabilityId)):
            level = _get_reliability_level(reliability)
            resolved_multiplier = level.multiplier
        else:
            if reliability <= 0 or reliability >= 1:
                raise SharenoteError("confidence must be in (0,1)")
            resolved_multiplier = -log(1 - reliability)

    resolved = ensure_note(note)
    return expected_hashes(resolved.bits) * resolved_multiplier / seconds


def required_hashrate_mean(note: LabelInput, seconds: float) -> float:
    return required_hashrate(note, seconds, multiplier=1.0)


def required_hashrate_quantile(note: LabelInput, seconds: float, confidence: float) -> float:
    if confidence <= 0 or confidence >= 1:
        raise SharenoteError("confidence must be in (0,1)")
    return required_hashrate(note, seconds, reliability=confidence)


def max_bits_for_hashrate(
    hashrate: float, seconds: float, multiplier: float = 1.0
) -> float:
    _assert_finite(hashrate, "hashrate")
    _assert_finite(seconds, "seconds")
    _assert_finite(multiplier, "multiplier")
    if hashrate <= 0 or seconds <= 0 or multiplier <= 0:
        raise SharenoteError("hashrate, seconds, and multiplier must be > 0")
    value = hashrate * seconds / multiplier
    return log2(value)


def note_from_hashrate(
    hashrate: HashrateValue,
    seconds: float,
    *,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
) -> Sharenote:
    numeric_hashrate = normalize_hashrate_value(hashrate)
    resolved_multiplier = 1.0
    if multiplier is not None:
        resolved_multiplier = multiplier
    elif reliability is not None:
        if isinstance(reliability, (str, ReliabilityId)):
            resolved_multiplier = _get_reliability_level(reliability).multiplier
        else:
            if reliability <= 0 or reliability >= 1:
                raise SharenoteError("confidence must be in (0,1)")
            resolved_multiplier = -log(1 - reliability)
    bits = max_bits_for_hashrate(numeric_hashrate, seconds, resolved_multiplier)
    return note_from_bits(bits)


def target_for(note: LabelInput) -> int:
    resolved = ensure_note(note)
    integer_bits = floor(resolved.bits)
    base_exponent = 256 - integer_bits
    if base_exponent < 0:
        raise SharenoteError("z too large; target would underflow")
    fractional = resolved.bits - integer_bits
    scale = 2.0 ** (-fractional)
    precision_bits = 48
    scale_factor = int(round(scale * (1 << precision_bits)))
    base = 1 << base_exponent
    return (base * scale_factor) >> precision_bits


def compare_notes(a: LabelInput, b: LabelInput) -> int:
    note_a = ensure_note(a)
    note_b = ensure_note(b)
    if note_a.z != note_b.z:
        return note_a.z - note_b.z
    return note_a.cents - note_b.cents


def nbits_to_sharenote(hex_string: str) -> Sharenote:
    cleaned = hex_string.strip().lower().removeprefix("0x")
    if not re.fullmatch(r"[0-9a-f]{8}", cleaned):
        raise SharenoteError("nBits must be an 8-character hex string")
    value = int(cleaned, 16)
    exponent = value >> 24
    mantissa = value & 0xFFFFFF
    if mantissa == 0:
        raise SharenoteError("mantissa must be non-zero")
    log2_target = log2(mantissa) + 8 * (exponent - 3)
    bits = 256 - log2_target
    return note_from_bits(bits)


def get_reliability_levels() -> Iterable[ReliabilityLevel]:
    return _RELIABILITY_LEVELS.values()


def format_probability_display(bits: float, precision: int = 8) -> str:
    _assert_finite(bits, "bits")
    return f"1 / 2^{bits:.{precision}f}"


_HASHRATE_UNITS = [
    (HashrateUnit.HPS, 0),
    (HashrateUnit.KHPS, 1),
    (HashrateUnit.MHPS, 2),
    (HashrateUnit.GHPS, 3),
    (HashrateUnit.THPS, 4),
    (HashrateUnit.PHPS, 5),
    (HashrateUnit.EHPS, 6),
    (HashrateUnit.ZHPS, 7),
]


def human_hashrate(hashrate: float) -> HumanHashrate:
    _assert_finite(hashrate, "hashrate")
    if hashrate <= 0:
        return HumanHashrate(0.0, HashrateUnit.HPS, "0 H/s", 0)

    import math

    log_value = math.log10(hashrate)
    unit_index = min(len(_HASHRATE_UNITS) - 1, int(log_value // 3))
    unit, exponent = _HASHRATE_UNITS[unit_index]
    scaled = hashrate / (10 ** (exponent * 3))
    if not isfinite(scaled):
        scaled = hashrate
    if scaled >= 100:
        text = f"{scaled:.0f} {unit.value}"
    elif scaled >= 10:
        text = f"{scaled:.1f} {unit.value}"
    else:
        text = f"{scaled:.2f} {unit.value}"
    return HumanHashrate(value=scaled, unit=unit, display=text, exponent=exponent)


def _resolve_multiplier(
    multiplier: float | None, reliability: ReliabilityId | float | None
) -> tuple[float, Optional[float]]:
    if multiplier is not None:
        _assert_finite(multiplier, "multiplier")
        if multiplier <= 0:
            raise SharenoteError("multiplier must be > 0")
        return float(multiplier), None
    if isinstance(reliability, (str, ReliabilityId)):
        level = _get_reliability_level(reliability)
        return level.multiplier, level.confidence
    if isinstance(reliability, (int, float)):
        q = float(reliability)
        if q <= 0 or q >= 1:
            raise SharenoteError("confidence must be in (0,1)")
        return -log(1 - q), q
    return 1.0, None


def build_bill_estimate(
    note: LabelInput,
    seconds: float,
    *,
    primary_mode: PrimaryMode | None = None,
    probability_precision: int = 8,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
) -> BillEstimate:
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")

    resolved = ensure_note(note)
    multiplier_value, quantile = _resolve_multiplier(multiplier, reliability)

    probability = probability_per_hash(resolved)
    expectation = expected_hashes(resolved.bits)
    mean = required_hashrate_mean(resolved, seconds)
    quantile_hashrate = required_hashrate(
        resolved, seconds, multiplier=multiplier_value
    )

    if primary_mode is None:
        mode = PrimaryMode.QUANTILE if quantile is not None else PrimaryMode.MEAN
    else:
        mode = primary_mode
        if mode is PrimaryMode.QUANTILE and quantile is None:
            mode = PrimaryMode.MEAN

    primary = quantile_hashrate if mode is PrimaryMode.QUANTILE else mean

    return BillEstimate(
        sharenote=resolved,
        label=resolved.label,
        bits=resolved.bits,
        seconds_target=seconds,
        probability_per_hash=probability,
        probability_display=format_probability_display(
            resolved.bits, probability_precision
        ),
        expected_hashes=expectation,
        required_hashrate_mean=mean,
        required_hashrate_quantile=quantile_hashrate,
        required_hashrate_primary=primary,
        required_hashrate_human=human_hashrate(primary),
        multiplier=multiplier_value,
        quantile=quantile,
        primary_mode=mode,
    )


def build_bill_estimates(
    notes: Sequence[LabelInput],
    seconds: float,
    **kwargs,
) -> list[BillEstimate]:
    return [build_bill_estimate(note, seconds, **kwargs) for note in notes]


def plan_sharenote_from_hashrate(
    hashrate: HashrateValue,
    seconds: float,
    *,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
    primary_mode: PrimaryMode | None = None,
    probability_precision: int = 8,
) -> SharenotePlan:
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    numeric_hashrate = normalize_hashrate_value(hashrate)
    if numeric_hashrate <= 0:
        raise SharenoteError("hashrate must be > 0")

    note = note_from_hashrate(
        numeric_hashrate,
        seconds,
        multiplier=multiplier,
        reliability=reliability,
    )

    bill = build_bill_estimate(
        note,
        seconds,
        multiplier=multiplier,
        reliability=reliability,
        primary_mode=primary_mode,
        probability_precision=probability_precision,
    )

    return SharenotePlan(
        sharenote=note,
        bill=bill,
        seconds_target=seconds,
        input_hashrate_hps=numeric_hashrate,
        input_hashrate_human=human_hashrate(numeric_hashrate),
    )


def combine_notes_serial(notes: Sequence[LabelInput]) -> Sharenote:
    if not notes:
        raise SharenoteError("notes sequence must not be empty")
    total_difficulty = 0.0
    for note in notes:
        total_difficulty += difficulty_from_note(note)
    if not isfinite(total_difficulty) or total_difficulty <= 0:
        return note_from_bits(0.0)
    return note_from_bits(bits_from_difficulty(total_difficulty))


def note_difference(
    minuend: LabelInput,
    subtrahend: LabelInput,
) -> Sharenote:
    diff = difficulty_from_note(minuend) - difficulty_from_note(subtrahend)
    if diff <= 0:
        return note_from_bits(0.0)
    return note_from_bits(bits_from_difficulty(diff))


def scale_note(note: LabelInput, factor: float) -> Sharenote:
    _assert_finite(factor, "factor")
    if factor < 0:
        raise SharenoteError("factor must be >= 0")
    if factor == 0:
        return note_from_bits(0.0)
    difficulty = difficulty_from_note(note) * factor
    return note_from_bits(bits_from_difficulty(difficulty))


def divide_notes(numerator: LabelInput, denominator: LabelInput) -> float:
    num = difficulty_from_note(numerator)
    den = difficulty_from_note(denominator)
    if den <= 0:
        raise SharenoteError("division by a zero-difficulty note")
    return num / den
