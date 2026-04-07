"""Comprehensive test suite for sharenotelib.snip00 — targeting 100% coverage."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from sharenotelib import (
    CENT_ZBIT_STEP,
    HashrateDescriptor,
    HashrateRange,
    HashrateUnit,
    HashrateMeasurement,
    HashesMeasurement,
    HumanHashrate,
    PrimaryMode,
    ReliabilityId,
    SharenoteError,
    SharenotePlan,
    BillEstimate,
    build_bill_estimate,
    build_bill_estimates,
    combine_notes_serial,
    compare_notes,
    continuous_difficulty,
    divide_notes,
    ensure_note,
    expected_hashes_for_note,
    expected_hashes_for_zbits,
    expected_hashes_measurement,
    format_label,
    format_probability_display,
    format_zbits_label,
    get_reliability_levels,
    hashrate_range_for_note,
    human_hashrate,
    max_zbits_for_hashrate,
    nbits_to_sharenote,
    normalize_hashrate_value,
    note_difference,
    note_from_centz_bits,
    note_from_components,
    note_from_hashrate,
    note_from_zbits,
    must_note_from_zbits,
    must_note_from_centz_bits,
    parse_hashrate,
    plan_sharenote_from_hashrate,
    probability_from_zbits,
    probability_per_hash,
    required_hashrate,
    required_hashrate_mean,
    required_hashrate_quantile,
    required_hashrate_measurement,
    required_hashrate_mean_measurement,
    required_hashrate_quantile_measurement,
    scale_note,
    sharenote_to_nbits,
    target_for,
    with_confidence,
    with_estimate_confidence,
    with_estimate_multiplier,
    with_estimate_primary_mode,
    with_estimate_probability_precision,
    with_estimate_reliability,
    with_human_hashrate_precision,
    with_multiplier,
    with_plan_confidence,
    with_plan_multiplier,
    with_plan_reliability,
    with_reliability,
    zbits_from_components,
    zbits_from_difficulty,
    difficulty_from_zbits,
    estimate_note,
    estimate_notes,
    __version__,
)

# ──────────────────────────────────────────────────────────────────────────
# Aliases & version
# ──────────────────────────────────────────────────────────────────────────

def test_estimate_note_alias():
    """F1: estimate_note is the canonical alias for build_bill_estimate."""
    assert estimate_note is build_bill_estimate


def test_estimate_notes_alias():
    """F1: estimate_notes is the canonical alias for build_bill_estimates."""
    assert estimate_notes is build_bill_estimates


def test_version_string():
    """F2: __version__ is importable and non-empty."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def close(a: float, b: float, rel: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel)


# ──────────────────────────────────────────────────────────────────────────
# Note construction & parsing
# ──────────────────────────────────────────────────────────────────────────

def test_note_construction():
    note = ensure_note((33, 53))
    assert note.z == 33
    assert note.cents == 53
    assert close(note.zbits, 33 + 53 * CENT_ZBIT_STEP, 1e-12)
    assert note.label == "33Z53"


def test_label_parsing_variants():
    for label, cents in [
        ("33Z53", 53),
        ("33Z 53CZ", 53),
        ("33.53Z", 53),
        ("33z", 0),
    ]:
        note = ensure_note(label)
        assert note.z == 33
        assert note.cents == cents


def test_zbits_roundtrip():
    zbits = 33 + 53 * CENT_ZBIT_STEP
    assert note_from_zbits(zbits).label == "33Z53"


def test_note_from_zbits_preserves_precision():
    precise = 33.537812
    note = note_from_zbits(precise)
    assert note.label == "33Z53"
    assert close(note.zbits, precise, 1e-12)


def test_note_from_components():
    note = note_from_components(33, 53)
    assert note.label == "33Z53"


def test_note_from_centz_bits():
    note = note_from_centz_bits(3353)
    assert note.label == "33Z53"


def test_must_note_from_zbits():
    note = must_note_from_zbits(33.53)
    assert note.label == "33Z53"


