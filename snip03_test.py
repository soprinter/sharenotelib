"""Tests for sharenotelib.snip03 (Kinds 35500-35505 - Pool Accounting)."""

import pytest
from sharenotelib.snip03 import (
    KIND_INVOICE, KIND_SETTLED_INVOICE,
    KIND_PENDING_SHARE, KIND_FINALIZED_SHARE, KIND_SHARE_PAYMENT,
    Transaction, Invoice, Share,
    marshal_invoice_tags, unmarshal_invoice_tags,
    marshal_share_tags, unmarshal_share_tags,
    validate_invoice, validate_share,
    compute_height_hash, compute_pending_share_id, compute_payment_share_id,
)


class TestConstants:
    def test_kind_values(self):
        assert KIND_INVOICE == 35500
        assert KIND_SETTLED_INVOICE == 35501
        assert KIND_PENDING_SHARE == 35503
        assert KIND_FINALIZED_SHARE == 35504
        assert KIND_SHARE_PAYMENT == 35505


class TestHashFunctions:
    def test_height_hash_deterministic(self):
        h1 = compute_height_hash(843000)
        h2 = compute_height_hash(843000)
        assert h1 == h2
        assert len(h1) == 64

    def test_height_hash_differs_per_height(self):
        assert compute_height_hash(1) != compute_height_hash(2)

    def test_height_hash_is_hex(self):
        h = compute_height_hash(100)
        int(h, 16)  # should not raise

    def test_pending_share_id_deterministic(self):
        id1 = compute_pending_share_id(100, "addr1", "rig01")
        id2 = compute_pending_share_id(100, "addr1", "rig01")
        assert id1 == id2

    def test_pending_share_id_includes_worker(self):
        id1 = compute_pending_share_id(100, "addr1", "rig01")
        id2 = compute_pending_share_id(100, "addr1", "rig02")
        assert id1 != id2

    def test_pending_share_id_includes_address(self):
        id1 = compute_pending_share_id(100, "addr1", "rig01")
        id2 = compute_pending_share_id(100, "addr2", "rig01")
        assert id1 != id2

    def test_pending_share_id_includes_height(self):
        id1 = compute_pending_share_id(100, "addr1", "rig01")
        id2 = compute_pending_share_id(101, "addr1", "rig01")
        assert id1 != id2

    def test_payment_share_id_deterministic(self):
        id1 = compute_payment_share_id(100, "addr1")
        id2 = compute_payment_share_id(100, "addr1")
        assert id1 == id2
        assert len(id1) == 64

    def test_payment_share_id_differs_by_address(self):
        assert compute_payment_share_id(100, "a") != compute_payment_share_id(100, "b")

    def test_payment_share_id_differs_by_height(self):
        assert compute_payment_share_id(1, "addr") != compute_payment_share_id(2, "addr")

    def test_cross_library_consistency(self):
        """Height hash and share IDs must match between Python and Go/TS (blake2b-256)."""
        # Known vector: blake2b-256 of "100"
        h = compute_height_hash(100)
        assert len(h) == 64
        # Verify it's actually blake2b-256, not sha256
        import hashlib
        expected = hashlib.blake2b(b"100", digest_size=32).hexdigest()
        assert h == expected


class TestInvoiceMarshal:
    def test_full_invoice_tags(self):
        inv = Invoice(
            height_hash="aabb", block_hash="ccdd",
            height=100, amount=5000, workers=3, shares="34z10",
        )
        tags = marshal_invoice_tags(inv)
        assert ["d", "aabb"] in tags
        assert ["b", "ccdd"] in tags
        assert ["height", "100"] in tags
        assert ["amount", "5000"] in tags
        assert ["workers", "3"] in tags
        assert ["shares", "34z10"] in tags

    def test_no_shares_omitted(self):
        inv = Invoice(height_hash="a", block_hash="b", height=1, amount=1, workers=1)
        tags = marshal_invoice_tags(inv)
        assert not any(t[0] == "shares" for t in tags)

    def test_no_tx_omitted(self):
        inv = Invoice(height_hash="a", block_hash="b", height=1, amount=1, workers=1)
        tags = marshal_invoice_tags(inv)
        assert not any(t[0] == "x" for t in tags)

    def test_unconfirmed_tx(self):
        inv = Invoice(
            height_hash="a", block_hash="b", height=1, amount=1, workers=1,
            tx=Transaction(txid="txid123"),
        )
        tags = marshal_invoice_tags(inv)
        x_tag = [t for t in tags if t[0] == "x"][0]
        assert x_tag == ["x", "txid123"]

    def test_confirmed_tx(self):
        inv = Invoice(
            height_hash="a", block_hash="b", height=1, amount=1, workers=1,
            tx=Transaction(txid="txid123", confirmed=True, block_height=50, block_hash="bh"),
        )
        tags = marshal_invoice_tags(inv)
        x_tag = [t for t in tags if t[0] == "x"][0]
        assert x_tag == ["x", "txid123", "50", "bh"]


