"""Tests for pool accounting events (kinds 35500/35501/35503/35504/35505)."""

from __future__ import annotations

import hashlib

import pytest

from sharenotelib import (
    InvalidEvent,
    Invoice,
    Kind,
    Share,
    SharenoteError,
    Transaction,
    finalized_share_id,
    height_hash,
    pending_share_id,
)


def test_kind_values() -> None:
    assert Kind.INVOICE == 35500
    assert Kind.SETTLED_INVOICE == 35501
    assert Kind.PENDING_SHARE == 35503
    assert Kind.FINALIZED_SHARE == 35504
    assert Kind.SHARE_PAYMENT == 35505


class TestHashHelpers:
    def test_height_hash_is_blake2b_256(self) -> None:
        h = height_hash(100)
        assert h == hashlib.blake2b(b"100", digest_size=32).hexdigest()
        assert len(h) == 64
        assert height_hash(1) != height_hash(2)

    def test_pending_id_depends_on_all_parts(self) -> None:
        base = pending_share_id(100, "addr1", "rig01")
        assert base == pending_share_id(100, "addr1", "rig01")
        assert base != pending_share_id(100, "addr1", "rig02")
        assert base != pending_share_id(100, "addr2", "rig01")
        assert base != pending_share_id(101, "addr1", "rig01")

    def test_finalized_id_depends_on_height_and_address(self) -> None:
        assert len(finalized_share_id(100, "addr1")) == 64
        assert finalized_share_id(100, "a") != finalized_share_id(100, "b")
        assert finalized_share_id(1, "a") != finalized_share_id(2, "a")

    def test_cross_sdk_golden_values(self) -> None:
        """Pin the exact blake2b-256 anchors shared with the Go/JS SDKs.

        These literal digests are the cross-SDK contract (see the
        validation_tests.json ``anchors``); a change to the hashing primitive
        (e.g. truncating blake2b-512 instead of true blake2b-256) would break
        them.
        """
        addr = "fc1q0vw9cmzqqc3vxfhd7m4zcqf8n82s9gsmagr02a"
        assert height_hash(843000) == (
            "9d83d89f11bc0b930935e9a58e93ac1e43cdcaf25e8e4d68dc4c96763208f479"
        )
        assert pending_share_id(843000, addr, "rig-01") == (
            "bb36d07ab1d2599fa24f174d52e36d6b1593eeddcbde3aad94878fd1a929b763"
        )
        assert finalized_share_id(843000, addr) == (
            "4c5a68c2ebcd6e180beefb309b1861708547a6622355da508cc4cad946a43bf0"
        )


