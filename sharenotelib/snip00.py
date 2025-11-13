from __future__ import annotations


import re
from dataclasses import dataclass
from enum import Enum
from math import floor, isfinite, log, log10, log2
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

CENT_ZBIT_STEP: float = 0.01
CONTINUOUS_EXPONENT_STEP: float = CENT_ZBIT_STEP
MIN_CENTZ: int = 0
MAX_CENTZ: int = 99
CENTZ_UNITS_PER_Z: int = int(round(1 / CENT_ZBIT_STEP))

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
    zbits: float
    _label_override: Optional[str] = None

    @property
    def label(self) -> str:
        if self._label_override is not None:
            return self._label_override
        return format_label(self.z, self.cents)

    def __str__(self) -> str:  # pragma: no cover - helper
        return self.label

    def probability_per_hash(self) -> float:
        return probability_from_zbits(self.zbits)

    def expected_hashes(self) -> HashesMeasurement:
        return expected_hashes_for_zbits(self.zbits)

    def required_hashrate(
        self, seconds: float, *, multiplier: float | None = None, reliability: ReliabilityId | float | None = None
    ) -> HashrateMeasurement:
        return required_hashrate(self, seconds, multiplier=multiplier, reliability=reliability)

    def required_hashrate_mean(self, seconds: float) -> HashrateMeasurement:
        return required_hashrate_mean(self, seconds)

    def required_hashrate_quantile(self, seconds: float, confidence: float) -> HashrateMeasurement:
        return required_hashrate_quantile(self, seconds, confidence)

    def target(self) -> int:
        return target_for(self)

    def combine_serial(self, *others: LabelInput) -> "Sharenote":
        return combine_notes_serial((self, *others))

    def difference(self, other: LabelInput) -> "Sharenote":
        return note_difference(self, other)

    def scale(self, factor: float) -> "Sharenote":
        return scale_note(self, factor)

    def nbits(self) -> str:
        return sharenote_to_nbits(self)


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


@dataclass(frozen=True)
class HashrateMeasurement:
    value: float

    def human(self, precision: int | None = None) -> HumanHashrate:
        return human_hashrate(self.value, precision=precision)

    def __float__(self) -> float:  # pragma: no cover - helper
        return self.value

    def __str__(self) -> str:  # pragma: no cover - helper
        return self.human().display


@dataclass(frozen=True)
class HashesMeasurement:
    value: float

    def __float__(self) -> float:  # pragma: no cover - helper
        return self.value

    def __str__(self) -> str:  # pragma: no cover - helper
        return _format_hash_count(self.value)


@dataclass(frozen=True)
class HashrateRange:
    """Inclusive lower bound and exclusive upper bound hashrate range for a note."""

    minimum: float
    maximum: float

    def human(self, precision: int | None = None) -> tuple[HumanHashrate, HumanHashrate]:
        return (
            human_hashrate(self.minimum, precision=precision),
            human_hashrate(self.maximum, precision=precision),
        )


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
    zbits: float
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

_HASH_COUNT_UNITS: Sequence[tuple[str, int]] = (
    ("", 0),
    ("K", 1),
    ("M", 2),
    ("G", 3),
    ("T", 4),
    ("P", 5),
    ("E", 6),
    ("Z", 7),
    ("Y", 8),
)


