"""SNIP-00 cross-SDK parity + exact-aggregation tests.

These tests load the *canonical* SNIP-00 arithmetic vectors that are shared
across the Go / JS / Python SDKs and assert that this SDK produces identical
labels, Z-bits and difficulties. They also assert the behaviour mandated by
critique #1: serial aggregation (``combine_notes_serial``) uses EXACT
arithmetic (rationals), not a ``float64`` accumulator.
"""
from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path

import pytest

from sharenotelib import (
    PrimaryMode,
    ReliabilityId,
    SharenoteError,
    build_bill_estimate,
    combine_notes_serial,
    divide_notes,
    ensure_note,
    exact_difficulty_from_note,
    human_hashrate,
    note_difference,
    note_from_hashrate,
    required_hashrate,
    scale_note,
    with_confidence,
    with_estimate_confidence,
    with_estimate_primary_mode,
    with_estimate_probability_precision,
    with_human_hashrate_precision,
    with_multiplier,
)

# ---------------------------------------------------------------------------
# Canonical vector source (shared parity file). Prefer the cross-SDK canonical
# copy in go-sharenote; fall back to the sibling copy bundled with this SDK so
# the suite still runs when the Go repo is not checked out alongside.
# ---------------------------------------------------------------------------
_CANONICAL = Path(
    "/u/flzpace/xgit/orgs/soprinter/go-sharenote/snip00/snip00_tests.json"
)
_LOCAL = Path(__file__).resolve().parent / "snip00_tests.json"


def _vectors_path() -> Path:
    if _CANONICAL.is_file():
        return _CANONICAL
    return _LOCAL


def _load_cases() -> list[dict]:
    with _vectors_path().open("r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def _close(a: float, b: float, rel: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=0.0) or (a == b)


_CASES = _load_cases()


def test_canonical_and_local_vectors_match():
    """The bundled copy must stay byte-identical to the canonical parity source."""
    if not _CANONICAL.is_file():
        pytest.skip("canonical go-sharenote vectors not checked out")
    assert _CANONICAL.read_bytes() == _LOCAL.read_bytes()


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_snip00_parity(case: dict):
    op = case["operation"]
    expected = case["expected"]

    if op == "add":
        labels = [i["label"] for i in case["inputs"]]
        result = combine_notes_serial(labels)
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])
        # Exact arithmetic: the combined note carries an exact rational
        # difficulty, and it agrees with the reference float difficulty.
        assert result.exact_difficulty is not None
        assert _close(float(result.exact_difficulty), expected["difficulty"])

    elif op == "subtract":
        result = note_difference(
            case["inputs"]["minuend"]["label"],
            case["inputs"]["subtrahend"]["label"],
        )
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])

    elif op == "scale":
        result = scale_note(
            case["inputs"]["note"]["label"],
            case["inputs"]["factor"],
        )
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])

    elif op == "divide":
        ratio = divide_notes(
            case["inputs"]["numerator"]["label"],
            case["inputs"]["denominator"]["label"],
        )
        assert _close(ratio, expected["ratio"], rel=1e-9)

    else:  # pragma: no cover - guards against new vector kinds
        raise AssertionError(f"unexpected operation {op!r}")


# ---------------------------------------------------------------------------
# Exact-aggregation behaviour (the core of critique #1)
# ---------------------------------------------------------------------------

def test_combine_stores_exact_rational_difficulty():
    """combine_notes_serial returns a note carrying an exact Fraction total."""
    result = combine_notes_serial(["1Z00", "1Z00"])
    assert result.exact_difficulty == Fraction(4)
    assert result.label == "2Z00"

    result = combine_notes_serial(["0Z00", "15Z00"])
    assert result.exact_difficulty == Fraction(32769)
    assert result.label == "15Z00"


def test_combine_is_order_independent():
    """Exact arithmetic is associative/commutative; float accumulation is not.

    Summing the same multiset in two different orders must yield a bit-for-bit
    identical exact difficulty (and label). A float64 accumulator cannot
    guarantee this across widely differing magnitudes.
    """
    notes = ["60Z99", "1Z00", "33Z53", "34Z76", "35Z14", "33Z53", "0Z00"]
    forward = combine_notes_serial(notes)
    backward = combine_notes_serial(list(reversed(notes)))
    assert forward.exact_difficulty == backward.exact_difficulty
    assert forward.label == backward.label
    assert forward.zbits == backward.zbits