class TestInvoice:
    def test_to_tags_full(self) -> None:
        tags = Invoice(
            height_hash="aabb", block_hash="ccdd", height=100,
            amount=5000, workers=3, shares="34z10",
        ).to_tags()
        for tag in (["d", "aabb"], ["b", "ccdd"], ["height", "100"],
                    ["amount", "5000"], ["workers", "3"], ["shares", "34z10"]):
            assert tag in tags

    def test_optional_fields_omitted(self) -> None:
        tags = Invoice(height_hash="a", block_hash="b", height=1, amount=1, workers=1).to_tags()
        assert not any(t[0] in ("shares", "x") for t in tags)

    def test_tx_short_and_full_form(self) -> None:
        short = Invoice(height_hash="a", block_hash="b", height=1, amount=1, workers=1,
                        tx=Transaction(txid="t"))
        assert ["x", "t"] in short.to_tags()
        full = Invoice(height_hash="a", block_hash="b", height=1, amount=1, workers=1,
                       tx=Transaction(txid="t", confirmed=True, block_height=50, block_hash="bh"))
        assert ["x", "t", "50", "bh"] in full.to_tags()

    def test_round_trip(self) -> None:
        inv = Invoice(
            height_hash=height_hash(843000), block_hash="00" * 32,
            height=843000, amount=625000000, workers=5, shares="34z10",
            tx=Transaction(txid="ff" * 32, confirmed=True, block_height=843006, block_hash="cd" * 32),
        )
        assert Invoice.from_tags(inv.to_tags()) == inv

    def test_from_tags_skips_short_and_unknown(self) -> None:
        inv = Invoice.from_tags([["d"], ["d", "hash"], ["unknown", "v"]])
        assert inv.height_hash == "hash"

    def test_from_event_accepts_both_kinds(self) -> None:
        inv = Invoice(height_hash=height_hash(1), block_hash="b", height=1, amount=1, workers=1)
        assert Invoice.from_event(inv.to_event(Kind.INVOICE)) == inv
        assert Invoice.from_event(inv.to_event(Kind.SETTLED_INVOICE)) == inv
        with pytest.raises(InvalidEvent):
            Invoice.from_event({"kind": 1, "tags": []})

    def test_validate(self) -> None:
        Invoice(height_hash=height_hash(100), block_hash="00" * 32, height=100, amount=5000).validate()
        with pytest.raises(InvalidEvent):
            Invoice(height=0, amount=5000).validate()
        with pytest.raises(InvalidEvent):
            Invoice(height_hash="wrong", block_hash="00" * 32, height=100, amount=5000).validate()
        with pytest.raises(InvalidEvent):
            # block hash must be a 32-byte (64 hex char) key (NIP-SN A7).
            Invoice(height_hash=height_hash(100), block_hash="deadbeef", height=100, amount=5000).validate()
        with pytest.raises(InvalidEvent):
            Invoice(height_hash=height_hash(100), block_hash="00" * 32, height=100, amount=0).validate()

    def test_validate_settled_requires_confirmed_tx(self) -> None:
        unpaid = Invoice(height_hash=height_hash(100), block_hash="00" * 32, height=100, amount=5000)
        with pytest.raises(InvalidEvent):
            unpaid.validate(Kind.SETTLED_INVOICE)
        settled = Invoice(
            height_hash=height_hash(100), block_hash="00" * 32, height=100, amount=5000,
            tx=Transaction(txid="t", confirmed=True, block_height=101, block_hash="h"),
        )
        settled.validate(Kind.SETTLED_INVOICE)

    def test_unconfirmed_tx_when_block_hash_empty(self) -> None:
        inv = Invoice.from_tags([["d", "h"], ["x", "txid", "50", ""]])
        assert inv.tx is not None and inv.tx.confirmed is False


