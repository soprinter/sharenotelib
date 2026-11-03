# sharenotelib

The reference Python SDK for **Sharenote** — proof-of-work bearer notes on
Nostr, as specified by **NIP-SN**.

Sharenotelib gives you three things, organised around the protocol's domains
rather than its spec numbering:

1. **Exact Z-unit arithmetic** — density, difficulty, targets, probability, and
   planning. Accounting paths use `fractions.Fraction` (and `int`) exactly and
   never a `float` accumulator; `float` appears only in clearly named display
   helpers (NIP-SN §Z-Arithmetic, A1/A2).
2. **NIP-SN event builders and parsers** — typed, immutable dataclasses that
   serialise to and parse from Nostr events, validating the kind and required
   tags.
3. **Identity** — miner and pool identity events.

Python 3.9+, fully type-hinted (ships `py.typed`), zero runtime dependencies.

```bash
pip install sharenotelib
```

---

## Quick start

```python
import sharenotelib as sn

# A denominated note from continuous Z-bits; the label truncates for display.
note = sn.note_from_zbits(33.537812)
print(note.label, note.zbits)          # "33Z53" 33.537812

# Exact, accounting-safe arithmetic (Fraction under the hood).
total = sn.combine("33Z53", "20Z10")   # linear difficulty sum
print(total.label)                     # "33Z53"
print(sn.difference("33Z53", "20Z10").label)   # "33Z52"
print(sn.scale("20Z10", 1.5).label)           # "20Z68"
print(round(sn.ratio("33Z53", "20Z10"), 4))   # 11036.5375

# The exact difficulty is a Fraction; the float form is a display helper.
print(type(sn.resolve_difficulty(total)).__name__)   # "Fraction"
print(sn.difficulty_float("10Z00"))                  # 1024.0

# Probability & planning.
print(sn.probability_per_hash(note))                       # 8.06e-11
print(sn.required_hashrate_quantile(note, 5, 0.95))        # ~7.43e9 (H/s)
print(sn.note_from_hashrate("2 GH/s", 5).label)            # "33Z21"

# Bitcoin compact-difficulty interop.
print(sn.note_from_nbits("19752b59").label)                # "57Z12"

# Report-ready figures.
est = sn.estimate(note, seconds=5, reliability=0.95)
print(est.probability_display)                 # "1 / 2^33.53000000"
print(est.required_hashrate_human.display)     # "7.43 GH/s"
```

Every arithmetic helper accepts a label string, a `(z, cents)` tuple, a numeric
Z-bit value, a `{"z": ..., "cents": ...}` mapping, or a `Sharenote`. Invalid
input raises a `SharenoteError` (a `ValueError` subclass) — never a silent
`None`.

---

## Z-unit arithmetic (`sharenotelib.arithmetic`)

| Area | Names |
|------|-------|
| Value type & coercion | `Sharenote`, `ensure_note`, `note_from_zbits`, `note_from_label`, `note_from_components`, `note_from_centibits` |
| Labels & components | `format_label`, `format_zbits_label`, `zbits_from_components`, `MIN_CENTS`, `MAX_CENTS` |
| Difficulty (exact) | `resolve_difficulty` → `Fraction` |
| Difficulty (display) | `difficulty_float`, `difficulty_from_zbits`, `zbits_from_difficulty` |
| Exact arithmetic | `combine`, `difference`, `scale`, `ratio`, `compare` |
| Probability | `probability_per_hash`, `probability_from_zbits`, `expected_hashes`, `expected_hashes_from_zbits`, `format_probability_display` |
| Hashrate planning | `required_hashrate`, `required_hashrate_mean`, `required_hashrate_quantile`, `max_zbits_for_hashrate`, `note_from_hashrate`, `hashrate_range` |
| Reliability | `Reliability`, `ReliabilityLevel`, `reliability_levels` |
| Estimates & plans | `estimate`, `estimate_many`, `Estimate`, `plan_from_hashrate`, `Plan`, `PrimaryMode` |
| Targets & interop | `target_for`, `zbits_from_target`, `note_from_nbits`, `note_to_nbits` |
| Hashrate formatting | `parse_hashrate`, `human_hashrate`, `HumanHashrate`, `HashrateUnit` |

`Sharenote` also carries fluent methods: `note.combine(...)`,
`note.difference(...)`, `note.scale(...)`, `note.ratio(...)`,
`note.difficulty()` (exact `Fraction`), `note.probability_per_hash()`,
`note.expected_hashes()`, `note.required_hashrate(...)`, `note.target()`, and
`note.to_nbits()`.