def test_combine_preserves_tiny_note_that_float_would_drop():
    """A tiny note added to a huge one survives in the exact difficulty.

    At ~2.29e18 the float64 ULP exceeds 2, so ``huge + 2.0 == huge`` in float.
    Exact aggregation must still account for the 1Z00 (difficulty 2) note.
    """
    huge = exact_difficulty_from_note("60Z99")
    # Demonstrate the float accumulator would lose the small note entirely.
    assert float(huge) + 2.0 == float(huge)
    # Exact aggregation keeps it.
    combined = combine_notes_serial(["60Z99", "1Z00"])
    assert combined.exact_difficulty == huge + Fraction(2)
    assert combined.exact_difficulty > huge


def test_combine_reaggregation_uses_stored_exact_difficulty():
    """Re-combining combined notes must not re-derive from rounded Z-bits.

    combine([a, b, c]) and combine([combine([a, b]), c]) must produce the same
    exact difficulty, which is only possible if the intermediate note's stored
    exact difficulty is reused instead of ``2 ** round(zbits)``.
    """
    a, b, c = "33Z53", "34Z76", "60Z99"
    flat = combine_notes_serial([a, b, c])
    nested = combine_notes_serial([combine_notes_serial([a, b]), c])
    assert nested.exact_difficulty == flat.exact_difficulty
    assert nested.label == flat.label


def test_combine_matches_exact_reference_sum():
    """Combined difficulty equals the exact rational sum of input difficulties."""
    labels = ["42Z76", "34Z76", "33Z53", "35Z14", "1Z00", "60Z99"]
    expected = sum((exact_difficulty_from_note(x) for x in labels), Fraction(0))
    result = combine_notes_serial(labels)
    assert result.exact_difficulty == expected
    assert _close(result.zbits, math.log2(expected.numerator) - math.log2(expected.denominator), rel=1e-12)


def test_scale_no_longer_clamps_subunit_to_zero():
    """SNIP-00 reconciliation: sub-unit scaled difficulty is rejected, not 0Z00."""
    with pytest.raises(SharenoteError):
        scale_note("1Z00", 0.1)  # difficulty 2 * 0.1 = 0.2 < 1
    # factor == 0 remains the only path to 0Z00
    assert scale_note("33Z53", 0).label == "0Z00"


# ---------------------------------------------------------------------------
# with_* helpers are wired into the actual call path (no longer vestigial).
# Passed positionally, they mirror Go's functional-option call sites and are
# equivalent to the matching keyword arguments.
# ---------------------------------------------------------------------------

def test_with_multiplier_option_is_applied():
    opt = required_hashrate("33Z53", 5, with_multiplier(2.0))
    kw = required_hashrate("33Z53", 5, multiplier=2.0)
    assert opt.value == kw.value


def test_with_confidence_option_is_applied():
    opt = required_hashrate("33Z53", 5, with_confidence(0.95))
    kw = required_hashrate("33Z53", 5, reliability=0.95)
    assert opt.value == kw.value


def test_note_from_hashrate_option_is_applied():
    opt = note_from_hashrate(5e9, 5, with_confidence(0.95))
    kw = note_from_hashrate(5e9, 5, reliability=0.95)
    assert opt.label == kw.label


def test_estimate_options_are_applied():
    est = build_bill_estimate(
        "33Z53",
        5,
        with_estimate_confidence(0.99),
        with_estimate_primary_mode(PrimaryMode.QUANTILE),
        with_estimate_probability_precision(3),
    )
    assert math.isclose(est.quantile, 0.99, rel_tol=1e-9)
    assert est.primary_mode == PrimaryMode.QUANTILE
    assert len(est.probability_display.split("^")[1].split(".")[1]) == 3


def test_explicit_kwarg_overrides_positional_option():
    # Explicit keyword wins over a positional option mapping.
    est = build_bill_estimate("33Z53", 5, with_estimate_confidence(0.90), reliability=0.99)
    assert math.isclose(est.quantile, 0.99, rel_tol=1e-9)


def test_with_human_hashrate_precision_option_is_applied():
    got = human_hashrate(3.2e9, with_human_hashrate_precision(4))
    assert got.display == "3.2000 GH/s"


def test_bad_positional_option_rejected():
    with pytest.raises(SharenoteError):
        required_hashrate("33Z53", 5, "not-a-mapping")  # type: ignore[arg-type]