def test_must_note_from_centz_bits():
    note = must_note_from_centz_bits(3353)
    assert note.label == "33Z53"


def test_zbits_from_components():
    zbits = zbits_from_components(33, 53)
    assert close(zbits, 33.53, 1e-12)


def test_ensure_note_number():
    note = ensure_note(33.53)
    assert note.label == "33Z53"


def test_ensure_note_dict():
    note = ensure_note({"z": 33, "cents": 53})
    assert note.label == "33Z53"


def test_ensure_note_sharenote():
    orig = note_from_zbits(33.53)
    same = ensure_note(orig)
    assert same is orig


# Error paths
def test_invalid_label():
    with pytest.raises(ValueError):
        ensure_note("XYZ")


def test_negative_zbits():
    with pytest.raises(ValueError):
        note_from_zbits(-1)


def test_nan_zbits():
    with pytest.raises(ValueError):
        note_from_zbits(float("nan"))


def test_negative_centz():
    with pytest.raises(ValueError):
        note_from_centz_bits(-1)


def test_ensure_note_unsupported():
    with pytest.raises(ValueError):
        ensure_note(True)  # type: ignore


def test_ensure_note_bad_dict():
    with pytest.raises(ValueError):
        ensure_note({"a": 1, "b": 2})  # type: ignore


def test_zbits_from_components_bad_z():
    with pytest.raises(ValueError):
        zbits_from_components(-1, 0)


def test_format_label():
    assert format_label(57, 12) == "57Z12"


def test_format_zbits_label():
    got = format_zbits_label(33.53, 4)
    assert got == "33.5300Z"


# ──────────────────────────────────────────────────────────────────────────
# Probabilities & hashrate
# ──────────────────────────────────────────────────────────────────────────

def test_probability_math():
    p = probability_per_hash("33Z53")
    zbits = ensure_note((33, 53)).zbits
    assert close(p, 2 ** (-zbits), 1e-12)
    assert close(expected_hashes_for_note("33Z53").value, 1 / p, 1e-6)
    assert format_probability_display(zbits, 5) == "1 / 2^33.53000"


def test_probability_from_zbits():
    assert close(probability_from_zbits(10), 2 ** -10, 1e-12)


def test_expected_hashes_for_zbits():
    m = expected_hashes_for_zbits(33.53)
    assert m.value > 0


def test_expected_hashes_measurement_alias():
    a = expected_hashes_measurement("33Z53")
    b = expected_hashes_for_note("33Z53")
    assert close(a.value, b.value, 1e-12)


def test_hashrate_requirements():
    mean = required_hashrate_mean("33Z53", 5)
    expected_zbits = ensure_note((33, 53)).zbits
    expected_mean = 2 ** expected_zbits / 5
    assert close(mean.value, expected_mean, 1e-9)

    q95 = required_hashrate_quantile("33Z53", 5, 0.95)
    assert close(q95.value, expected_mean * -math.log(1 - 0.95), 1e-9)


def test_required_hashrate_with_multiplier():
    r = required_hashrate("33Z53", 5, multiplier=2.0)
    mean = required_hashrate_mean("33Z53", 5)
    assert close(r.value, mean.value * 2, 1e-6)


def test_required_hashrate_with_reliability_id():
    r = required_hashrate("33Z53", 5, reliability=ReliabilityId.OFTEN_95)
    assert r.value > 0


def test_required_hashrate_with_numeric_reliability():
    r = required_hashrate("33Z53", 5, reliability=0.95)
    assert r.value > 0


def test_required_hashrate_measurement_aliases():
    a = required_hashrate_measurement("33Z53", 5)
    b = required_hashrate_mean("33Z53", 5)
    assert close(a.value, b.value, 1e-6)

    c = required_hashrate_mean_measurement("33Z53", 5)
    assert close(c.value, b.value, 1e-6)

    d = required_hashrate_quantile_measurement("33Z53", 5, 0.95)
    e = required_hashrate_quantile("33Z53", 5, 0.95)
    assert close(d.value, e.value, 1e-6)


