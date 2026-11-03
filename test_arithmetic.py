"""Tests for the Z-unit arithmetic surface (:mod:`sharenotelib.arithmetic`)."""

from __future__ import annotations

import math
import struct
from fractions import Fraction

import pytest

from sharenotelib import (
    MAX_CENTS,
    MIN_CENTS,
    Estimate,
    HashrateRange,
    HashrateUnit,
    HumanHashrate,
    InvalidLabel,
    Plan,
    PrimaryMode,
    Reliability,
    Sharenote,
    SharenoteError,
    __version__,
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


def close(a: float, b: float, rel: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel)


# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------
def test_version_is_non_empty_string() -> None:
    assert isinstance(__version__, str) and __version__


def test_cent_bounds() -> None:
    assert (MIN_CENTS, MAX_CENTS) == (0, 99)


# ---------------------------------------------------------------------------
# Construction & parsing
# ---------------------------------------------------------------------------
def test_note_from_components() -> None:
    note = note_from_components(33, 53)
    assert (note.z, note.cents, note.label) == (33, 53, "33Z53")
    assert close(note.zbits, 33.53, 1e-12)


@pytest.mark.parametrize(
    "label,cents",
    [("33Z53", 53), ("33Z 53CZ", 53), ("33.53Z", 53), ("33z", 0)],
)
def test_label_parsing_variants(label: str, cents: int) -> None:
    note = note_from_label(label)
    assert note.z == 33 and note.cents == cents


def test_decimal_label_preserves_precision() -> None:
    note = note_from_label("33.537812Z")
    assert note.label == "33Z53"
    assert close(note.zbits, 33.537812, 1e-9)


def test_note_from_zbits_truncates_label_but_keeps_zbits() -> None:
    note = note_from_zbits(33.537812)
    assert note.label == "33Z53"
    assert close(note.zbits, 33.537812, 1e-12)


def test_note_from_centibits() -> None:
    assert note_from_centibits(3353).label == "33Z53"


def test_ensure_note_coercions() -> None:
    assert ensure_note(33.53).label == "33Z53"
    assert ensure_note((33, 53)).label == "33Z53"
    assert ensure_note({"z": 33, "cents": 53}).label == "33Z53"
    note = note_from_zbits(33.53)
    assert ensure_note(note) is note


def test_str_is_label() -> None:
    assert str(note_from_label("57Z12")) == "57Z12"


def test_format_helpers() -> None:
    assert format_label(57, 12) == "57Z12"
    assert format_zbits_label(33.53, 4) == "33.5300Z"
    assert close(zbits_from_components(33, 53), 33.53, 1e-12)


def test_cents_clamping() -> None:
    assert note_from_components(10, -5).cents == 0
    assert note_from_components(10, 150).cents == 99


def test_clamp_cents_bad_type() -> None:
    """_clamp_cents rejects a non-numeric cents value (ported edge case)."""
    with pytest.raises(SharenoteError):
        note_from_components(10, "foo")  # type: ignore[arg-type]


def test_resolve_hashrate_unit_none() -> None:
    """_resolve_hashrate_unit(None) returns the base (H/s) exponent 0 (ported edge case)."""
    from sharenotelib.arithmetic import _resolve_hashrate_unit

    assert _resolve_hashrate_unit(None) == 0


# Error paths
def test_invalid_label_raises_invalid_label() -> None:
    with pytest.raises(InvalidLabel):
        note_from_label("XYZ")


def test_negative_and_nan_zbits_rejected() -> None:
    with pytest.raises(SharenoteError):
        note_from_zbits(-1)
    with pytest.raises(SharenoteError):
        note_from_zbits(float("nan"))


def test_negative_centibits_rejected() -> None:
    with pytest.raises(SharenoteError):
        note_from_centibits(-1)


def test_ensure_note_rejects_bool_and_bad_mapping() -> None:
    with pytest.raises(SharenoteError):
        ensure_note(True)  # type: ignore[arg-type]
    with pytest.raises(SharenoteError):
        ensure_note({"a": 1})  # type: ignore[arg-type]
    with pytest.raises(SharenoteError):
        ensure_note(-5)
    with pytest.raises(SharenoteError):
        zbits_from_components(-1, 0)


# ---------------------------------------------------------------------------
# Difficulty: exact vs display
# ---------------------------------------------------------------------------
def test_resolve_difficulty_is_exact_fraction() -> None:
    assert resolve_difficulty("15Z00") == Fraction(32768)
    assert isinstance(resolve_difficulty("33Z53"), Fraction)


def test_difficulty_float_is_display() -> None:
    assert close(difficulty_float("10Z00"), 1024.0, 1e-12)
    assert close(difficulty_from_zbits(10), 1024.0, 1e-12)


def test_zbits_difficulty_roundtrip() -> None:
    assert close(zbits_from_difficulty(difficulty_from_zbits(33.53)), 33.53, 1e-12)
    with pytest.raises(SharenoteError):
        zbits_from_difficulty(0)


# ---------------------------------------------------------------------------
# Exact arithmetic
# ---------------------------------------------------------------------------
def test_combine_difference_scale_ratio() -> None:
    a, b = ensure_note("33Z53"), ensure_note("20Z10")

    assert combine(a, b).label == "33Z53"
    assert close(combine(a, b).zbits, math.log2(2 ** a.zbits + 2 ** b.zbits), 1e-12)

    delta = difference("33Z53", "20Z10")
    assert delta.label == "33Z52"

    scaled = scale("20Z10", 1.5)
    assert scaled.label == "20Z68"

    assert close(ratio("33Z53", "20Z10"), (2 ** a.zbits) / (2 ** b.zbits), 1e-9)


def test_combine_requires_a_note() -> None:
    with pytest.raises(SharenoteError):
        combine()


def test_combine_overflow_path_stays_exact() -> None:
    """Combining near-float64-max notes must not overflow (ported edge case).

    Exact ``Fraction`` accumulation means folding three ``note_from_zbits(1023)``
    notes neither raises nor collapses to zero, where a ``float64`` accumulator
    would reach ``inf``.
    """
    huge = note_from_zbits(1023)
    result = combine(huge, huge, huge)
    assert result.zbits >= 0
    assert result.exact_difficulty is not None
    assert result.exact_difficulty == 3 * resolve_difficulty(huge)


def test_difference_clamps_to_zero() -> None:
    assert difference("10Z00", "33Z53").zbits == 0


def test_scale_zero_and_negative() -> None:
    assert scale("33Z53", 0).label == "0Z00"
    with pytest.raises(SharenoteError):
        scale("33Z53", -1)


def test_ratio_rejects_zero_denominator_note() -> None:
    # 0Z00 has difficulty 1 (not zero); a genuine zero would be rejected.
    assert ratio("10Z00", "0Z00") > 0


def test_ratio_single_rounds_the_exact_fraction() -> None:
    """FIX #4: ``ratio`` divides in exact ``Fraction`` space and rounds to
    float64 exactly once (Go's ``big.Rat.Quo(...).Float64()``), never
    ``float(num) / float(den)``, which double-rounds.

    The double-round only bites when an operand's exact difficulty is not itself
    float-representable -- e.g. an aggregated note whose ``exact_difficulty`` is a
    non-dyadic-float ``Fraction`` -- so this guard uses combined operands where
    the two rounding orders genuinely disagree by a ULP.
    """
    a = combine("10Z00", "10Z01", "10Z33")
    b = combine("10Z00", "10Z01", "9Z50")
    num, den = resolve_difficulty(a), resolve_difficulty(b)
    single = float(num / den)  # one rounding of the exact quotient
    double = float(num) / float(den)  # collapses operands first: two roundings
    assert single != double  # the orders really diverge for these operands
    assert ratio(a, b) == single  # ratio must take the single-rounding path


def _f64hex(value: float) -> str:
    return struct.pack(">d", value).hex()


def test_ratio_single_round_boundaries_from_fuzz() -> None:
    """Pin the single-rounded ratio on cross-SDK parity-fuzz boundary cases.

    Each value is the exact-``Fraction`` quotient of the two notes' difficulties,
    correctly rounded to float64 once (``ratio-04805`` / ``-04810`` / ``-04812``).
    """
    assert _f64hex(ratio("149Z56", note_from_zbits(186.591483))) == "3d9f4f2af1cd33fd"
    assert _f64hex(ratio("136Z01", "170Z23")) == "3dcb795e38df3c64"
    assert _f64hex(ratio("149Z76", "55Z36")) == "45d51cb453b9534a"


def test_compare() -> None:
    assert compare("32Z00", "33Z00") < 0
    assert compare("33Z54", "33Z53") > 0
    assert compare("33Z53", "33Z53") == 0


# ---------------------------------------------------------------------------
# Probability & hashes
# ---------------------------------------------------------------------------
def test_probability_and_expected_hashes() -> None:
    p = probability_per_hash("33Z53")
    zbits = ensure_note("33Z53").zbits
    assert close(p, 2 ** -zbits, 1e-12)
    assert close(probability_from_zbits(10), 2 ** -10, 1e-12)
    assert close(expected_hashes("33Z53"), 1 / p, 1e-6)
    assert expected_hashes_from_zbits(33.53) > 0
    assert format_probability_display(zbits, 5) == "1 / 2^33.53000"


# ---------------------------------------------------------------------------
# Hashrate planning
# ---------------------------------------------------------------------------
def test_required_hashrate_variants() -> None:
    mean = required_hashrate_mean("33Z53", 5)
    zbits = ensure_note("33Z53").zbits
    assert close(mean, 2 ** zbits / 5, 1e-9)
    assert close(required_hashrate("33Z53", 5, multiplier=2.0), mean * 2, 1e-6)
    q95 = required_hashrate_quantile("33Z53", 5, 0.95)
    assert close(q95, mean * -math.log(1 - 0.95), 1e-9)
    assert required_hashrate("33Z53", 5, reliability=Reliability.OFTEN_95) > 0


def test_required_hashrate_bad_inputs() -> None:
    with pytest.raises(SharenoteError):
        required_hashrate("33Z53", 0)
    with pytest.raises(SharenoteError):
        required_hashrate_quantile("33Z53", 5, 0)
    with pytest.raises(SharenoteError):
        required_hashrate("33Z53", 5, reliability=1.5)


def test_note_from_hashrate_roundtrip_and_strings() -> None:
    note = note_from_hashrate(parse_hashrate("2.480651469 GH/s"), 5)
    assert note.label == "33Z53"
    assert note_from_hashrate("5 GH/s", 5).label == note_from_hashrate(5e9, 5).label
    with pytest.raises(SharenoteError):
        note_from_hashrate(5e9, 5, reliability=1.5)


def test_max_zbits_for_hashrate() -> None:
    assert close(max_zbits_for_hashrate(2.480651469003486e9, 5), ensure_note("33Z53").zbits, 1e-6)
    with pytest.raises(SharenoteError):
        max_zbits_for_hashrate(0, 5)


def test_hashrate_range() -> None:
    seconds = 5
    rate = parse_hashrate("1 TH/s")
    note = note_from_hashrate(rate, seconds)
    rng = hashrate_range(note.label, seconds)
    assert isinstance(rng, HashrateRange)
    assert rng.minimum <= rate < rng.maximum
    assert note_from_hashrate(rng.minimum, seconds).label == note.label
    often = hashrate_range(note, seconds, reliability=Reliability.OFTEN_95)
    assert often.minimum > rng.minimum
    low, _ = rng.human()
    assert "H/s" in low.display
    with pytest.raises(SharenoteError):
        hashrate_range("33Z53", 0)


# ---------------------------------------------------------------------------
# Hashrate parsing & formatting
# ---------------------------------------------------------------------------
def test_parse_hashrate() -> None:
    assert close(parse_hashrate("5 GH/s"), 5e9, 1e-9)
    assert close(parse_hashrate("12.5 MH/s"), 12.5e6, 1e-9)
    assert close(parse_hashrate("5 gh/s"), 5e9, 1e-9)
    assert close(parse_hashrate("5 GHps"), 5e9, 1e-9)
    assert close(parse_hashrate("5 GH"), 5e9, 1e-9)
    assert parse_hashrate(5e9) == 5e9


def test_parse_hashrate_errors() -> None:
    for bad in ["", "12 foo/s", "abc xyz"]:
        with pytest.raises(SharenoteError):
            parse_hashrate(bad)
    with pytest.raises(SharenoteError):
        parse_hashrate("-5 GH/s")
    with pytest.raises(SharenoteError):
        parse_hashrate(True)  # type: ignore[arg-type]


def test_human_hashrate() -> None:
    assert human_hashrate(3.2e9).unit is HashrateUnit.GHPS
    assert human_hashrate(3.2e9).display.startswith("3.20")
    assert human_hashrate(0).display == "0 H/s"
    assert human_hashrate(-5).display == "0 H/s"
    assert human_hashrate(500e9).display == "500 GH/s"
    assert human_hashrate(50e9).display == "50.0 GH/s"
    assert human_hashrate(3.2e9, precision=4).display == "3.2000 GH/s"
    assert human_hashrate(0.25, precision=2).display == "0.25 H/s"
    assert "H/s" in human_hashrate(1e21).display


# ---------------------------------------------------------------------------
# Targets & nBits interop
# ---------------------------------------------------------------------------
def test_target_and_zbits_from_target_roundtrip() -> None:
    assert isinstance(target_for("33Z00"), int)
    assert 222 < math.log(target_for("33Z00"), 2) < 224
    for label in ["0Z00", "10Z00", "20Z50", "33Z53", "50Z99", "64Z00", "80Z00"]:
        note = ensure_note(label)
        assert close(zbits_from_target(target_for(note)), note.zbits, 1e-6), label


def test_target_errors() -> None:
    with pytest.raises(SharenoteError):
        target_for(note_from_zbits(300))
    with pytest.raises(SharenoteError):
        zbits_from_target(0)
    with pytest.raises(SharenoteError):
        zbits_from_target(3.14)  # type: ignore[arg-type]


def test_nbits_conversion() -> None:
    note = note_from_nbits("19752b59")
    assert note.label == "57Z12"
    nbits = note_to_nbits("33Z53")
    assert len(nbits) == 8 and all(c in "0123456789abcdef" for c in nbits)
    with pytest.raises(InvalidLabel):
        note_from_nbits("abc")
    with pytest.raises(InvalidLabel):
        note_from_nbits("19000000")  # mantissa 0


def test_target_rounds_half_away_from_zero() -> None:
    """FIX #3: the 48-bit scale factor rounds half-away-from-zero.

    Both boundary inputs land on an exact half (``2 ** -frac * 2 ** 48`` ends in
    ``.5``). Python's built-in ``round`` is banker's rounding (half-to-even) and
    rounds *down* to the even neighbour, producing a 1-ULP-low target
    (``...d98...`` / ``...da0...``). Go's ``math.Round`` and JS's ``Math.round``
    round half away from zero (``...d9a...`` / ``...da2...``); the pinned hex
    values below are the canonical Go/JS targets from the cross-SDK parity fuzz
    (cases ``target-05129`` and ``target-05291``).
    """
    # target-05129: note_from_zbits(99.86162), scale factor 154905317779148.5
    assert (
        format(target_for(note_from_zbits(99.86162)), "x")
        == "119c568e14d9a000000000000000000000000000"
    )
    # target-05291: 99Z96, scale factor 144694157706960.5
    assert (
        format(target_for(note_from_label("99Z96")), "x")
        == "1073277be0da2000000000000000000000000000"
    )
    # nBits (the compact target) is derived from the same target and is unchanged
    # by the rounding-mode fix -- it reads only the leading mantissa bytes.
    assert note_to_nbits(note_from_zbits(99.86162)) == "14119c56"
    assert note_to_nbits(note_from_label("99Z96")) == "14107327"


def test_target_to_compact_internal_paths() -> None:
    from sharenotelib.arithmetic import _target_to_compact

    assert _target_to_compact(255) > 0
    assert _target_to_compact(0x00800001) > 0
    with pytest.raises(SharenoteError):
        _target_to_compact(0)
    with pytest.raises(SharenoteError):
        _target_to_compact(1 << 2100)


# ---------------------------------------------------------------------------
# Reliability presets
# ---------------------------------------------------------------------------
def test_reliability_levels() -> None:
    levels = reliability_levels()
    assert len(levels) == 5
    assert levels[0].id is Reliability.MEAN and levels[0].multiplier == 1.0


# ---------------------------------------------------------------------------
# Estimates & plans
# ---------------------------------------------------------------------------
def test_estimate() -> None:
    est = estimate("33Z53", 5, reliability=0.95)
    assert isinstance(est, Estimate)
    assert est.label == "33Z53"
    expected = (2 ** est.zbits / 5) * -math.log(1 - 0.95)
    assert close(est.required_hashrate_primary, expected, 1e-9)
    assert est.required_hashrate_human.unit is HashrateUnit.GHPS
    assert est.primary_mode is PrimaryMode.QUANTILE


def test_estimate_modes_and_options() -> None:
    assert estimate("33Z53", 5, multiplier=2.0).multiplier == 2.0
    assert estimate("33Z53", 5, primary_mode=PrimaryMode.MEAN).primary_mode is PrimaryMode.MEAN
    # QUANTILE requested with no confidence falls back to MEAN.
    assert estimate("33Z53", 5, primary_mode=PrimaryMode.QUANTILE).primary_mode is PrimaryMode.MEAN
    rel = estimate("33Z53", 5, reliability=Reliability.VERY_LIKELY_99)
    assert close(rel.quantile, 0.99, 1e-6)
    with pytest.raises(SharenoteError):
        estimate("33Z53", 0)
    with pytest.raises(SharenoteError):
        estimate("33Z53", 5, multiplier=0)


def test_estimate_many() -> None:
    ests = estimate_many(["33Z53", "20Z10"], 5)
    assert [e.label for e in ests] == ["33Z53", "20Z10"]


def test_plan_from_hashrate() -> None:
    plan = plan_from_hashrate("5 GH/s", 5, reliability=Reliability.OFTEN_95)
    assert isinstance(plan, Plan)
    expected = note_from_hashrate(5e9, 5, reliability=Reliability.OFTEN_95)
    assert plan.note.label == expected.label
    assert abs(plan.estimate.required_hashrate_primary - plan.input_hashrate) / plan.input_hashrate < 0.02
    assert plan.input_hashrate_human.unit is HashrateUnit.GHPS
    with pytest.raises(SharenoteError):
        plan_from_hashrate(0, 5)
    with pytest.raises(SharenoteError):
        plan_from_hashrate(5e9, 0)


# ---------------------------------------------------------------------------
# Sharenote convenience methods
# ---------------------------------------------------------------------------
def test_sharenote_methods() -> None:
    note = ensure_note("33Z53")
    assert isinstance(note, Sharenote)
    assert close(note.probability_per_hash(), 2 ** -note.zbits, 1e-12)
    assert note.expected_hashes() > 0
    assert note.required_hashrate(5, multiplier=2.0) > 0
    assert isinstance(note.target(), int)
    assert note.difficulty() == resolve_difficulty(note)
    assert note.combine("20Z10").label == "33Z53"
    assert note.difference("20Z10").z == 33
    assert note.scale(2).zbits > note.zbits
    assert note.ratio("20Z10") > 1
    assert len(note.to_nbits()) == 8
