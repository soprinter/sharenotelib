# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-02

A ground-up redesign of the public API around the NIP-SN protocol domains
(replacing the former SNIP-00..05 numbering). This is the baseline release of
the redesigned SDK; it is a breaking change from 1.x. See the migration table in
`README.md`.

### Added

- `sharenotelib.arithmetic` — the exact Z-unit domain: the `Sharenote` value
  type, construction/coercion helpers, exact `combine` / `difference` / `scale`
  / `ratio`, `compare`, probability and hashrate planning (`estimate`,
  `estimate_many`, `plan_from_hashrate`), target/`nBits` interop, and hashrate
  formatting. Accounting is computed in exact `fractions.Fraction` space;
  `float` is exposed only through display helpers (`difficulty_float`,
  `difficulty_from_zbits`, `probability_*`, `human_hashrate`).
- NIP-SN event builders and parsers as typed, immutable dataclasses, each with
  `to_tags()` / `from_tags()` and `to_event()` / `from_event()` (the latter
  validating the event kind): `Telemetry` (35502, `sharenotelib.telemetry`),
  `Invoice` and `Share` (35500/35501/35503/35504/35505,
  `sharenotelib.accounting`), `RawSharenote` (35510, `sharenotelib.minting`),
  `MinerIdentity` and `PoolIdentity` (10520/10521, `sharenotelib.identity`).
- `OperatorMessage` (kind 35515) in `sharenotelib.messaging`, covering the
  optional operator↔miner direct-message kind (ciphertext carried verbatim).
- `Kind`, an `IntEnum` of every NIP-SN event kind, as the single source of truth
  for kind numbers.
- A precise exception hierarchy — `SharenoteError` (a `ValueError`) with
  `InvalidLabel` and `InvalidEvent` subclasses — raised across all modules
  instead of bare `ValueError` or silent `None`.
- A curated, flat public API re-exported from the top-level `sharenotelib`
  package with an explicit `__all__`, and a `py.typed` marker (PEP 561) so type
  checkers consume the shipped annotations.
- The full NIP-SN validation MUST-set (union) across every `validate()`: block
  anchors and 32-byte-hex block hashes (A7/A9), coordinate equality (A7/A10),
  required `chain` + confirmed full-form settlement on Share Payment (A13/D5),
  `MinerIdentity.validate()`/`PoolIdentity.validate()` (hex chain IDs, no
  duplicates, `pplns` `n:` — A5/A6/A16), `Telemetry.validate()` (exactly one of
  `all`/`h` — A15), and `validate_raw_event()` enforcing both clauses of A14
  (header hash match **and** the `z` leading-zero bound) plus the `w`/`z`/`dd`
  structure. Telemetry worker tags are sorted by name on build (D6). The shared
  `sdk_edge_tests.json` (D1–D4) and `validation_tests.json` fixtures are wired
  into the pytest suite, byte-identical to the canonical go-sharenote copies.

### Changed

- Reorganised the package from spec-numbered modules (`snip00`–`snip05`) into
  domain modules; names moved to idiomatic Python (`combine`, `difference`,
  `scale`, `ratio`, `resolve_difficulty`, `zbits_from_target`,
  `note_from_nbits`, `estimate`, `plan_from_hashrate`, `Reliability`,
  `MinerIdentity.to_tags()`, …). On-the-wire tag output and the Z-arithmetic
  results are unchanged and remain conformant with the shared cross-SDK vectors.
- Hashrate inputs now accept a plain number (H/s) or a human string such as
  `"5 GH/s"` via `parse_hashrate`; hashrate and expected-hash results are plain
  `float`s.
- Scaling keeps the no-sub-unit-clamp behaviour: `scale(note, 0)` yields `0Z00`,
  while a positive factor that drives difficulty below one hash is rejected,
  matching the Go/JS SDKs and the conformance vectors.

### Removed

- The `snip00`–`snip05` modules and their generic `marshal_tags` /
  `unmarshal_tags` functions.
- The Go-style functional options (`with_multiplier`, `with_confidence`,
  `with_estimate_*`, `with_plan_*`) — use keyword arguments instead.
- Redundant aliases and wrappers: `estimate_note`/`estimate_notes`,
  `must_note_from_*`, the `*_measurement` helpers, `HashrateMeasurement`,
  `HashesMeasurement`, `HashrateDescriptor`, `normalize_hashrate_value`, and the
  single-chain `Identity` compatibility shims.
