"""Cross-SDK edge-case conformance tests (decisions D1-D4).

Drives ``sdk_edge_tests.json`` -- the positive edge vectors shared byte-identical
across the Go / JS / Python SDKs (see ``followup/VALIDATION-CONTRACT.md``). The
fixture is the frozen contract and must not be modified; this module only
consumes it.

Coverage:

* **D1** note comparison orders by label components ``(z, cents)`` -- two notes
  with the same label are EQUAL even when their continuous Z-bits differ.
* **D2** near-integer label carry clamps raw cents to ``99`` (never ``(z+1)Z00``).
* **D3** ``combine`` folds a previously-combined note using its stored *exact*
  difficulty, never a value re-derived from its display Z-bits.
* **D4** ``amount`` / ``fee`` / ``threshold`` integers round-trip exactly, with no
  ``float64`` precision loss above 2**53.
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from sharenotelib import (
    Invoice,
    PoolIdentity,
    Share,
    combine,
    compare,
    note_from_label,
    note_from_zbits,
)

_HERE = Path(__file__).resolve().parent
_LOCAL = _HERE / "sdk_edge_tests.json"

# The canonical master lives in go-sharenote/testdata; the sibling copy bundled
# here must stay byte-identical (same guard pattern as test_parity.py).
_CANONICAL = (
    Path("/u/flzpace/xgit/orgs/soprinter/go-sharenote/testdata/sdk_edge_tests.json")
)

# Pinned in followup/VALIDATION-CONTRACT.md section 5.
_EXPECTED_SHA256 = "dde47c42dd2292171d2f0ef6529fcf59370595456a52f1a5cc5e695605b48cea"


def _load() -> dict:
    with _LOCAL.open("r", encoding="utf-8") as handle:
        return json.load(handle)


_FIXTURE = _load()
_CASES = _FIXTURE["cases"]


def _close(a: float, b: float, rel: float = 1e-9) -> bool:
    import math

    return math.isclose(a, b, rel_tol=rel, abs_tol=0.0) or a == b


def test_fixture_sha256_matches_contract() -> None:
    """The bundled fixture must match the sha256 pinned in the contract."""
    digest = hashlib.sha256(_LOCAL.read_bytes()).hexdigest()
    assert digest == _EXPECTED_SHA256


def test_bundled_copy_matches_canonical() -> None:
    """The bundled copy must stay byte-identical to the canonical go-sharenote copy."""
    if not _CANONICAL.is_file():
        pytest.skip("canonical go-sharenote fixture not checked out")
    assert _CANONICAL.read_bytes() == _LOCAL.read_bytes()


def _operand(spec: dict):
    if "label" in spec:
        return note_from_label(spec["label"])
    return note_from_zbits(spec["z_bits"])


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _replay_combine(inputs: dict):
    results = []
    for step in inputs["steps"]:
        tokens = []
        for token in step["combine"]:
            if isinstance(token, str) and token.startswith("$"):
                tokens.append(results[int(token[1:])])
            else:
                tokens.append(note_from_label(token))
        results.append(combine(*tokens))
    return results


def _roundtrip_integer(context: dict, wire: str) -> int:
    """Parse ``wire`` into the tag's integer via the real event parser (D4)."""
    kind, tag = int(context["kind"]), context["tag"]
    if tag == "amount" and kind in (35500, 35501):
        return Invoice.from_tags([["amount", wire]]).amount
    if tag == "amount" and kind in (35503, 35504, 35505):
        return Share.from_tags([["amount", wire]]).amount
    if tag == "threshold" and kind == 10521:
        pool = PoolIdentity.from_tags(
            [["a", "15", "addr", "0"], ["payout", "pps"], ["threshold", "15", wire]]
        )
        return pool.thresholds[0].amount
    if tag == "fee" and kind in (35503, 35504, 35505):
        return Share.from_tags([["fee", wire]]).fee
    raise AssertionError(f"unhandled D4 context: kind={kind} tag={tag!r}")


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_edge_case(case: dict) -> None:
    op = case["operation"]
    expected = case["expected"]

    if op == "compare":
        got = compare(_operand(case["inputs"]["a"]), _operand(case["inputs"]["b"]))
        assert _sign(got) == expected["cmp"]

    elif op == "label_from_zbits":
        note = note_from_zbits(case["inputs"]["z_bits"])
        assert note.label == expected["label"]
        assert note.z == expected["z"]
        assert note.cents == expected["cents"]

    elif op == "combine":
        results = _replay_combine(case["inputs"])
        result = results[case["inputs"]["result_step"]]
        exact = result.exact_difficulty
        assert exact is not None
        assert result.label == expected["label"]
        # D3 discriminator: the EXACT difficulty, carried through the fold.
        assert exact == Fraction(int(expected["exact_difficulty_decimal"]))
        dyadic = expected["exact_dyadic"]
        assert exact == Fraction(int(dyadic["sig"])) * (Fraction(2) ** int(dyadic["exp"]))
        assert _close(float(exact), expected["difficulty"])
        assert results[0].exact_difficulty == Fraction(
            int(expected["intermediate_step0_decimal"])
        )

    elif op == "integer_roundtrip":
        wire = case["inputs"]["wire"]
        got = _roundtrip_integer(case["context"], wire)
        assert got == int(expected["value"])
        assert str(got) == expected["value"]
        # A float64/number parser would lose precision; Python int does not.
        assert got != int(expected["float64_would_give"])

    else:  # pragma: no cover - guards against new vector kinds
        raise AssertionError(f"unexpected operation {op!r}")
