"""Tests for raw Sharenote / AuxPoW minting events (kind 35510)."""

from __future__ import annotations

import hashlib

import pytest

from sharenotelib import (
    AuxBlock,
    InvalidEvent,
    InvalidLabel,
    Kind,
    RawSharenote,
    validate_header_hash,
    validate_label,
    validate_raw_event,
)


def _header_pair() -> tuple[str, str]:
    header_hex = "00" * 80
    digest = hashlib.sha256(hashlib.sha256(bytes.fromhex(header_hex)).digest()).digest()
    return header_hex, digest[::-1].hex()


def test_kind() -> None:
    assert RawSharenote.KIND == 35510 == Kind.RAW_SHARENOTE


class TestToTags:
    def test_tag_order_and_lowercase_label(self) -> None:
        tags = RawSharenote(
            header_hash="hh", address="addr", worker="w", agent="a",
            label="34Z10", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=1, sharenote_label="34z10")],
        ).to_tags()
        assert [t[0] for t in tags[:3]] == ["d", "a", "z"]
        assert tags[-1][0] == "dd"
        assert [t for t in tags if t[0] == "z"][0][1] == "34z10"

    def test_a_tag_format(self) -> None:
        tags = RawSharenote(
            header_hash="hh", address="fc1qtest", worker="rig01", agent="bmminer/2.0",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
        ).to_tags()
        assert ["a", "fc1qtest", "rig01", "bmminer/2.0"] in tags

    def test_primary_chain_first(self) -> None:
        tags = RawSharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="2a",
            aux_blocks=[
                AuxBlock(chain_id="15", height=1, sharenote_label="30z00"),
                AuxBlock(chain_id="2a", height=2, sharenote_label="30z00"),
                AuxBlock(chain_id="ff", height=3, sharenote_label="30z00"),
            ],
        ).to_tags()
        w_tags = [t for t in tags if t[0] == "w"]
        assert [t[2] for t in w_tags] == ["2a", "15", "ff"]

    def test_single_block_shape(self) -> None:
        tags = RawSharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=843000, solved=True, sharenote_label="40z00")],
        ).to_tags()
        w_tags = [t for t in tags if t[0] == "w"]
        assert w_tags == [["w", "bh", "15", "843000", "true", "40z00"]]

    def test_empty_aux_blocks_raises(self) -> None:
        with pytest.raises(InvalidEvent):
            RawSharenote(label="30z00").to_tags()

    def test_missing_primary_chain_raises(self) -> None:
        with pytest.raises(InvalidEvent):
            RawSharenote(
                label="30z00", primary_chain_id="ff",
                aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
            ).to_tags()

    def test_marshal_validates_header_when_both_present(self) -> None:
        with pytest.raises(InvalidEvent):
            RawSharenote(
                header_hash="ff" * 32, header_hex="00" * 80,
                address="a", worker="w", agent="ag", label="30z00", primary_chain_id="15",
                aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
            ).to_tags()


class TestFromTags:
    def test_skips_empty_and_short(self) -> None:
        note = RawSharenote.from_tags([[], ["a", "addr"], ["d", "hh"], ["w", "bh", "15", "1", "true"]])
        assert note.header_hash == "hh"
        assert note.address == ""  # 'a' needs 4 elements
        assert note.aux_blocks == []  # 'w' needs 6 elements

    def test_primary_from_first_w_and_solved_case_insensitive(self) -> None:
        note = RawSharenote.from_tags(
            [["w", "bh1", "15", "1", "True", "30z00"], ["w", "bh2", "2a", "2", "FALSE", "30z00"]]
        )
        assert note.primary_chain_id == "15"
        assert note.aux_blocks[0].solved is True
        assert note.aux_blocks[1].solved is False


class TestRoundTrip:
    def test_full(self) -> None:
        note = RawSharenote(
            header_hash="00" * 32, address="fc1qtest", worker="rig01", agent="bmminer/2.0",
            label="34z10", primary_chain_id="15",
            aux_blocks=[
                AuxBlock(block_hash="ab" * 32, chain_id="15", height=843000, solved=True, sharenote_label="40z00"),
                AuxBlock(block_hash="cd" * 32, chain_id="2a", height=110000, solved=False, sharenote_label="34z10"),
            ],
        )
        assert RawSharenote.from_tags(note.to_tags()) == note

    def test_from_event(self) -> None:
        header_hex, header_hash = _header_pair()
        note = RawSharenote(
            header_hash=header_hash, address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15", header_hex=header_hex,
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=1, sharenote_label="30z00")],
        )
        event = note.to_event()
        assert event["kind"] == 35510 and event["content"] == ""
        assert RawSharenote.from_event(event) == note
        with pytest.raises(InvalidEvent):
            RawSharenote.from_event({"kind": 1, "tags": []})