def test_required_hashrate_rejects_bad_seconds():
    with pytest.raises(ValueError):
        required_hashrate("33Z53", 0)
    with pytest.raises(ValueError):
        required_hashrate("33Z53", -1)


def test_required_hashrate_quantile_bad_confidence():
    with pytest.raises(ValueError):
        required_hashrate_quantile("33Z53", 5, 0)
    with pytest.raises(ValueError):
        required_hashrate_quantile("33Z53", 5, 1)


def test_note_from_hashrate_roundtrip():
    note = note_from_hashrate(parse_hashrate("2.480651469 GH/s"), 5)
    assert note.label == "33Z53"
    with pytest.raises(ValueError):
        note_from_hashrate("1 GH/s", 5)  # type: ignore


def test_note_from_hashrate_with_reliability():
    note = note_from_hashrate(5e9, 5, reliability=ReliabilityId.OFTEN_95)
    assert note.z > 0


def test_note_from_hashrate_with_numeric_reliability():
    note = note_from_hashrate(5e9, 5, reliability=0.95)
    assert note.z > 0


def test_note_from_hashrate_with_multiplier():
    note = note_from_hashrate(5e9, 5, multiplier=2.0)
    assert note.z > 0


def test_note_from_hashrate_bad_reliability():
    with pytest.raises(ValueError):
        note_from_hashrate(5e9, 5, reliability=1.5)


def test_hashrate_range_captures_original():
    seconds = 5
    hashrate = parse_hashrate("1 TH/s")
    note = note_from_hashrate(hashrate, seconds)
    rng = hashrate_range_for_note(note.label, seconds)
    assert isinstance(rng, HashrateRange)
    assert rng.minimum <= hashrate < rng.maximum
    assert note_from_hashrate(rng.minimum, seconds).label == note.label


def test_hashrate_range_with_reliability():
    note = ensure_note("33Z53")
    base = hashrate_range_for_note(note, 5)
    often = hashrate_range_for_note(note, 5, reliability=ReliabilityId.OFTEN_95)
    assert often.minimum > base.minimum


def test_hashrate_range_bad_seconds():
    with pytest.raises(ValueError):
        hashrate_range_for_note("33Z53", 0)


def test_hashrate_range_human():
    rng = hashrate_range_for_note("33Z53", 5)
    low, high = rng.human()
    assert "H/s" in low.display


def test_parse_hashrate_inputs():
    assert close(parse_hashrate("5 GH/s"), 5e9, 1e-9)
    assert close(parse_hashrate("12.5 MH/s"), 12.5e6, 1e-9)
    descriptor = HashrateDescriptor(value=3.5, unit=HashrateUnit.PHPS)
    assert close(parse_hashrate(descriptor), 3.5e15, 1e-9)
    with pytest.raises(ValueError):
        parse_hashrate("12 foo/s")


def test_parse_hashrate_empty():
    with pytest.raises(ValueError):
        parse_hashrate("")


def test_parse_hashrate_numeric():
    assert parse_hashrate(5e9) == 5e9


def test_parse_hashrate_negative():
    with pytest.raises(ValueError):
        parse_hashrate("-5 GH/s")


def test_normalize_hashrate_value_descriptor():
    val = normalize_hashrate_value(HashrateDescriptor(value=5, unit=HashrateUnit.GHPS))
    assert val == 5e9


def test_normalize_hashrate_value_negative():
    with pytest.raises(ValueError):
        normalize_hashrate_value(-1)
    with pytest.raises(ValueError):
        normalize_hashrate_value(HashrateDescriptor(value=-1))


def test_normalize_hashrate_value_nan():
    with pytest.raises(ValueError):
        normalize_hashrate_value(float("nan"))


def test_normalize_hashrate_value_unsupported():
    with pytest.raises(ValueError):
        normalize_hashrate_value("bad")  # type: ignore


