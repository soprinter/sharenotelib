# Sharenotelib

Sharenotelib is the reference Python toolkit for [Sharenote](https://sharenote.xyz) clients.

Designed for Python 3.9+. Ships as a zero-dependency package (aside from optional testing tools).

## Installation

```bash
pip install sharenotelib
```

---

## Quick Start

```python
from sharenotelib import (
    note_from_zbits,
    probability_per_hash,
    required_hashrate_quantile,
    note_from_hashrate,
    nbits_to_sharenote,
    build_bill_estimate,
    human_hashrate,
    combine_notes_serial,
    note_difference,
    scale_note,
    divide_notes,
    parse_hashrate,
    HashrateDescriptor,
    HashrateUnit,
    plan_sharenote_from_hashrate,
    ReliabilityId,
)

# 1. Canonical note representation.
note = note_from_zbits(33.537812)
print(note.label, note.zbits)  # "33Z53", 33.537812

# 1a. Parse rig telemetry and plan against human-readable hashrates.
rig_hashrate = parse_hashrate("5 GH/s")
plan = plan_sharenote_from_hashrate(
    HashrateDescriptor(value=5, unit=HashrateUnit.GHPS),
    seconds=5,
    reliability=ReliabilityId.OFTEN_95,
)
print(plan.sharenote.label)                       # "32Z95"
print(plan.bill.required_hashrate_human.display)  # "5.00 GH/s"

# 2. Probability & planning.
print(probability_per_hash(note))                       # 8.06e-11
print(required_hashrate_quantile(note, 5, 0.95))        # 7431367665.13 (H/s)
print(note_from_hashrate(HashrateDescriptor(2, HashrateUnit.GHPS), 5).label)  # "33Z21"

# 3. Interop with Bitcoin compact difficulty.
print(nbits_to_sharenote("19752b59").label)             # "57Z12"

# 4. Report-ready artefacts.
bill = build_bill_estimate(note, seconds=5, reliability=0.95)
print(bill.probability_display)                         # "1 / 2^33.53000"
print(bill.required_hashrate_human.display)             # "7.43 GH/s"
print(human_hashrate(3.2e9))                            # HumanHashrate(... unit='GH/s')

# 5. Arithmetic helpers.
print(combine_notes_serial(["33Z53", "20Z10"]).label)   # "33Z53"
print(note_difference("33Z53", "20Z10").label)          # "33Z52"
print(scale_note("20Z10", 1.5).label)                   # "20Z68"
print(f"{divide_notes('33Z53', '20Z10'):.4f}")          # 11036.5375
```

All high-level helpers accept canonical strings, `(z, cents)` tuples, dataclass instances (`Sharenote`), or dictionaries with `z`/`cents`.

---

## Core Surface (Cheat Sheet)

| Category | Functions | Notes |
|----------|-----------|-------|
| Labels & Z-bits | `ensure_note`, `note_from_zbits`, `zbits_from_components` | Canonical labelling with cent clamping (`0‒99`) and preserved precision. |
| Probability | `probability_per_hash`, `expected_hashes_for_note` | Floating-point safe; matches paper formulas. |
| Planning | `parse_hashrate`, `note_from_hashrate`, `plan_sharenote_from_hashrate`, `required_hashrate*`, `max_zbits_for_hashrate` | Accept raw reliability (`0‒1`), enum presets (`ReliabilityId.OFTEN_95`), or explicit multipliers; parse human-readable hashrates. |
| Reporting | `build_bill_estimate`, `build_bill_estimates`, `format_probability_display`, `human_hashrate` | Produce `BillEstimate` dataclasses with machine- and human-friendly fields. |
| Arithmetic | `combine_notes_serial`, `note_difference`, `scale_note`, `divide_notes` | Compose sequential difficulty, compute gaps, apply scalars, and compare ratios. |
| Interop | `nbits_to_sharenote`, `target_for`, `compare_notes` | Convert from compact `nBits`, inspect targets (`int`), and sort by rarity. |

Each function raises `SharenoteError` (subclass of `ValueError`) on invalid input.

---

## Common Recipes

```python
from sharenotelib import (
    combine_notes_serial,
    note_difference,
    scale_note,
    divide_notes,
    build_bill_estimates,
)

# Combine sequential proofs (adds Z-bit difficulty).
serial = combine_notes_serial(["33Z53", "20Z10"])
assert serial.label == "33Z53"

# Compare two notes.
gap = note_difference("33Z53", "20Z10")
assert gap.label == "33Z52"

# Scale in-flight Z-bit difficulty (e.g., speed-up factor).
scaled = scale_note("20Z10", 1.5)
assert scaled.label == "20Z68"

# Relative difficulty ratio.
ratio = divide_notes("33Z53", "20Z10")
assert round(ratio, 4) == 11036.5375

# Generate a dashboard table.
rows = build_bill_estimates(["33Z53", "30Z00"], seconds=5, reliability=ReliabilityId.OFTEN_95)
for row in rows:
    print(row.label, row.required_hashrate_human.display)
```

---

## Testing & Development

```bash
hatch env create   # first time
hatch run test     # pytest suite
```

Feel free to plug the functions into notebooks, dashboards, or CLI scripts—the API is pure Python and side-effect free.

---

## License

Creative Commons CC0 1.0 Universal
