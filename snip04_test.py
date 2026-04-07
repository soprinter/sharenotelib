"""Tests for sharenotelib.snip04 (Kind 35510 - AuxPoW Minting)."""

import hashlib
import pytest
from sharenotelib.snip04 import (
    KIND_SHARENOTE,
    AuxBlock, Sharenote,
    marshal_tags, unmarshal_tags,
    validate_header_hash, validate_label,
)


class TestConstants:
    def test_kind_sharenote(self):
        assert KIND_SHARENOTE == 35510


class TestMarshalTags:
    def test_tag_order(self):
        sn = Sharenote(
            header_hash="hh", address="addr", worker="w", agent="a",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=1, sharenote_label="30z00")],
        )
        tags = marshal_tags(sn)
        assert tags[0][0] == "d"
        assert tags[1][0] == "a"
        assert tags[2][0] == "z"
        assert tags[-1][0] == "dd"

    def test_label_lowercased(self):
        sn = Sharenote(
            header_hash="hh", address="addr", worker="w", agent="a",
            label="34Z10", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=1, sharenote_label="34z10")],
        )
        tags = marshal_tags(sn)
        z_tag = [t for t in tags if t[0] == "z"][0]
        assert z_tag[1] == "34z10"

    def test_a_tag_format(self):
        sn = Sharenote(
            header_hash="hh", address="fc1qtest", worker="rig01", agent="bmminer/2.0",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
        )
        tags = marshal_tags(sn)
        a_tag = [t for t in tags if t[0] == "a"][0]
        assert a_tag == ["a", "fc1qtest", "rig01", "bmminer/2.0"]

    def test_primary_chain_first(self):
        sn = Sharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="2a",
            aux_blocks=[
                AuxBlock(block_hash="aa", chain_id="15", height=1, sharenote_label="30z00"),
                AuxBlock(block_hash="bb", chain_id="2a", height=2, sharenote_label="30z00"),
            ],
        )
        tags = marshal_tags(sn)
        w_tags = [t for t in tags if t[0] == "w"]
        assert w_tags[0][2] == "2a"
        assert w_tags[1][2] == "15"

    def test_single_aux_block(self):
        sn = Sharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=843000, solved=True, sharenote_label="40z00")],
        )
        tags = marshal_tags(sn)
        w_tags = [t for t in tags if t[0] == "w"]
        assert len(w_tags) == 1
        assert w_tags[0] == ["w", "bh", "15", "843000", "true", "40z00"]

    def test_solved_false_format(self):
        sn = Sharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(chain_id="15", height=1, solved=False, sharenote_label="30z00")],
        )
        tags = marshal_tags(sn)
        w_tag = [t for t in tags if t[0] == "w"][0]
        assert w_tag[4] == "false"

    def test_empty_aux_blocks_raises(self):
        with pytest.raises(ValueError, match="aux_blocks must not be empty"):
            marshal_tags(Sharenote(label="30z00"))

    def test_missing_primary_chain_raises(self):
        sn = Sharenote(
            label="30z00", primary_chain_id="ff",
            aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
        )
        with pytest.raises(ValueError, match="primary chain ff not found"):
            marshal_tags(sn)

    def test_three_aux_blocks_ordering(self):
        sn = Sharenote(
            header_hash="hh", address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="2a",
            aux_blocks=[
                AuxBlock(chain_id="15", height=1, sharenote_label="30z00"),
                AuxBlock(chain_id="2a", height=2, sharenote_label="30z00"),
                AuxBlock(chain_id="ff", height=3, sharenote_label="30z00"),
            ],
        )
        tags = marshal_tags(sn)
        w_tags = [t for t in tags if t[0] == "w"]
        assert len(w_tags) == 3
        assert w_tags[0][2] == "2a"  # primary first
        assert w_tags[1][2] == "15"  # original order preserved
        assert w_tags[2][2] == "ff"


class TestUnmarshalTags:
    def test_skips_empty_tags(self):
        tags = [[], ["d", "hh"], ["z", "30z00"]]
        sn = unmarshal_tags(tags)
        assert sn.header_hash == "hh"

    def test_skips_short_a_tag(self):
        tags = [["a", "addr"], ["d", "hh"]]
        sn = unmarshal_tags(tags)
        assert sn.address == ""  # needs >= 4 elements

    def test_skips_short_w_tag(self):
        tags = [["w", "bh", "15", "1", "true"]]  # only 5 elements, needs 6
        sn = unmarshal_tags(tags)
        assert len(sn.aux_blocks) == 0

    def test_primary_chain_from_first_w(self):
        tags = [
            ["w", "bh1", "15", "1", "true", "30z00"],
            ["w", "bh2", "2a", "2", "false", "30z00"],
        ]
        sn = unmarshal_tags(tags)
        assert sn.primary_chain_id == "15"

    def test_solved_case_insensitive(self):
        tags = [["w", "bh", "15", "1", "True", "30z00"]]
        sn = unmarshal_tags(tags)
        assert sn.aux_blocks[0].solved is True

        tags2 = [["w", "bh", "15", "1", "FALSE", "30z00"]]
        sn2 = unmarshal_tags(tags2)
        assert sn2.aux_blocks[0].solved is False

    def test_dd_tag_parsed(self):
        tags = [["dd", "0100000081cd02ab"]]
        sn = unmarshal_tags(tags)
        assert sn.header_hex == "0100000081cd02ab"