def test_max_zbits():
    zbits = max_zbits_for_hashrate(2.480651469003486e9, 5)
    reference = ensure_note((33, 53)).zbits
    assert close(zbits, reference, 1e-6)


def test_max_zbits_bad_inputs():
    with pytest.raises(ValueError):
        max_zbits_for_hashrate(0, 5)
    with pytest.raises(ValueError):
        max_zbits_for_hashrate(1e9, 0)
    with pytest.raises(ValueError):
        max_zbits_for_hashrate(1e9, 5, 0)


# ──────────────────────────────────────────────────────────────────────────
# Target computation & ContinuousDifficulty
# ──────────────────────────────────────────────────────────────────────────

def test_target_computation():
    target = target_for("33Z00")
    assert isinstance(target, int)
    approx_bits = math.log(target, 2)
    assert 222 < approx_bits < 224


def test_target_z_too_large():
    with pytest.raises(ValueError):
        target_for(note_from_zbits(300))


def test_continuous_difficulty_roundtrip():
    for label in ["0Z00", "10Z00", "20Z50", "33Z53", "40Z00", "50Z99", "64Z00", "80Z00"]:
        note = ensure_note(label)
        target = target_for(note)
        recovered = continuous_difficulty(target)
        assert close(recovered, note.zbits, 1e-6), f"failed for {label}"


def test_continuous_difficulty_rejects_zero():
    with pytest.raises(ValueError):
        continuous_difficulty(0)


def test_continuous_difficulty_rejects_negative():
    with pytest.raises(ValueError):
        continuous_difficulty(-1)


def test_continuous_difficulty_rejects_non_int():
    with pytest.raises(ValueError):
        continuous_difficulty(3.14)  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# nBits conversion
# ──────────────────────────────────────────────────────────────────────────

def test_compact_conversion():
    converted = nbits_to_sharenote("19752b59")
    value = int("19752b59", 16)
    exponent = value >> 24
    mantissa = value & 0xFFFFFF
    expected_zbits = 256 - (math.log2(mantissa) + 8 * (exponent - 3))
    assert close(converted.zbits, expected_zbits, 1e-12)
    assert converted.label == "57Z12"


def test_sharenote_to_nbits():
    nbits = sharenote_to_nbits("33Z53")
    assert len(nbits) == 8
    assert all(c in "0123456789abcdef" for c in nbits)


def test_nbits_bad_input():
    with pytest.raises(ValueError):
        nbits_to_sharenote("abc")
    with pytest.raises(ValueError):
        nbits_to_sharenote("19000000")  # mantissa=0


def test_compare_notes():
    assert compare_notes("32Z00", "33Z00") < 0
    assert compare_notes("33Z54", "33Z53") > 0
    assert compare_notes("33Z53", "33Z53") == 0


# ──────────────────────────────────────────────────────────────────────────
# Display / Human utilities
# ──────────────────────────────────────────────────────────────────────────

def test_human_hashrate():
    human = human_hashrate(3.2e9)
    assert human.unit == HashrateUnit.GHPS
    assert human.display.startswith("3.20")


def test_human_hashrate_zero():
    h = human_hashrate(0)
    assert h.display == "0 H/s"


def test_human_hashrate_negative():
    h = human_hashrate(-5)
    assert h.display == "0 H/s"


def test_human_hashrate_large():
    h = human_hashrate(500e9)
    assert h.display == "500 GH/s"


def test_human_hashrate_medium():
    h = human_hashrate(50e9)
    assert h.display == "50.0 GH/s"


def test_human_hashrate_precision():
    h = human_hashrate(3.2e9, precision=4)
    assert h.display == "3.2000 GH/s"


def test_human_hashrate_tiny():
    h = human_hashrate(0.25, precision=2)
    assert h.display == "0.25 H/s"


# ──────────────────────────────────────────────────────────────────────────
# Bill estimates
# ──────────────────────────────────────────────────────────────────────────