class TestInvoiceUnmarshal:
    def test_skips_short_tags(self):
        tags = [["d"], ["d", "hash"]]
        inv = unmarshal_invoice_tags(tags)
        assert inv.height_hash == "hash"

    def test_all_fields_parsed(self):
        tags = [
            ["d", "hh"], ["b", "bh"], ["height", "100"],
            ["amount", "5000"], ["workers", "3"], ["shares", "34z10"],
        ]
        inv = unmarshal_invoice_tags(tags)
        assert inv.height_hash == "hh"
        assert inv.block_hash == "bh"
        assert inv.height == 100
        assert inv.amount == 5000
        assert inv.workers == 3
        assert inv.shares == "34z10"

    def test_unknown_tags_ignored(self):
        tags = [["d", "hh"], ["unknown", "val"]]
        inv = unmarshal_invoice_tags(tags)
        assert inv.height_hash == "hh"


class TestInvoiceRoundTrip:
    def test_without_tx(self):
        inv = Invoice(
            height_hash=compute_height_hash(843000), block_hash="00" * 32,
            height=843000, amount=625000000, workers=5, shares="34z10",
        )
        parsed = unmarshal_invoice_tags(marshal_invoice_tags(inv))
        assert parsed.height_hash == inv.height_hash
        assert parsed.height == 843000
        assert parsed.amount == 625000000
        assert parsed.workers == 5
        assert parsed.shares == "34z10"
        assert parsed.tx is None

    def test_with_confirmed_tx(self):
        inv = Invoice(
            height_hash=compute_height_hash(100), block_hash="ab" * 32,
            height=100, amount=5000, workers=2,
            tx=Transaction(txid="ff" * 32, confirmed=True, block_height=101, block_hash="cd" * 32),
        )
        parsed = unmarshal_invoice_tags(marshal_invoice_tags(inv))
        assert parsed.tx.txid == "ff" * 32
        assert parsed.tx.confirmed is True
        assert parsed.tx.block_height == 101

    def test_with_unconfirmed_tx(self):
        inv = Invoice(
            height_hash="h", block_hash="b", height=1, amount=1, workers=1,
            tx=Transaction(txid="abc"),
        )
        parsed = unmarshal_invoice_tags(marshal_invoice_tags(inv))
        assert parsed.tx.txid == "abc"
        assert parsed.tx.confirmed is False

    def test_minimal_invoice(self):
        inv = Invoice(height_hash="h", block_hash="b", height=1, amount=1, workers=1)
        parsed = unmarshal_invoice_tags(marshal_invoice_tags(inv))
        assert parsed.height == 1
        assert parsed.shares == ""
        assert parsed.tx is None


class TestShareMarshal:
    def test_full_share_tags(self):
        s = Share(
            share_id="sid", address="addr", height_hash="hh", block_hash="bh",
            chain_id="15", workers=["rig01", "rig02"], height=100, amount=1000,
            shares="33z53", share_count=5, total_shares="34z10", total_share_count=20,
            timestamp=1700000000, fee=100, est_payment_height=200,
            sharenote_event_ids=["ev1", "ev2"],
        )
        tags = marshal_share_tags(s)
        assert ["d", "sid"] in tags
        assert ["a", "addr"] in tags
        assert ["h", "hh"] in tags
        assert ["b", "bh"] in tags
        assert ["chain", "15"] in tags
        assert ["workers", "rig01", "rig02"] in tags
        assert ["height", "100"] in tags
        assert ["amount", "1000"] in tags
        assert ["shares", "33z53", "5"] in tags
        assert ["totalshares", "34z10", "20"] in tags
        assert ["timestamp", "1700000000"] in tags
        assert ["fee", "100"] in tags
        assert ["eph", "200"] in tags
        assert ["sn", "ev1"] in tags
        assert ["sn", "ev2"] in tags

    def test_no_chain_omitted(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, timestamp=0,
        )
        tags = marshal_share_tags(s)
        assert not any(t[0] == "chain" for t in tags)

    def test_no_fee_omitted(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, timestamp=0,
        )
        tags = marshal_share_tags(s)
        assert not any(t[0] == "fee" for t in tags)

    def test_no_eph_omitted(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, timestamp=0,
        )
        tags = marshal_share_tags(s)
        assert not any(t[0] == "eph" for t in tags)

    def test_shares_without_count(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, shares="33z53", timestamp=0,
        )
        tags = marshal_share_tags(s)
        shares_tag = [t for t in tags if t[0] == "shares"][0]
        assert shares_tag == ["shares", "33z53"]

    def test_whitespace_event_ids_skipped(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, timestamp=0,
            sharenote_event_ids=["ev1", "  ", "", "ev2"],
        )
        tags = marshal_share_tags(s)
        sn_tags = [t for t in tags if t[0] == "sn"]
        assert len(sn_tags) == 2


