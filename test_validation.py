"""Cross-SDK negative/positive validation conformance tests.

Drives ``validation_tests.json`` -- the forged events every SDK ``validate()``
MUST reject, plus genuinely-valid control events it MUST accept (the NIP-SN
validation MUST-set / union; see ``followup/VALIDATION-CONTRACT.md``). The
fixture is byte-identical across the Go / JS / Python SDKs and is the frozen
contract; this module only consumes it.

Each case is dispatched by kind to the matching parser + ``validate()`` and
checked against its ``expect`` (``"reject"`` or ``"accept"``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sharenotelib import (
    Invoice,
    MinerIdentity,
    PoolIdentity,
    Share,
    SharenoteError,
    Telemetry,
    validate_raw_event,
)

_HERE = Path(__file__).resolve().parent
_LOCAL = _HERE / "validation_tests.json"

_CANONICAL = (
    Path("/u/flzpace/xgit/orgs/soprinter/go-sharenote/testdata/validation_tests.json")
)

# Pinned in followup/VALIDATION-CONTRACT.md section 5.
_EXPECTED_SHA256 = "36d915d63756c9fd8eaa05a9400581b8c442a5b819a33e76ec91763b5bb7d445"


def _load() -> dict:
    with _LOCAL.open("r", encoding="utf-8") as handle:
        return json.load(handle)


_FIXTURE = _load()
_CASES = _FIXTURE["cases"]


def test_fixture_sha256_matches_contract() -> None:
    """The bundled fixture must match the sha256 pinned in the contract."""
    digest = hashlib.sha256(_LOCAL.read_bytes()).hexdigest()
    assert digest == _EXPECTED_SHA256


def test_bundled_copy_matches_canonical() -> None:
    """The bundled copy must stay byte-identical to the canonical go-sharenote copy."""
    if not _CANONICAL.is_file():
        pytest.skip("canonical go-sharenote fixture not checked out")
    assert _CANONICAL.read_bytes() == _LOCAL.read_bytes()


def _run(case: dict) -> None:
    """Parse and validate the case's event; raise on any structural failure.

    Parsing and validation are a single unit: a forged event may be rejected at
    either the parse step or the ``validate()`` step, and both count as a
    rejection.
    """
    event = case["event"]
    kind = case["kind"]

    if kind in (35500, 35501):
        Invoice.from_event(event).validate(kind)
    elif kind in (35503, 35504, 35505):
        Share.from_event(event).validate(kind)
    elif kind == 10520:
        MinerIdentity.from_event(event).validate()
    elif kind == 10521:
        PoolIdentity.from_event(event).validate()
    elif kind == 35502:
        Telemetry.from_event(event).validate()
    elif kind == 35510:
        validate_raw_event(event, primary_chain_id=case.get("primary_chain_id", ""))
    else:  # pragma: no cover - guards against new kinds
        raise AssertionError(f"unhandled validation kind {kind}")


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_validation_case(case: dict) -> None:
    if case["expect"] == "reject":
        with pytest.raises(SharenoteError):
            _run(case)
    elif case["expect"] == "accept":
        _run(case)  # must not raise
    else:  # pragma: no cover
        raise AssertionError(f"unexpected expect {case['expect']!r}")


def test_fixture_has_both_reject_and_accept() -> None:
    """Guard: the suite is not satisfiable by rejecting (or accepting) everything."""
    expects = {c["expect"] for c in _CASES}
    assert expects == {"reject", "accept"}
    assert sum(c["expect"] == "reject" for c in _CASES) == 20
    assert sum(c["expect"] == "accept" for c in _CASES) == 8