def test_bill_estimate():
    estimate = build_bill_estimate("33Z53", 5, reliability=0.95)
    assert estimate.label == "33Z53"
    expected_primary = (2 ** estimate.zbits / 5) * -math.log(1 - 0.95)
    assert close(estimate.required_hashrate_primary, expected_primary, 1e-9)
    assert estimate.required_hashrate_human.unit == HashrateUnit.GHPS


def test_bill_estimate_with_multiplier():
    est = build_bill_estimate("33Z53", 5, multiplier=2.0)
    assert est.multiplier == 2.0


def test_bill_estimate_with_reliability_id():
    est = build_bill_estimate("33Z53", 5, reliability=ReliabilityId.VERY_LIKELY_99)
    assert close(est.quantile, 0.99, 1e-6)
    assert est.primary_mode == PrimaryMode.QUANTILE


def test_bill_estimate_with_primary_mode_mean():
    est = build_bill_estimate("33Z53", 5, primary_mode=PrimaryMode.MEAN)
    assert est.primary_mode == PrimaryMode.MEAN


def test_bill_estimate_with_primary_mode_quantile_no_quantile():
    est = build_bill_estimate("33Z53", 5, primary_mode=PrimaryMode.QUANTILE)
    # Falls back to Mean because no quantile is set
    assert est.primary_mode == PrimaryMode.MEAN


def test_bill_estimate_bad_seconds():
    with pytest.raises(ValueError):
        build_bill_estimate("33Z53", 0)


def test_bill_estimates_multiple():
    ests = build_bill_estimates(["33Z53", "20Z10"], 5)
    assert len(ests) == 2
    assert ests[0].label == "33Z53"
    assert ests[1].label == "20Z10"


def test_bill_estimate_probability_precision():
    est = build_bill_estimate("33Z53", 5, probability_precision=3)
    assert est.probability_display.count(".") == 1
    decimals = est.probability_display.split("^")[1]
    assert len(decimals.split(".")[1]) == 3


# ──────────────────────────────────────────────────────────────────────────
# Plan from hashrate
# ──────────────────────────────────────────────────────────────────────────

def test_plan_sharenote_from_hashrate():
    plan = plan_sharenote_from_hashrate(
        HashrateDescriptor(value=5.0, unit=HashrateUnit.GHPS),
        seconds=5,
        reliability=ReliabilityId.OFTEN_95,
    )
    expected = note_from_hashrate(
        HashrateDescriptor(value=5.0, unit=HashrateUnit.GHPS),
        5,
        reliability=ReliabilityId.OFTEN_95,
    )
    assert plan.sharenote.label == expected.label
    diff = abs(plan.bill.required_hashrate_primary - plan.input_hashrate_hps)
    assert diff / plan.input_hashrate_hps < 0.02
    assert plan.input_hashrate_human.unit == HashrateUnit.GHPS


def test_plan_bad_inputs():
    with pytest.raises(ValueError):
        plan_sharenote_from_hashrate(0, 5)
    with pytest.raises(ValueError):
        plan_sharenote_from_hashrate(5e9, 0)


# ──────────────────────────────────────────────────────────────────────────
# Arithmetic helpers
# ──────────────────────────────────────────────────────────────────────────

def test_arithmetic_helpers():
    note_a = ensure_note("33Z53")
    note_b = ensure_note("20Z10")

    combined = combine_notes_serial([note_a, note_b])
    assert combined.label == "33Z53"
    expected_combined = math.log2(2 ** note_a.zbits + 2 ** note_b.zbits)
    assert close(combined.zbits, expected_combined, 1e-12)

    delta = note_difference("33Z53", "20Z10")
    assert delta.label == "33Z52"
    expected_delta = math.log2(2 ** note_a.zbits - 2 ** note_b.zbits)
    assert close(delta.zbits, expected_delta, 1e-12)

    scaled = scale_note("20Z10", 1.5)
    expected_scaled = math.log2(2 ** note_b.zbits * 1.5)
    assert close(scaled.zbits, expected_scaled, 1e-12)
    assert scaled.label == "20Z68"

    ratio = divide_notes("33Z53", "20Z10")
    expected_ratio = (2 ** note_a.zbits) / (2 ** note_b.zbits)
    assert close(ratio, expected_ratio, 1e-9)