class TestShareUnmarshal:
    def test_multiple_sn_tags_collected(self):
        tags = [
            ["d", "sid"], ["a", "addr"], ["h", "hh"], ["b", "bh"],
            ["workers", "w1"], ["height", "1"], ["amount", "1"],
            ["timestamp", "0"], ["sn", "ev1"], ["sn", "ev2", "ev3"],
        ]
        s = unmarshal_share_tags(tags)
        assert s.sharenote_event_ids == ["ev1", "ev2", "ev3"]

    def test_unknown_tags_ignored(self):
        tags = [
            ["d", "sid"], ["a", "addr"], ["h", "hh"], ["b", "bh"],
            ["workers", "w1"], ["height", "1"], ["amount", "1"],
            ["timestamp", "0"], ["unknown", "val"],
        ]
        s = unmarshal_share_tags(tags)
        assert s.share_id == "sid"

    def test_shares_with_count(self):
        tags = [
            ["d", "s"], ["a", "a"], ["h", "h"], ["b", "b"],
            ["workers", "w"], ["height", "1"], ["amount", "1"],
            ["shares", "33z53", "5"], ["timestamp", "0"],
        ]
        s = unmarshal_share_tags(tags)
        assert s.shares == "33z53"
        assert s.share_count == 5

    def test_totalshares_with_count(self):
        tags = [
            ["d", "s"], ["a", "a"], ["h", "h"], ["b", "b"],
            ["workers", "w"], ["height", "1"], ["amount", "1"],
            ["totalshares", "34z10", "20"], ["timestamp", "0"],
        ]
        s = unmarshal_share_tags(tags)
        assert s.total_shares == "34z10"
        assert s.total_share_count == 20


class TestShareRoundTrip:
    def test_pending_share(self):
        s = Share(
            share_id=compute_pending_share_id(100, "addr1", "rig01"),
            address="addr1", height_hash=compute_height_hash(100),
            block_hash="ab" * 32, workers=["rig01"], height=100, amount=1000,
            shares="33z53", share_count=5, total_shares="34z10",
            total_share_count=20, timestamp=1700000000, fee=100,
            est_payment_height=200, sharenote_event_ids=["event1", "event2"],
        )
        parsed = unmarshal_share_tags(marshal_share_tags(s))
        assert parsed.share_id == s.share_id
        assert parsed.address == "addr1"
        assert parsed.workers == ["rig01"]
        assert parsed.shares == "33z53"
        assert parsed.share_count == 5
        assert parsed.total_shares == "34z10"
        assert parsed.total_share_count == 20
        assert parsed.fee == 100
        assert parsed.est_payment_height == 200
        assert parsed.sharenote_event_ids == ["event1", "event2"]

    def test_share_with_chain_and_tx(self):
        s = Share(
            share_id=compute_payment_share_id(100, "addr1"),
            address="addr1", height_hash=compute_height_hash(100),
            block_hash="ab" * 32, chain_id="15",
            workers=["rig01", "rig02"], height=100, amount=2000,
            timestamp=1700000000, tx=Transaction(txid="cc" * 32),
        )
        parsed = unmarshal_share_tags(marshal_share_tags(s))
        assert parsed.chain_id == "15"
        assert parsed.workers == ["rig01", "rig02"]
        assert parsed.tx.txid == "cc" * 32
        assert parsed.tx.confirmed is False

    def test_minimal_share(self):
        s = Share(
            share_id="s", address="a", height_hash="h", block_hash="b",
            workers=["w"], height=1, amount=1, timestamp=0,
        )
        parsed = unmarshal_share_tags(marshal_share_tags(s))
        assert parsed.shares == ""
        assert parsed.fee == 0
        assert parsed.est_payment_height == 0
        assert parsed.sharenote_event_ids == []
        assert parsed.tx is None