class TestShare:
    def test_to_tags_full(self) -> None:
        tags = Share(
            share_id="sid", address="addr", height_hash="hh", block_hash="bh",
            chain_id="15", workers=["rig01", "rig02"], height=100, amount=1000,
            shares="33z53", share_count=5, total_shares="34z10", total_share_count=20,
            timestamp=1700000000, fee=100, est_payment_height=200,
            sharenote_event_ids=["ev1", "ev2"],
        ).to_tags()
        for tag in (
            ["d", "sid"], ["a", "addr"], ["h", "hh"], ["b", "bh"], ["chain", "15"],
            ["workers", "rig01", "rig02"], ["height", "100"], ["amount", "1000"],
            ["shares", "33z53", "5"], ["totalshares", "34z10", "20"],
            ["timestamp", "1700000000"], ["fee", "100"], ["eph", "200"],
            ["sn", "ev1"], ["sn", "ev2"],
        ):
            assert tag in tags

    def test_optional_fields_omitted(self) -> None:
        tags = Share(share_id="s", address="a", height_hash="h", block_hash="b",
                     workers=["w"], height=1, amount=1, timestamp=0).to_tags()
        assert not any(t[0] in ("chain", "fee", "eph") for t in tags)

    def test_shares_without_count(self) -> None:
        tags = Share(share_id="s", address="a", height_hash="h", block_hash="b",
                     workers=["w"], height=1, amount=1, shares="33z53", timestamp=0).to_tags()
        assert ["shares", "33z53"] in tags

    def test_whitespace_event_ids_skipped(self) -> None:
        tags = Share(share_id="s", address="a", height_hash="h", block_hash="b",
                     workers=["w"], height=1, amount=1, timestamp=0,
                     sharenote_event_ids=["ev1", "  ", "", "ev2"]).to_tags()
        assert len([t for t in tags if t[0] == "sn"]) == 2

    def test_from_tags_collects_sn_and_counts(self) -> None:
        tags = [
            ["d", "sid"], ["a", "addr"], ["h", "hh"], ["b", "bh"],
            ["workers", "w1"], ["height", "1"], ["amount", "1"],
            ["shares", "33z53", "5"], ["totalshares", "34z10", "20"],
            ["timestamp", "0"], ["sn", "ev1"], ["sn", "ev2", "ev3"], ["unknown", "x"],
        ]
        share = Share.from_tags(tags)
        assert share.sharenote_event_ids == ["ev1", "ev2", "ev3"]
        assert share.share_count == 5 and share.total_share_count == 20

    def test_round_trip(self) -> None:
        share = Share(
            share_id=pending_share_id(100, "addr1", "rig01"), address="addr1",
            height_hash=height_hash(100), block_hash="ab" * 32, chain_id="15",
            workers=["rig01", "rig02"], height=100, amount=1000, shares="33z53",
            share_count=5, total_shares="34z10", total_share_count=20,
            timestamp=1700000000, fee=100, est_payment_height=200,
            sharenote_event_ids=["event1"], tx=Transaction(txid="cc" * 32),
        )
        assert Share.from_tags(share.to_tags()) == share

    def test_from_event_accepts_share_kinds(self) -> None:
        share = Share(
            share_id=finalized_share_id(100, "addr1"), address="addr1",
            height_hash=height_hash(100), block_hash="b", workers=["w"],
            height=100, amount=1, timestamp=0,
        )
        for kind in (Kind.PENDING_SHARE, Kind.FINALIZED_SHARE, Kind.SHARE_PAYMENT):
            assert Share.from_event(share.to_event(kind)) == share
        with pytest.raises(InvalidEvent):
            Share.from_event({"kind": 1, "tags": []})

    def test_validate_pending(self) -> None:
        share = Share(
            share_id=pending_share_id(100, "addr1", "rig01"),
            height_hash=height_hash(100), block_hash="00" * 32,
            height=100, address="addr1", workers=["rig01"],
        )
        share.validate(Kind.PENDING_SHARE)

    def test_validate_finalized_and_payment(self) -> None:
        # A payment (35505) MUST carry a chain tag and a confirmed full-form
        # settlement (NIP-SN A13 / D5); a finalized share accepts the same shape.
        share = Share(
            share_id=finalized_share_id(100, "addr1"),
            height_hash=height_hash(100), block_hash="00" * 32, chain_id="15",
            height=100, address="addr1", workers=["rig01"],
            tx=Transaction(txid="t", confirmed=True, block_height=101, block_hash="bh"),
        )
        share.validate(Kind.FINALIZED_SHARE)
        share.validate(Kind.SHARE_PAYMENT)

    def test_validate_payment_requires_chain_and_full_x(self) -> None:
        base = dict(
            share_id=finalized_share_id(100, "addr1"),
            height_hash=height_hash(100), block_hash="00" * 32,
            height=100, address="addr1", workers=["rig01"],
        )
        # Missing chain (D5: require + error, no auto-inject).
        with pytest.raises(InvalidEvent):
            Share(**base, tx=Transaction(txid="t", confirmed=True, block_height=1, block_hash="h")).validate(Kind.SHARE_PAYMENT)
        # Short-form (unconfirmed) settlement.
        with pytest.raises(InvalidEvent):
            Share(**base, chain_id="15", tx=Transaction(txid="t")).validate(Kind.SHARE_PAYMENT)
        # Missing settlement entirely.
        with pytest.raises(InvalidEvent):
            Share(**base, chain_id="15").validate(Kind.SHARE_PAYMENT)

    def test_validate_errors(self) -> None:
        with pytest.raises(InvalidEvent):
            Share(height=0, workers=["w"]).validate(Kind.PENDING_SHARE)
        with pytest.raises(InvalidEvent):
            Share(height_hash="wrong", block_hash="00" * 32, height=100, workers=["w"]).validate(Kind.PENDING_SHARE)
        with pytest.raises(InvalidEvent):
            # block hash must be a 32-byte hex key (NIP-SN A9).
            Share(share_id=pending_share_id(100, "addr1", "rig01"), height_hash=height_hash(100),
                  block_hash="deadbeef", height=100, address="addr1", workers=["rig01"]).validate(Kind.PENDING_SHARE)
        with pytest.raises(InvalidEvent):
            Share(height_hash=height_hash(100), block_hash="00" * 32, height=100).validate(Kind.PENDING_SHARE)
        with pytest.raises(InvalidEvent):
            Share(share_id="wrong", height_hash=height_hash(100), block_hash="00" * 32, height=100,
                  address="addr1", workers=["rig01"]).validate(Kind.PENDING_SHARE)
        with pytest.raises(SharenoteError):
            Share(height_hash=height_hash(100), block_hash="00" * 32, height=100, address="a",
                  workers=["w"]).validate(99999)