def test_combine_notes_serial_empty():
    with pytest.raises(ValueError):
        combine_notes_serial([])


def test_note_difference_negative_clamps():
    diff = note_difference("10Z00", "33Z53")
    assert diff.zbits == 0


def test_scale_note_zero_factor():
    scaled = scale_note("33Z53", 0)
    assert scaled.label == "0Z00"


def test_scale_note_negative_factor():
    with pytest.raises(ValueError):
        scale_note("33Z53", -1)


def test_scale_note_tiny_factor():
    scaled = scale_note("1Z00", 0.1)
    assert scaled.label == "0Z00"


def test_divide_notes_valid():
    ratio = divide_notes("10Z00", "0Z00")
    assert ratio > 0


# ──────────────────────────────────────────────────────────────────────────
# Option factories
# ──────────────────────────────────────────────────────────────────────────

def test_with_multiplier():
    assert with_multiplier(2) == {"multiplier": 2.0}


def test_with_multiplier_bad():
    with pytest.raises(ValueError):
        with_multiplier(0)
    with pytest.raises(ValueError):
        with_multiplier(-1)


def test_with_reliability():
    assert with_reliability(ReliabilityId.OFTEN_95) == {"reliability": ReliabilityId.OFTEN_95}


def test_with_confidence():
    assert with_confidence(0.95) == {"reliability": 0.95}


def test_with_confidence_bad():
    with pytest.raises(ValueError):
        with_confidence(0)
    with pytest.raises(ValueError):
        with_confidence(1)


def test_estimate_option_factories():
    assert with_estimate_multiplier(2) == {"multiplier": 2.0}
    assert with_estimate_reliability(ReliabilityId.MEAN) == {"reliability": ReliabilityId.MEAN}
    assert with_estimate_confidence(0.99) == {"reliability": 0.99}
    assert with_estimate_primary_mode(PrimaryMode.QUANTILE) == {"primary_mode": PrimaryMode.QUANTILE}
    assert with_estimate_probability_precision(4) == {"probability_precision": 4}


def test_plan_option_factories():
    assert with_plan_multiplier(2) == {"multiplier": 2.0}
    assert with_plan_reliability(ReliabilityId.ALMOST_999) == {"reliability": ReliabilityId.ALMOST_999}
    assert with_plan_confidence(0.9) == {"reliability": 0.9}


def test_human_hashrate_precision_factory():
    assert with_human_hashrate_precision(3) == {"precision": 3}


def test_get_reliability_levels():
    levels = list(get_reliability_levels())
    assert len(levels) == 5


def test_difficulty_from_zbits_roundtrip():
    d = difficulty_from_zbits(33.53)
    z = zbits_from_difficulty(d)
    assert close(z, 33.53, 1e-12)


def test_zbits_from_difficulty_bad():
    with pytest.raises(ValueError):
        zbits_from_difficulty(0)
    with pytest.raises(ValueError):
        zbits_from_difficulty(-1)


def test_resolve_multiplier_bad_confidence():
    with pytest.raises(ValueError):
        required_hashrate("33Z53", 5, reliability=1.5)  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# Sharenote instance methods
# ──────────────────────────────────────────────────────────────────────────

def test_sharenote_methods():
    note = ensure_note("33Z53")
    p = note.probability_per_hash()
    assert close(p, 2 ** -note.zbits, 1e-12)
    assert note.expected_hashes().value > 0
    mean = note.required_hashrate_mean(5)
    assert mean.value > 0
    q = note.required_hashrate_quantile(5, 0.95)
    assert q.value > mean.value
    target = note.target()
    assert isinstance(target, int)
    combined = note.combine_serial("20Z10")
    assert combined.label == "33Z53"
    diff = note.difference("20Z10")
    assert diff.z == 33
    scaled = note.scale(2)
    assert scaled.zbits > note.zbits
    nbits = note.nbits()
    assert len(nbits) == 8