class TestValidateHeaderHash:
    def test_valid(self) -> None:
        header_hex, header_hash = _header_pair()
        validate_header_hash(RawSharenote(header_hash=header_hash, header_hex=header_hex))

    def test_requires_both_fields(self) -> None:
        with pytest.raises(InvalidEvent):
            validate_header_hash(RawSharenote(header_hash="abc"))
        with pytest.raises(InvalidEvent):
            validate_header_hash(RawSharenote(header_hex="abc"))

    def test_mismatch(self) -> None:
        with pytest.raises(InvalidEvent):
            validate_header_hash(RawSharenote(header_hash="ff" * 32, header_hex="00" * 80))

    def test_bad_hex(self) -> None:
        with pytest.raises(ValueError):
            validate_header_hash(RawSharenote(header_hash="abc", header_hex="not_hex"))

    def test_clause2_zbound(self) -> None:
        # A14 clause 2: with a label present, the hash must clear target_for(z).
        header_hex, header_hash = _header_pair()
        # "0z00" -> target 2**256: any hash clears it (clause 2 passes).
        validate_header_hash(
            RawSharenote(header_hash=header_hash, header_hex=header_hex, label="0z00")
        )
        # A very high floor the mock hash cannot clear -> clause 2 rejects,
        # even though clause 1 (the hash match) passes.
        with pytest.raises(InvalidEvent):
            validate_header_hash(
                RawSharenote(header_hash=header_hash, header_hex=header_hex, label="250z00")
            )


class TestParseIntErrors:
    def test_malformed_branch_height_raises_invalid_event(self) -> None:
        with pytest.raises(InvalidEvent):
            AuxBlock.from_tag(["w", "bh", "15", "notanumber", "true", "30z00"])

    def test_from_tags_malformed_height_raises_invalid_event(self) -> None:
        with pytest.raises(InvalidEvent):
            RawSharenote.from_tags([["w", "bh", "15", "notanumber", "true", "30z00"]])


class TestValidateRawEvent:
    def _valid_event(self) -> dict:
        header_hex, header_hash = _header_pair()
        return RawSharenote(
            header_hash=header_hash, header_hex=header_hex,
            address="a", worker="w", agent="ag", label="0z00", primary_chain_id="15",
            aux_blocks=[
                AuxBlock(block_hash="bh1", chain_id="15", height=1, sharenote_label="0z00"),
                AuxBlock(block_hash="bh2", chain_id="2a", height=2, sharenote_label="0z00"),
            ],
        ).to_event()

    def test_accepts_valid(self) -> None:
        note = validate_raw_event(self._valid_event(), primary_chain_id="15")
        assert note.header_hash and len(note.aux_blocks) == 2

    def test_rejects_uppercase_z(self) -> None:
        ev = self._valid_event()
        for tag in ev["tags"]:
            if tag[0] == "z":
                tag[1] = tag[1].upper()
        with pytest.raises(InvalidEvent):
            validate_raw_event(ev, primary_chain_id="15")

    def test_rejects_w_wrong_arity(self) -> None:
        ev = self._valid_event()
        ev["tags"] = [t if t[0] != "w" else t[:-1] for t in ev["tags"]]
        with pytest.raises(InvalidEvent):
            validate_raw_event(ev, primary_chain_id="15")

    def test_rejects_dd_not_last(self) -> None:
        ev = self._valid_event()
        dd = next(t for t in ev["tags"] if t[0] == "dd")
        ev["tags"].remove(dd)
        ev["tags"].insert(0, dd)
        with pytest.raises(InvalidEvent):
            validate_raw_event(ev, primary_chain_id="15")

    def test_rejects_missing_or_misordered_primary(self) -> None:
        with pytest.raises(InvalidEvent):  # declared primary absent
            validate_raw_event(self._valid_event(), primary_chain_id="99")
        with pytest.raises(InvalidEvent):  # declared primary not first
            validate_raw_event(self._valid_event(), primary_chain_id="2a")


class TestValidateLabel:
    @pytest.mark.parametrize("label", ["34z10", "30Z00", "33Z55", "0z0"])
    def test_valid(self, label: str) -> None:
        validate_label(label)

    @pytest.mark.parametrize("label", ["abc", "abz10", "30zxx", "30z"])
    def test_invalid(self, label: str) -> None:
        with pytest.raises(InvalidLabel):
            validate_label(label)