class TestValidateInvoice:
    def test_valid(self):
        inv = Invoice(height_hash=compute_height_hash(100), height=100, amount=5000)
        validate_invoice(inv)

    def test_zero_height(self):
        with pytest.raises(ValueError, match="height must be greater than zero"):
            validate_invoice(Invoice(height=0, amount=5000))

    def test_negative_height(self):
        with pytest.raises(ValueError, match="height must be greater than zero"):
            validate_invoice(Invoice(height=-1, amount=5000))

    def test_wrong_height_hash(self):
        with pytest.raises(ValueError, match="height hash mismatch"):
            validate_invoice(Invoice(height_hash="wrong", height=100, amount=5000))

    def test_zero_amount(self):
        with pytest.raises(ValueError, match="amount must be positive"):
            validate_invoice(Invoice(
                height_hash=compute_height_hash(100), height=100, amount=0,
            ))

    def test_negative_amount(self):
        with pytest.raises(ValueError, match="amount must be positive"):
            validate_invoice(Invoice(
                height_hash=compute_height_hash(100), height=100, amount=-1,
            ))


class TestValidateShare:
    def test_valid_pending(self):
        s = Share(
            share_id=compute_pending_share_id(100, "addr1", "rig01"),
            height_hash=compute_height_hash(100), height=100,
            address="addr1", workers=["rig01"],
        )
        validate_share(s, KIND_PENDING_SHARE)

    def test_valid_finalized(self):
        s = Share(
            share_id=compute_payment_share_id(100, "addr1"),
            height_hash=compute_height_hash(100), height=100,
            address="addr1", workers=["rig01"],
        )
        validate_share(s, KIND_FINALIZED_SHARE)

    def test_valid_payment(self):
        s = Share(
            share_id=compute_payment_share_id(100, "addr1"),
            height_hash=compute_height_hash(100), height=100,
            address="addr1", workers=["rig01"],
        )
        validate_share(s, KIND_SHARE_PAYMENT)

    def test_zero_height(self):
        with pytest.raises(ValueError, match="height must be greater than zero"):
            validate_share(Share(height=0, workers=["w"]), KIND_PENDING_SHARE)

    def test_wrong_height_hash(self):
        with pytest.raises(ValueError, match="height hash mismatch"):
            validate_share(
                Share(height_hash="wrong", height=100, workers=["w"]),
                KIND_PENDING_SHARE,
            )

    def test_no_workers(self):
        with pytest.raises(ValueError, match="at least one worker"):
            validate_share(
                Share(height_hash=compute_height_hash(100), height=100),
                KIND_PENDING_SHARE,
            )

    def test_wrong_share_id(self):
        with pytest.raises(ValueError, match="shareID mismatch"):
            validate_share(
                Share(
                    share_id="wrong",
                    height_hash=compute_height_hash(100), height=100,
                    address="addr1", workers=["rig01"],
                ),
                KIND_PENDING_SHARE,
            )

    def test_unknown_kind(self):
        with pytest.raises(ValueError, match="unknown share kind"):
            validate_share(
                Share(
                    height_hash=compute_height_hash(100), height=100,
                    address="addr1", workers=["rig01"],
                ),
                99999,
            )


class TestTransactionRoundTrip:
    def test_unconfirmed_tx(self):
        tags = [["d", "h"], ["x", "txid123"]]
        inv = unmarshal_invoice_tags(tags)
        assert inv.tx.txid == "txid123"
        assert inv.tx.confirmed is False
        assert inv.tx.block_height == 0

    def test_confirmed_tx(self):
        tags = [["d", "h"], ["x", "txid123", "50", "blockhash"]]
        inv = unmarshal_invoice_tags(tags)
        assert inv.tx.txid == "txid123"
        assert inv.tx.confirmed is True
        assert inv.tx.block_height == 50
        assert inv.tx.block_hash == "blockhash"

    def test_tx_with_empty_block_hash_stays_unconfirmed(self):
        tags = [["d", "h"], ["x", "txid123", "50", ""]]
        inv = unmarshal_invoice_tags(tags)
        assert inv.tx.confirmed is False