def _assert_finite(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise SharenoteError(f"{field} must be a finite number")


def _clamp_cents(value: int) -> int:
    if not isinstance(value, (int, float)):
        raise SharenoteError("cents must be numeric")
    rounded = int(round(value))
    if rounded < MIN_CENTZ:
        return MIN_CENTZ
    if rounded > MAX_CENTZ:
        return MAX_CENTZ
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


def format_zbits_label(zbits: float, precision: int = 8) -> str:
    return f"{zbits:.{precision}f}Z"


def zbits_from_components(z: int, cents: int) -> float:
    if not isinstance(z, int) or z < 0:
        raise SharenoteError("z must be a non-negative integer")
    cents_norm = _clamp_cents(cents)
    return z + cents_norm * CENT_ZBIT_STEP


def _note_from_components(z: int, cents: int) -> Sharenote:
    normalized_z = int(z)
    normalized_cents = _clamp_cents(cents)
    zbits = zbits_from_components(normalized_z, normalized_cents)
    return Sharenote(z=normalized_z, cents=normalized_cents, zbits=zbits)


def note_from_centz_bits(centz: int) -> Sharenote:
    if not isinstance(centz, (int, float)):
        raise SharenoteError("cent-z value must be numeric")
    if centz < 0:
        raise SharenoteError("cent-z value must be non-negative")
    z = int(centz) // CENTZ_UNITS_PER_Z
    cents = int(centz) % CENTZ_UNITS_PER_Z
    return _note_from_components(z, cents)


def note_from_components(z: int, cents: int) -> Sharenote:
    return _note_from_components(z, cents)


def _label_components_from_zbits(zbits: float) -> Tuple[int, int]:
    z = floor(zbits)
    fractional = zbits - z
    raw_cents = int((fractional / CENT_ZBIT_STEP) + 1e-9)
    return int(max(0, z)), _clamp_cents(raw_cents)


def note_from_zbits(zbits: float) -> Sharenote:
    _assert_finite(zbits, "zbits")
    if zbits < 0:
        raise SharenoteError("zbits must be non-negative")
    z, cents = _label_components_from_zbits(zbits)
    return Sharenote(z=z, cents=cents, zbits=zbits)


def must_note_from_zbits(zbits: float) -> Sharenote:
    return note_from_zbits(zbits)


def must_note_from_centz_bits(centz: int) -> Sharenote:
    return note_from_centz_bits(centz)


def difficulty_from_zbits(zbits: float) -> float:
    return 2.0 ** zbits


def difficulty_from_note(note: LabelInput) -> float:
    resolved = ensure_note(note)
    return difficulty_from_zbits(resolved.zbits)


def zbits_from_difficulty(difficulty: float) -> float:
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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        _assert_finite(numeric, "zbits")
        if numeric < 0:
            raise SharenoteError("zbits must be non-negative")
        return note_from_zbits(numeric)
    if isinstance(value, str):
        return _parse_label(value)
    if isinstance(value, tuple) and len(value) == 2:
        return _note_from_components(int(value[0]), int(value[1]))
    if isinstance(value, Mapping):
        z, cents = _normalise_mapping(value)
        return _note_from_components(z, cents)
    raise SharenoteError("unsupported note input")


def _parse_label(label: str) -> Sharenote:
    cleaned = label.strip().upper().replace(" ", "")

    if match := _LABEL_STANDARD.match(cleaned):
        z = int(match.group(1))
        cents = int(match.group(2)) if match.group(2) else 0
        return _note_from_components(z, cents)

    if match := _LABEL_DOTTED.match(cleaned):
        z = int(match.group(1))
        decimals = match.group(2).ljust(2, "0")[:2]
        cents = int(decimals)
        return _note_from_components(z, cents)

    if match := _LABEL_DECIMAL.match(cleaned):
        bits = float(match.group(1))
        return note_from_zbits(bits)

    raise SharenoteError(f"unrecognised Sharenote label: '{label}'")


def probability_from_zbits(zbits: float) -> float:
    _assert_finite(zbits, "zbits")
    return 2.0 ** (-zbits)


def probability_per_hash(note: LabelInput) -> float:
    resolved = ensure_note(note)
    return probability_from_zbits(resolved.zbits)


def _expected_hashes_value_from_zbits(zbits: float) -> float:
    return 1.0 / probability_from_zbits(zbits)


def expected_hashes_for_zbits(zbits: float) -> HashesMeasurement:
    return HashesMeasurement(_expected_hashes_value_from_zbits(zbits))


def expected_hashes_for_note(note: LabelInput) -> HashesMeasurement:
    resolved = ensure_note(note)
    return expected_hashes_for_zbits(resolved.zbits)


def expected_hashes_measurement(note: LabelInput) -> HashesMeasurement:
    return expected_hashes_for_note(note)


def _required_hashrate_value(
    note: LabelInput,
    seconds: float,
    *,
    multiplier: float,
) -> float:
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    resolved = ensure_note(note)
    expected = _expected_hashes_value_from_zbits(resolved.zbits)
    return expected * multiplier / seconds


def required_hashrate(
    note: LabelInput,
    seconds: float,
    *,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
) -> HashrateMeasurement:
    resolved_multiplier, _ = _resolve_multiplier(multiplier, reliability)
    return HashrateMeasurement(
        _required_hashrate_value(note, seconds, multiplier=resolved_multiplier)
    )


def required_hashrate_mean(note: LabelInput, seconds: float) -> HashrateMeasurement:
    return required_hashrate(note, seconds, multiplier=1.0)


def required_hashrate_quantile(
    note: LabelInput, seconds: float, confidence: float
) -> HashrateMeasurement:
    if confidence <= 0 or confidence >= 1:
        raise SharenoteError("confidence must be in (0,1)")
    return required_hashrate(note, seconds, reliability=confidence)


def required_hashrate_measurement(
    note: LabelInput, seconds: float, *, multiplier: float | None = None, reliability: ReliabilityId | float | None = None
) -> HashrateMeasurement:
    return required_hashrate(note, seconds, multiplier=multiplier, reliability=reliability)


def required_hashrate_mean_measurement(note: LabelInput, seconds: float) -> HashrateMeasurement:
    return required_hashrate_mean(note, seconds)


def required_hashrate_quantile_measurement(
    note: LabelInput, seconds: float, confidence: float
) -> HashrateMeasurement:
    return required_hashrate_quantile(note, seconds, confidence)


def hashrate_range_for_note(
    note: LabelInput,
    seconds: float,
    *,
    multiplier: float | None = None,
    reliability: ReliabilityId | float | None = None,
) -> HashrateRange:
    """Returns the [min, max) hashrate that maps to this note for the given window."""
    _assert_finite(seconds, "seconds")
    if seconds <= 0:
        raise SharenoteError("seconds must be greater than zero")
    resolved_note = ensure_note(note)
    resolved_multiplier, _ = _resolve_multiplier(multiplier, reliability)
    lower_expected = _expected_hashes_value_from_zbits(resolved_note.zbits)
    lower = lower_expected * resolved_multiplier / seconds
    upper_zbits = resolved_note.zbits + CENT_ZBIT_STEP
    upper_expected = _expected_hashes_value_from_zbits(upper_zbits)
    upper = upper_expected * resolved_multiplier / seconds
    return HashrateRange(minimum=lower, maximum=upper)


def max_zbits_for_hashrate(
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
    zbits = max_zbits_for_hashrate(numeric_hashrate, seconds, resolved_multiplier)
    return note_from_zbits(zbits)


def target_for(note: LabelInput) -> int:
    resolved = ensure_note(note)
    integer_bits = floor(resolved.zbits)
    base_exponent = 256 - integer_bits
    if base_exponent < 0:
        raise SharenoteError("z too large; target would underflow")
    fractional = resolved.zbits - integer_bits
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
    zbits = 256 - log2_target
    return note_from_zbits(zbits)


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


def sharenote_to_nbits(note: LabelInput) -> str:
    target = target_for(note)
    compact = _target_to_compact(target)
    return f"{compact:08x}"


def get_reliability_levels() -> Iterable[ReliabilityLevel]:
    return _RELIABILITY_LEVELS.values()


def format_probability_display(zbits: float, precision: int = 8) -> str:
    _assert_finite(zbits, "zbits")
    return f"1 / 2^{zbits:.{precision}f}"


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


def human_hashrate(hashrate: float, precision: int | None = None) -> HumanHashrate:
    _assert_finite(hashrate, "hashrate")
    if hashrate <= 0:
        return HumanHashrate(0.0, HashrateUnit.HPS, "0 H/s", 0)

    log_value = log10(hashrate)
    unit_index = min(len(_HASHRATE_UNITS) - 1, max(0, int(log_value // 3)))
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


def _format_hash_count(value: float) -> str:
    if not isfinite(value) or value <= 0:
        return "0 H/s"
    index = min(len(_HASH_COUNT_UNITS) - 1, int(max(0, log10(value) // 3)))
    prefix, exponent = _HASH_COUNT_UNITS[index]
    scaled = value / (10 ** (exponent * 3))
    if not isfinite(scaled) or scaled <= 0:
        return "0 H/s"
    if scaled >= 100:
        display = f"{scaled:.0f}"
    elif scaled >= 10:
        display = f"{scaled:.1f}"
    else:
        display = f"{scaled:.2f}"
    label = f"{prefix}H/s" if prefix else "H/s"
    return f"{display} {label}"


def with_human_hashrate_precision(precision: int) -> dict[str, int]:
    return {"precision": max(0, int(precision))}


def with_multiplier(multiplier: float) -> dict[str, float]:
    _assert_finite(multiplier, "multiplier")
    if multiplier <= 0:
        raise SharenoteError("multiplier must be > 0")
    return {"multiplier": float(multiplier)}


def with_reliability(reliability: ReliabilityId) -> dict[str, ReliabilityId]:
    return {"reliability": reliability}


def with_confidence(confidence: float) -> dict[str, float]:
    if confidence <= 0 or confidence >= 1:
        raise SharenoteError("confidence must be in (0,1)")
    return {"reliability": float(confidence)}


def with_estimate_multiplier(multiplier: float) -> dict[str, float]:
    return with_multiplier(multiplier)


def with_estimate_reliability(reliability: ReliabilityId) -> dict[str, ReliabilityId]:
    return with_reliability(reliability)


def with_estimate_confidence(confidence: float) -> dict[str, float]:
    return with_confidence(confidence)


def with_estimate_primary_mode(mode: PrimaryMode) -> dict[str, PrimaryMode]:
    return {"primary_mode": mode}


def with_estimate_probability_precision(precision: int) -> dict[str, int]:
    return {"probability_precision": max(0, int(precision))}


def with_plan_multiplier(multiplier: float) -> dict[str, float]:
    return {"multiplier": float(multiplier)}


def with_plan_reliability(reliability: ReliabilityId) -> dict[str, ReliabilityId]:
    return {"reliability": reliability}


def with_plan_confidence(confidence: float) -> dict[str, float]:
    return {"reliability": float(confidence)}


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
    expectation = expected_hashes_for_zbits(resolved.zbits)
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
        zbits=resolved.zbits,
        seconds_target=seconds,
        probability_per_hash=probability,
        probability_display=format_probability_display(
            resolved.zbits, probability_precision
        ),
        expected_hashes=expectation.value,
        required_hashrate_mean=mean.value,
        required_hashrate_quantile=quantile_hashrate.value,
        required_hashrate_primary=primary.value,
        required_hashrate_human=primary.human(),
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
        return note_from_zbits(0.0)
    return note_from_zbits(zbits_from_difficulty(total_difficulty))


def note_difference(
    minuend: LabelInput,
    subtrahend: LabelInput,
) -> Sharenote:
    diff = difficulty_from_note(minuend) - difficulty_from_note(subtrahend)
    if diff <= 0:
        return note_from_zbits(0.0)
    return note_from_zbits(zbits_from_difficulty(diff))


def scale_note(note: LabelInput, factor: float) -> Sharenote:
    _assert_finite(factor, "factor")
    if factor < 0:
        raise SharenoteError("factor must be >= 0")
    if factor == 0:
        return note_from_zbits(0.0)
    difficulty = difficulty_from_note(note) * factor
    if difficulty < 1.0:
        return note_from_zbits(0.0)
    return note_from_zbits(zbits_from_difficulty(difficulty))


def divide_notes(numerator: LabelInput, denominator: LabelInput) -> float:
    num = difficulty_from_note(numerator)
    den = difficulty_from_note(denominator)
    if den <= 0:
        raise SharenoteError("division by a zero-difficulty note")
    return num / den
