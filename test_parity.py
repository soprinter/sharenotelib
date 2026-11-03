"""Cross-SDK conformance + exact-aggregation tests.

These load the *canonical* Z-arithmetic vectors shared across the Go / JS /
Python SDKs and assert this SDK produces identical labels, Z-bits, difficulties,
and ratios. They also assert the NIP-SN A1 guarantee: aggregation
(:func:`sharenotelib.combine`) uses exact :class:`fractions.Fraction` arithmetic,
never a ``float64`` accumulator.

The shared JSON fixtures are the contract and must not be modified.
"""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

import json
import pytest

from sharenotelib import (
    PrimaryMode,
    Reliability,
    SharenoteError,
    combine,
    difference,
    estimate,
    human_hashrate,
    note_from_hashrate,
    ratio,
    required_hashrate,
    resolve_difficulty,
    scale,
)

# Prefer the cross-SDK canonical copy in go-sharenote; fall back to the sibling
# copy bundled with this SDK so the suite still runs when the Go repo is absent.
# The Go repo has carried the vectors under both ``testdata/`` and ``snip00/``,
# so probe both known locations.
_GO_SHARENOTE = Path("/u/flzpace/xgit/orgs/soprinter/go-sharenote")
_CANONICAL_CANDIDATES = (
    _GO_SHARENOTE / "testdata" / "snip00_tests.json",
    _GO_SHARENOTE / "snip00" / "snip00_tests.json",
)
_LOCAL = Path(__file__).resolve().parent / "snip00_tests.json"


def _canonical_path() -> Path | None:
    return next((p for p in _CANONICAL_CANDIDATES if p.is_file()), None)


def _vectors_path() -> Path:
    canonical = _canonical_path()
    return canonical if canonical is not None else _LOCAL


def _load_cases() -> list[dict]:
    with _vectors_path().open("r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def _close(a: float, b: float, rel: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=0.0) or a == b


_CASES = _load_cases()


def test_bundled_vectors_match_canonical() -> None:
    """The bundled copy must stay byte-identical to the canonical parity source."""
    canonical = _canonical_path()
    if canonical is None:
        pytest.skip("canonical go-sharenote vectors not checked out")
    assert canonical.read_bytes() == _LOCAL.read_bytes()


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_z_arithmetic_vectors(case: dict) -> None:
    op = case["operation"]
    expected = case["expected"]

    if op == "add":
        result = combine(*(item["label"] for item in case["inputs"]))
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])
        # Exact arithmetic: the combined note carries an exact rational that
        # agrees with the reference float difficulty.
        assert result.exact_difficulty is not None
        assert _close(float(result.exact_difficulty), expected["difficulty"])

    elif op == "subtract":
        result = difference(
            case["inputs"]["minuend"]["label"],
            case["inputs"]["subtrahend"]["label"],
        )
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])

    elif op == "scale":
        result = scale(case["inputs"]["note"]["label"], case["inputs"]["factor"])
        assert result.label == expected["label"]
        assert _close(result.zbits, expected["z_bits"])
        assert _close(2 ** result.zbits, expected["difficulty"])

    elif op == "divide":
        got = ratio(
            case["inputs"]["numerator"]["label"],
            case["inputs"]["denominator"]["label"],
        )
        assert _close(got, expected["ratio"], rel=1e-9)

    else:  # pragma: no cover - guards against new vector kinds
        raise AssertionError(f"unexpected operation {op!r}")


# ---------------------------------------------------------------------------
# Exact-aggregation behaviour (NIP-SN A1)
# ---------------------------------------------------------------------------
def test_combine_stores_exact_rational_difficulty() -> None:
    result = combine("1Z00", "1Z00")
    assert result.exact_difficulty == Fraction(4)
    assert result.label == "2Z00"

    result = combine("0Z00", "15Z00")
    assert result.exact_difficulty == Fraction(32769)
    assert result.label == "15Z00"


def test_combine_accepts_an_iterable() -> None:
    labels = ["1Z00", "1Z00", "1Z00", "1Z00"]
    assert combine(labels).exact_difficulty == Fraction(8)
    assert combine(*labels).exact_difficulty == Fraction(8)


def test_combine_is_order_independent() -> None:
    notes = ["60Z99", "1Z00", "33Z53", "34Z76", "35Z14", "33Z53", "0Z00"]
    forward = combine(*notes)
    backward = combine(*reversed(notes))
    assert forward.exact_difficulty == backward.exact_difficulty
    assert forward.label == backward.label
    assert forward.zbits == backward.zbits


def test_combine_preserves_tiny_note_that_float_would_drop() -> None:
    huge = resolve_difficulty("60Z99")
    # A float accumulator would lose the small note entirely.
    assert float(huge) + 2.0 == float(huge)
    combined = combine("60Z99", "1Z00")
    assert combined.exact_difficulty == huge + Fraction(2)
    assert combined.exact_difficulty > huge


def test_combine_reaggregation_uses_stored_exact_difficulty() -> None:
    a, b, c = "33Z53", "34Z76", "60Z99"
    flat = combine(a, b, c)
    nested = combine(combine(a, b), c)
    assert nested.exact_difficulty == flat.exact_difficulty
    assert nested.label == flat.label


def test_combine_matches_exact_reference_sum() -> None:
    labels = ["42Z76", "34Z76", "33Z53", "35Z14", "1Z00", "60Z99"]
    expected = sum((resolve_difficulty(x) for x in labels), Fraction(0))
    result = combine(*labels)
    assert result.exact_difficulty == expected
    assert _close(
        result.zbits,
        math.log2(expected.numerator) - math.log2(expected.denominator),
        rel=1e-12,
    )


def test_scale_rejects_sub_unit_difficulty() -> None:
    """No sub-unit clamp: difficulty < 1 is rejected, matching Go/JS and vectors."""
    with pytest.raises(SharenoteError):
        scale("1Z00", 0.1)  # difficulty 2 * 0.1 = 0.2 < 1
    assert scale("33Z53", 0).label == "0Z00"  # only factor 0 -> 0Z00


# ---------------------------------------------------------------------------
# Options are now plain keyword arguments (no functional-option helpers).
# ---------------------------------------------------------------------------
def test_required_hashrate_multiplier_and_confidence() -> None:
    assert required_hashrate("33Z53", 5, multiplier=2.0) == (
        required_hashrate("33Z53", 5) * 2
    )
    assert required_hashrate("33Z53", 5, reliability=0.95) > 0


def test_note_from_hashrate_matches_confidence_and_preset() -> None:
    by_float = note_from_hashrate(5e9, 5, reliability=0.95)
    by_string = note_from_hashrate("5 GH/s", 5, reliability=0.95)
    assert by_float.label == by_string.label


def test_estimate_keyword_options() -> None:
    est = estimate(
        "33Z53",
        5,
        reliability=0.99,
        primary_mode=PrimaryMode.QUANTILE,
        probability_precision=3,
    )
    assert math.isclose(est.quantile, 0.99, rel_tol=1e-9)
    assert est.primary_mode is PrimaryMode.QUANTILE
    assert len(est.probability_display.split("^")[1].split(".")[1]) == 3


def test_human_hashrate_precision() -> None:
    assert human_hashrate(3.2e9, precision=4).display == "3.2000 GH/s"


def test_reliability_preset_option() -> None:
    assert required_hashrate("33Z53", 5, reliability=Reliability.OFTEN_95) > 0