> **Exactness.** `combine`/`difference`/`scale` accumulate in linear difficulty
> space as `Fraction`s, so summing millions of micro-shares loses nothing and
> the result is order-independent. Reserve `resolve_difficulty` for accounting;
> use `difficulty_float` only for display. A discrete label (`33Z53`) is a
> pricing-bucket floor and must never be used to verify a target (NIP-SN A2).
>
> **No sub-unit clamp.** `scale(note, 0)` yields `0Z00`, but a positive factor
> that drives difficulty below one hash produces negative Z-bits and is
> rejected — matching the Go/JS SDKs and the shared conformance vectors.

---

## NIP-SN events

Each event kind is a frozen dataclass. Build one and call `to_tags()` /
`to_event()`; parse a received event with `from_tags()` / `from_event()`
(`from_event` validates the kind). Kind numbers live on `Kind` and on each
class's `KIND` attribute.

| Kind | Class | Module |
|------|-------|--------|
| 10520 Miner Identity | `MinerIdentity` (`ChainAddress`) | `sharenotelib.identity` |
| 10521 Pool Identity | `PoolIdentity` (`PoolChain`, `PayoutScheme`, `PayoutThreshold`, `PoolProfile`) | `sharenotelib.identity` |
| 35500 Unpaid Invoice / 35501 Settled | `Invoice` (`Transaction`) | `sharenotelib.accounting` |
| 35502 Hashrate Telemetry | `Telemetry` (`Worker`) | `sharenotelib.telemetry` |
| 35503/35504/35505 Shares | `Share` (`Transaction`) | `sharenotelib.accounting` |
| 35510 Raw Sharenote / AuxPoW | `RawSharenote` (`AuxBlock`) | `sharenotelib.minting` |
| 35515 Operator Messaging | `OperatorMessage` | `sharenotelib.messaging` |

Block anchors: `height_hash(height)`, `pending_share_id(height, address, worker)`
(kind 35503), and `finalized_share_id(height, address)` (kinds 35504/35505).

```python
import sharenotelib as sn

# Build a pending-share event.
share = sn.Share(
    share_id=sn.pending_share_id(843000, "fc1q…", "rig-01"),
    address="fc1q…",
    height_hash=sn.height_hash(843000),
    block_hash="00…e9",
    workers=["rig-01", "rig-02"],
    height=843000,
    amount=2441406,
    shares="34Z10",
    share_count=128,
    timestamp=1743638400123,
)
share.validate(sn.Kind.PENDING_SHARE)      # NIP-SN A9/A10
event = share.to_event(sn.Kind.PENDING_SHARE)
# {"kind": 35503, "content": "", "tags": [...]}

# Parse one back (validates the kind).
parsed = sn.Share.from_event(event)
assert parsed == share
```

`OperatorMessage.content` is an opaque NIP-44/NIP-04 ciphertext: the SDK carries
it verbatim and performs no encryption.

---

## Migration from 1.x (`snipXX`)

2.0 removes the spec-numbered modules. The arithmetic behaviour and on-the-wire
tag output are unchanged; names and call style changed.