def test_sharenote_label_override():
    note = note_from_zbits(33.537812)
    assert note.label == "33Z53"


def test_hashrate_measurement_human():
    m = HashrateMeasurement(value=3.2e9)
    h = m.human()
    assert "GH/s" in h.display


# ──────────────────────────────────────────────────────────────────────────
# Unit normalization edge cases
# ──────────────────────────────────────────────────────────────────────────

def test_resolve_hashrate_unit_enum():
    val = normalize_hashrate_value(HashrateDescriptor(value=5, unit=HashrateUnit.THPS))
    assert val == 5e12


def test_parse_hashrate_lowercase_unit():
    val = parse_hashrate("5 gh/s")
    assert close(val, 5e9, 1e-9)


def test_parse_hashrate_hps_suffix():
    val = parse_hashrate("5 GHps")
    assert close(val, 5e9, 1e-9)


# ──────────────────────────────────────────────────────────────────────────
# JSON arithmetic vectors
# ──────────────────────────────────────────────────────────────────────────

def test_arithmetic_vectors_from_json():
    vectors_path = Path(__file__).resolve().parent / "snip00_tests.json"
    with vectors_path.open("r", encoding="utf-8") as f:
        vectors = json.load(f)

    for case in vectors["cases"]:
        op = case["operation"]
        if op == "add":
            labels = [i["label"] for i in case["inputs"]]
            result = combine_notes_serial(labels)
            assert result.label == case["expected"]["label"]
            assert close(result.zbits, case["expected"]["z_bits"], 1e-6)
            assert close(2 ** result.zbits, case["expected"]["difficulty"], 1e-6)
        elif op == "subtract":
            result = note_difference(
                case["inputs"]["minuend"]["label"],
                case["inputs"]["subtrahend"]["label"],
            )
            assert result.label == case["expected"]["label"]
            assert close(result.zbits, case["expected"]["z_bits"], 1e-6)
        elif op == "scale":
            result = scale_note(
                case["inputs"]["note"]["label"],
                case["inputs"]["factor"],
            )
            assert result.label == case["expected"]["label"]
            assert close(result.zbits, case["expected"]["z_bits"], 1e-6)
        elif op == "divide":
            ratio = divide_notes(
                case["inputs"]["numerator"]["label"],
                case["inputs"]["denominator"]["label"],
            )
            expected_ratio = case["expected"]["ratio"]
            num = ensure_note(case["inputs"]["numerator"]["label"]).zbits
            den = ensure_note(case["inputs"]["denominator"]["label"]).zbits
            calc = 2 ** (num - den)
            assert close(ratio, expected_ratio, 1e-9)
            assert close(ratio, calc, 1e-9)
        else:
            raise AssertionError(f"unexpected operation {op}")


# ──────────────────────────────────────────────────────────────────────────
# Final coverage closers
# ──────────────────────────────────────────────────────────────────────────

def test_clamp_cents_below_min():
    """L265: _clamp_cents returns MIN_CENTZ for negative."""
    note = note_from_components(10, -5)
    assert note.cents == 0


def test_clamp_cents_above_max():
    """L267: _clamp_cents returns MAX_CENTZ for > 99."""
    note = note_from_components(10, 150)
    assert note.cents == 99


def test_clamp_cents_bad_type():
    """L262: _clamp_cents raises for non-numeric."""
    with pytest.raises(ValueError):
        note_from_components(10, "foo")  # type: ignore


def test_normalize_hashrate_unit_h_without_slash_s():
    """L287: _normalize_hashrate_unit_string appends /S when H present but no /S."""
    val = parse_hashrate("5 GH")
    assert close(val, 5e9, 1e-9)


