import math

import pytest

from sharenotelib import (
    CENT_ZBIT_STEP,
    HashrateDescriptor,
    HashrateRange,
    HashrateUnit,
    ReliabilityId,
    hashrate_range_for_note,
    build_bill_estimate,
    combine_notes_serial,
    compare_notes,
    divide_notes,
    expected_hashes_for_note,
    format_probability_display,
    human_hashrate,
    max_zbits_for_hashrate,
    nbits_to_sharenote,
    note_difference,
    note_from_hashrate,
    note_from_zbits,
    parse_hashrate,
    plan_sharenote_from_hashrate,
    probability_per_hash,
    required_hashrate_mean,
    required_hashrate_quantile,
    scale_note,
    target_for,
    ensure_note,
)


def test_note_construction():
    note = ensure_note((33, 53))
    assert note.z == 33
    assert note.cents == 53
    assert math.isclose(
        note.zbits,
        33 + 53 * CENT_ZBIT_STEP,
        rel_tol=1e-12,
    )
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
    assert math.isclose(note.zbits, precise, rel_tol=1e-12)


def test_probability_math():
    p = probability_per_hash("33Z53")
    zbits = ensure_note((33, 53)).zbits
    assert math.isclose(p, 2 ** (-zbits), rel_tol=1e-12)
    assert math.isclose(expected_hashes_for_note("33Z53").value, 1 / p, rel_tol=1e-6)
    assert format_probability_display(zbits, 5) == "1 / 2^33.53000"


def test_hashrate_requirements():
    mean = required_hashrate_mean("33Z53", 5)
    expected_zbits = ensure_note((33, 53)).zbits
    expected_mean = 2 ** expected_zbits / 5
    assert math.isclose(mean.value, expected_mean, rel_tol=1e-9)

    q95 = required_hashrate_quantile("33Z53", 5, 0.95)
    assert math.isclose(q95.value, expected_mean * -math.log(1 - 0.95), rel_tol=1e-9)


def test_note_from_hashrate_roundtrip():
    note = note_from_hashrate(parse_hashrate("2.480651469 GH/s"), 5)
    assert note.label == "33Z53"
    with pytest.raises(ValueError):
        note_from_hashrate("1 GH/s", 5)


def test_hashrate_range_captures_original_hashrate():
    seconds = 5
    hashrate = parse_hashrate("1 TH/s")
    note = note_from_hashrate(hashrate, seconds)
    rng = hashrate_range_for_note(note.label, seconds)
    assert isinstance(rng, HashrateRange)
    assert rng.minimum <= hashrate < rng.maximum
    assert note_from_hashrate(rng.minimum, seconds).label == note.label


def test_hashrate_range_handles_1000_mh_note():
    seconds = 5
    hashrate = parse_hashrate("1000 MH/s")
    note = note_from_hashrate(hashrate, seconds)
    rng = hashrate_range_for_note(note.label, seconds)
    assert rng.minimum <= hashrate < rng.maximum
    assert note_from_hashrate(rng.minimum, seconds).label == note.label


def test_parse_hashrate_inputs():
    assert math.isclose(parse_hashrate("5 GH/s"), 5e9, rel_tol=1e-9)
    assert math.isclose(parse_hashrate("12.5 MH/s"), 12.5e6, rel_tol=1e-9)
    descriptor = HashrateDescriptor(value=3.5, unit=HashrateUnit.PHPS)
    assert math.isclose(parse_hashrate(descriptor), 3.5e15, rel_tol=1e-9)
    with pytest.raises(ValueError):
        parse_hashrate("12 foo/s")


def test_max_zbits():
    zbits = max_zbits_for_hashrate(2.480651469003486e9, 5)
    reference = ensure_note((33, 53)).zbits
    assert math.isclose(zbits, reference, rel_tol=1e-6)
    human = human_hashrate(3.2e9)
    assert human.unit == HashrateUnit.GHPS
    assert human.display.startswith("3.20")


def test_target_computation():
    target = target_for("33Z00")
    assert isinstance(target, int)
    approx_bits = math.log(target, 2)
    assert 222 < approx_bits < 224


def test_compare_notes():
    assert compare_notes("32Z00", "33Z00") < 0
    assert compare_notes("33Z54", "33Z53") > 0


def test_compact_conversion():
    converted = nbits_to_sharenote("19752b59")
    value = int("19752b59", 16)
    exponent = value >> 24
    mantissa = value & 0xFFFFFF
    expected_zbits = 256 - (math.log2(mantissa) + 8 * (exponent - 3))
    assert math.isclose(converted.zbits, expected_zbits, rel_tol=1e-12)
    assert converted.label == "57Z12"


def test_bill_estimate():
    estimate = build_bill_estimate("33Z53", 5, reliability=0.95)
    assert estimate.label == "33Z53"
    expected_primary = (2 ** estimate.zbits / 5) * -math.log(1 - 0.95)
    assert math.isclose(
        estimate.required_hashrate_primary, expected_primary, rel_tol=1e-9
    )
    assert estimate.required_hashrate_human.unit == HashrateUnit.GHPS
    assert estimate.probability_display.startswith("1 / 2^")


def test_human_readable_hashrate_display():
    estimate = build_bill_estimate("33Z53", 5)
    display = estimate.required_hashrate_human.display
    assert display.endswith(" GH/s")
    magnitude = float(display.split()[0])
    assert math.isclose(magnitude, 2.48, rel_tol=0.02)


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


def test_arithmetic_helpers():
    note_a = ensure_note("33Z53")
    note_b = ensure_note("20Z10")

    combined = combine_notes_serial([note_a, note_b])
    assert combined.label == "33Z53"
    expected_combined = math.log2(2 ** note_a.zbits + 2 ** note_b.zbits)
    assert math.isclose(combined.zbits, expected_combined, rel_tol=1e-12)

    delta = note_difference("33Z53", "20Z10")
    assert delta.label == "33Z52"
    expected_delta = math.log2(2 ** note_a.zbits - 2 ** note_b.zbits)
    assert math.isclose(delta.zbits, expected_delta, rel_tol=1e-12)

    scaled = scale_note("20Z10", 1.5)
    expected_scaled = math.log2(2 ** note_b.zbits * 1.5)
    assert math.isclose(scaled.zbits, expected_scaled, rel_tol=1e-12)
    assert scaled.label == "20Z68"

    ratio = divide_notes("33Z53", "20Z10")
    expected_ratio = (2 ** note_a.zbits) / (2 ** note_b.zbits)
    assert math.isclose(ratio, expected_ratio, rel_tol=1e-9)


def test_invalid_label():
    with pytest.raises(ValueError):
        ensure_note("XYZ")


def test_scale_note_handles_small_factors():
    scaled = scale_note("1Z00", 0.1)
    assert scaled.label == "0Z00"