class TestRoundTrip:
    def test_full_round_trip(self):
        sn = Sharenote(
            header_hash="00" * 32, address="fc1qtest",
            worker="rig01", agent="bmminer/2.0",
            label="34Z10", primary_chain_id="15",
            aux_blocks=[
                AuxBlock(block_hash="ab" * 32, chain_id="15", height=843000, solved=True, sharenote_label="40z00"),
                AuxBlock(block_hash="cd" * 32, chain_id="2a", height=110000, solved=False, sharenote_label="34z10"),
            ],
        )
        parsed = unmarshal_tags(marshal_tags(sn))

        assert parsed.header_hash == "00" * 32
        assert parsed.address == "fc1qtest"
        assert parsed.worker == "rig01"
        assert parsed.agent == "bmminer/2.0"
        assert parsed.label == "34z10"
        assert parsed.primary_chain_id == "15"
        assert len(parsed.aux_blocks) == 2
        assert parsed.aux_blocks[0].height == 843000
        assert parsed.aux_blocks[0].solved is True
        assert parsed.aux_blocks[1].chain_id == "2a"
        assert parsed.aux_blocks[1].solved is False

    def test_single_block_round_trip(self):
        # Use a valid header_hex / header_hash pair for the round-trip.
        header_hex = "00" * 80
        header_bytes = bytes.fromhex(header_hex)
        first = hashlib.sha256(header_bytes).digest()
        second = hashlib.sha256(first).digest()
        header_hash = second[::-1].hex()

        sn = Sharenote(
            header_hash=header_hash, address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(block_hash="bh", chain_id="15", height=1, solved=False, sharenote_label="30z00")],
            header_hex=header_hex,
        )
        parsed = unmarshal_tags(marshal_tags(sn))
        assert parsed.header_hex == header_hex
        assert len(parsed.aux_blocks) == 1


class TestValidateHeaderHash:
    def test_requires_both_fields(self):
        with pytest.raises(ValueError, match="both header_hex and header_hash"):
            validate_header_hash(Sharenote(header_hash="abc"))

        with pytest.raises(ValueError, match="both header_hex and header_hash"):
            validate_header_hash(Sharenote(header_hex="abc"))

    def test_valid_double_sha256(self):
        # Create a known header hex and compute its double-SHA256 reversed.
        header_hex = "00" * 80  # 80-byte mock header
        header_bytes = bytes.fromhex(header_hex)
        first = hashlib.sha256(header_bytes).digest()
        second = hashlib.sha256(first).digest()
        expected_hash = second[::-1].hex()

        sn = Sharenote(header_hash=expected_hash, header_hex=header_hex)
        validate_header_hash(sn)  # should not raise

    def test_invalid_hash_mismatch(self):
        header_hex = "00" * 80
        with pytest.raises(ValueError, match="header hash mismatch"):
            validate_header_hash(Sharenote(header_hash="ff" * 32, header_hex=header_hex))

    def test_invalid_hex_raises(self):
        with pytest.raises(ValueError):
            validate_header_hash(Sharenote(header_hash="abc", header_hex="not_hex"))

    def test_marshal_validates_when_both_present(self):
        """Marshal should reject mismatched header_hash and header_hex."""
        sn = Sharenote(
            header_hash="ff" * 32, header_hex="00" * 80,
            address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
        )
        with pytest.raises(ValueError, match="header hash mismatch"):
            marshal_tags(sn)

    def test_marshal_skips_validation_when_hex_empty(self):
        """Marshal should not validate when header_hex is empty."""
        sn = Sharenote(
            header_hash="ff" * 32,
            address="a", worker="w", agent="ag",
            label="30z00", primary_chain_id="15",
            aux_blocks=[AuxBlock(chain_id="15", height=1, sharenote_label="30z00")],
        )
        marshal_tags(sn)  # should not raise


class TestValidateLabel:
    def test_valid_lowercase(self):
        validate_label("34z10")

    def test_valid_uppercase(self):
        validate_label("30Z00")

    def test_valid_mixed_case(self):
        validate_label("33Z55")

    def test_no_z_raises(self):
        with pytest.raises(ValueError, match="invalid sharenote label"):
            validate_label("abc")

    def test_non_numeric_before_z_raises(self):
        with pytest.raises(ValueError, match="invalid sharenote label"):
            validate_label("abz10")

    def test_non_numeric_after_z_raises(self):
        with pytest.raises(ValueError, match="invalid sharenote label"):
            validate_label("30zxx")

    def test_empty_after_z_raises(self):
        with pytest.raises(ValueError, match="invalid sharenote label"):
            validate_label("30z")

    def test_zero_values_valid(self):
        validate_label("0z0")