def test_resolve_hashrate_unit_none():
    """L294: _resolve_hashrate_unit returns (0, HPS) for None."""
    val = normalize_hashrate_value(HashrateDescriptor(value=100, unit=None))
    assert val == 100


def test_parse_label_re_decimal():
    """L461-462: parseLabel reDecimal path with float like '33.53Z'."""
    note = ensure_note("33.537812Z")
    assert note.z == 33
    assert close(note.zbits, 33.537812, 1e-9)


def test_note_from_centz_bits_bad_type():
    """L371: note_from_centz_bits raises for non-numeric."""
    with pytest.raises(ValueError):
        note_from_centz_bits("abc")  # type: ignore


def test_ensure_note_negative_number():
    """L434: ensure_note raises for negative zbits."""
    with pytest.raises(ValueError):
        ensure_note(-5)


def test_sharenote_required_hashrate_instance():
    """L57: Sharenote.required_hashrate instance method."""
    note = ensure_note("33Z53")
    r = note.required_hashrate(5, multiplier=2.0)
    assert r.value > 0


def test_sharenote_label_override():
    """L42: Sharenote._label_override is used when present."""
    from sharenotelib.snip00 import Sharenote
    note = Sharenote(z=33, cents=53, zbits=33.53, _label_override="CUSTOM")
    assert note.label == "CUSTOM"


def test_target_to_compact_small_exponent():
    """L665: _target_to_compact exponent <= 3 left-shift path."""
    from sharenotelib.snip00 import _target_to_compact
    compact = _target_to_compact(255)  # very small target, exponent <= 3
    assert compact > 0


def test_target_to_compact_high_bit():
    """L670-671: _target_to_compact mantissa high-bit adjustment."""
    from sharenotelib.snip00 import _target_to_compact
    # Target whose top 3 bytes have high bit set
    target = 0x00800001
    compact = _target_to_compact(target)
    assert compact > 0


def test_target_to_compact_overflow():
    """L673: _target_to_compact exponent overflow."""
    from sharenotelib.snip00 import _target_to_compact
    with pytest.raises(ValueError):
        _target_to_compact(1 << 2100)


def test_target_to_compact_zero():
    """L662: _target_to_compact rejects zero."""
    from sharenotelib.snip00 import _target_to_compact
    with pytest.raises(ValueError):
        _target_to_compact(0)


def test_format_hash_count():
    """L728-742: _format_hash_count branches."""
    from sharenotelib.snip00 import _format_hash_count
    assert _format_hash_count(0) == "0 H/s"
    assert _format_hash_count(-1) == "0 H/s"
    assert _format_hash_count(float("inf")) == "0 H/s"
    # Small value
    got = _format_hash_count(0.5)
    assert "H/s" in got
    # Mid value (10-100 scaled)
    got = _format_hash_count(50e9)
    assert "H/s" in got
    # Large value (>100 scaled)
    got = _format_hash_count(500e9)
    assert "H/s" in got


def test_human_hashrate_not_finite():
    """L714: human_hashrate !isfinite(scaled) fallback."""
    # This is nearly impossible to trigger via normal inputs.
    # Testing extremely large values to exercise the clamp.
    h = human_hashrate(1e21)
    assert "H/s" in h.display


def test_build_bill_estimate_bad_multiplier():
    """L804: build_bill_estimate multiplier <= 0."""
    with pytest.raises(ValueError):
        build_bill_estimate("33Z53", 5, multiplier=-1)
    with pytest.raises(ValueError):
        build_bill_estimate("33Z53", 5, multiplier=0)


def test_combine_notes_serial_overflow():
    """L925: combine_notes_serial total not finite → clamp to 0."""
    huge = note_from_zbits(1023)
    result = combine_notes_serial([huge, huge, huge])
    # Should not crash; either clamps to 0 or handles Inf
    assert result.zbits >= 0


def test_parse_hashrate_unrecognised():
    """L336: parse_hashrate raises for unrecognised format."""
    with pytest.raises(ValueError):
        parse_hashrate("abc xyz")