| 1.x (`snipXX`) | 2.0 |
|----------------|-----|
| `sharenotelib.snip00` | `sharenotelib.arithmetic` (all re-exported from the top level) |
| `combine_notes_serial(notes)` | `combine(*notes)` |
| `note_difference(a, b)` | `difference(a, b)` |
| `scale_note(n, f)` | `scale(n, f)` |
| `divide_notes(a, b)` | `ratio(a, b)` |
| `compare_notes(a, b)` | `compare(a, b)` |
| `exact_difficulty_from_note(n)` | `resolve_difficulty(n)` |
| `difficulty_from_note(n)` | `difficulty_float(n)` |
| `continuous_difficulty(target)` | `zbits_from_target(target)` |
| `nbits_to_sharenote(hex)` / `sharenote_to_nbits(n)` | `note_from_nbits(hex)` / `note_to_nbits(n)` |
| `note_from_centz_bits(n)` | `note_from_centibits(n)` |
| `build_bill_estimate` / `estimate_note` | `estimate` |
| `build_bill_estimates` / `estimate_notes` | `estimate_many` |
| `BillEstimate` / `SharenotePlan` | `Estimate` / `Plan` |
| `plan_sharenote_from_hashrate` | `plan_from_hashrate` |
| `hashrate_range_for_note` | `hashrate_range` |
| `expected_hashes_for_note` | `expected_hashes` |
| `expected_hashes_for_zbits` | `expected_hashes_from_zbits` |
| `ReliabilityId` / `get_reliability_levels` | `Reliability` / `reliability_levels` |
| `MAX_CENTZ` / `MIN_CENTZ` | `MAX_CENTS` / `MIN_CENTS` |
| `CENT_ZBIT_STEP` / `CONTINUOUS_EXPONENT_STEP` | internal `_CENTIBIT_STEP` (no longer a public constant) |
| `HashrateValue` / `HashrateParseInput` (type aliases) | removed — `parse_hashrate(...)` accepts a number or a string directly |
| `with_multiplier(...)`, `with_confidence(...)`, `with_estimate_*`, `with_plan_*` | plain keyword args: `multiplier=`, `reliability=`, `primary_mode=`, `probability_precision=` |
| `HashrateMeasurement` / `HashesMeasurement` | plain `float` (+ `human_hashrate(...)`) |
| `HashrateDescriptor` / `normalize_hashrate_value` | `parse_hashrate(...)` (accepts a number or a string like `"5 GH/s"`) |
| `must_note_from_*`, `*_measurement` aliases | removed (use the canonical function) |
| `sharenotelib.snip02` · `Hashrate` · `marshal_tags`/`unmarshal_tags` | `sharenotelib.telemetry` · `Telemetry` · `Telemetry.to_tags()`/`from_tags()`/`to_event()`/`from_event()` |
| `Worker.count_sharenotes` / `count_rejected_sharenotes` | `Worker.accepted` / `rejected` |
| `sharenotelib.snip03` · `marshal_invoice_tags`/`unmarshal_invoice_tags` | `sharenotelib.accounting` · `Invoice.to_tags()`/`from_tags()` |
| `marshal_share_tags`/`unmarshal_share_tags` | `Share.to_tags()`/`from_tags()` |
| `validate_invoice(inv)` / `validate_share(s, kind)` | `inv.validate()` / `s.validate(kind)` |
| `compute_height_hash` / `compute_pending_share_id` / `compute_payment_share_id` | `height_hash` / `pending_share_id` / `finalized_share_id` |
| `sharenotelib.snip04` · `Sharenote` (minting) · `marshal_tags`/`unmarshal_tags` | `sharenotelib.minting` · `RawSharenote` · `RawSharenote.to_tags()`/`from_tags()` |
| `sharenotelib.snip05` · `marshal_miner_tags`/`marshal_pool_tags` (+ `unmarshal_*`) | `sharenotelib.identity` · `MinerIdentity`/`PoolIdentity` `.to_tags()`/`from_tags()` |
| `marshal_pool_content` / `unmarshal_pool_content` | `PoolIdentity.to_content()` / `PoolIdentity.from_content()` |
| `snip05.Identity`, `snip05.marshal_tags`/`unmarshal_tags` (single-chain shims) | removed (use `MinerIdentity` / `ChainAddress`) |
| `KIND_HASHRATE`, `KIND_INVOICE`, `KIND_SHARENOTE`, `KIND_MINER_IDENTITY`, … | `Kind.HASHRATE`, `Kind.INVOICE`, `Kind.RAW_SHARENOTE`, `Kind.MINER_IDENTITY`, … |
| — | **new:** `OperatorMessage` (kind 35515), in `sharenotelib.messaging` |

---

## Testing & development

```bash
hatch run test        # pytest, via the configured hatch env
# or, in any environment with pytest installed:
python3 -m pytest
```

The shared conformance vectors are the cross-SDK contract, held byte-identical
across all three SDKs (the master copy lives in `go-sharenote/testdata`):

- `snip00_tests.json` — Z-arithmetic parity vectors (`test_parity.py`).
- `sdk_edge_tests.json` — decision D1–D4 edge vectors: label-component
  comparison, near-integer clamp, exact `combine` folding, and exact integer
  round-trip (`test_sdk_edge.py`).
- `validation_tests.json` — the NIP-SN validation MUST-set: forged events every
  `validate()` must reject plus valid controls it must accept
  (`test_validation.py`).

Each suite also asserts the bundled copy stays byte-identical to the canonical
copy in `go-sharenote` and matches its pinned sha256.

---

## License

Creative Commons CC0 1.0 Universal.
