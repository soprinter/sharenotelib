"""Tests for miner (kind 10520) and pool (kind 10521) identity events."""

from __future__ import annotations

import pytest

from sharenotelib import (
    ChainAddress,
    InvalidEvent,
    Kind,
    MinerIdentity,
    PayoutScheme,
    PayoutThreshold,
    PoolChain,
    PoolIdentity,
    PoolProfile,
)


def test_kinds() -> None:
    assert MinerIdentity.KIND == 10520 == Kind.MINER_IDENTITY
    assert PoolIdentity.KIND == 10521 == Kind.POOL_IDENTITY


class TestMinerIdentity:
    def test_to_tags(self) -> None:
        tags = MinerIdentity(
            chains=[ChainAddress("15", "fc1q"), ChainAddress("01", "bc1q")],
            preferred_payout="pplns",
        ).to_tags()
        assert ["a", "15", "fc1q"] in tags
        assert ["a", "01", "bc1q"] in tags
        assert ["payout", "pplns"] in tags

    def test_no_payout_tag_when_empty(self) -> None:
        tags = MinerIdentity(chains=[ChainAddress("15", "fc1q")]).to_tags()
        assert not any(t[0] == "payout" for t in tags)

    def test_errors(self) -> None:
        with pytest.raises(InvalidEvent):
            MinerIdentity().to_tags()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress(address="fc1q")]).to_tags()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress(chain_id="15")]).to_tags()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress("15", "a1"), ChainAddress("15", "a2")]).to_tags()

    def test_from_tags_and_errors(self) -> None:
        parsed = MinerIdentity.from_tags([["a", "15", "fc1q"], ["payout", "pps"], ["x", "y"]])
        assert parsed.chains[0].chain_id == "15" and parsed.preferred_payout == "pps"
        with pytest.raises(InvalidEvent):
            MinerIdentity.from_tags([["a", "15"]])  # needs 3 elements

    def test_round_trip_and_event(self) -> None:
        miner = MinerIdentity(
            chains=[ChainAddress("15", "fc1q"), ChainAddress("01", "bc1q")],
            preferred_payout="pplns",
        )
        assert MinerIdentity.from_tags(miner.to_tags()) == miner
        event = miner.to_event()
        assert event["kind"] == 10520 and event["content"] == ""
        assert MinerIdentity.from_event(event) == miner
        with pytest.raises(InvalidEvent):
            MinerIdentity.from_event({"kind": 1, "tags": []})

    def test_validate(self) -> None:
        # NIP-SN A5/A16: hex chain IDs, no duplicates, addresses present.
        MinerIdentity(chains=[ChainAddress("15", "fc1q"), ChainAddress("01", "bc1q")]).validate()
        with pytest.raises(InvalidEvent):
            MinerIdentity().validate()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress("xz", "fc1q")]).validate()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress("15", "a1"), ChainAddress("15", "a2")]).validate()
        with pytest.raises(InvalidEvent):
            MinerIdentity(chains=[ChainAddress("15", "")]).validate()


class TestPoolIdentity:
    def test_to_tags_full(self) -> None:
        tags = PoolIdentity(
            chains=[PoolChain("15", "fc1q", 150), PoolChain("01", "bc1q", 200)],
            payouts=[PayoutScheme("pps", ["fee:300"]), PayoutScheme("pplns", ["fee:150", "n:5000"])],
            min_sharenote="30z00",
            thresholds=[PayoutThreshold("15", 100000), PayoutThreshold("01", 50000)],
        ).to_tags()
        assert ["a", "15", "fc1q", "150"] in tags
        assert ["a", "01", "bc1q", "200"] in tags
        assert ["payout", "pps", "fee:300"] in tags
        assert ["payout", "pplns", "fee:150", "n:5000"] in tags
        assert ["sharenote", "30z00"] in tags
        assert ["threshold", "15", "100000"] in tags

    def test_zero_fee(self) -> None:
        tags = PoolIdentity(chains=[PoolChain("15", "fc1q", 0)], payouts=[PayoutScheme("prop")]).to_tags()
        assert ["a", "15", "fc1q", "0"] in tags

    def test_errors(self) -> None:
        with pytest.raises(InvalidEvent):
            PoolIdentity(payouts=[PayoutScheme("pps")]).to_tags()
        with pytest.raises(InvalidEvent):
            PoolIdentity(chains=[PoolChain("15", "fc1q", 0)]).to_tags()
        with pytest.raises(InvalidEvent):
            PoolIdentity(chains=[PoolChain("15", "fc1q", -1)], payouts=[PayoutScheme("pps")]).to_tags()
        with pytest.raises(InvalidEvent):
            PoolIdentity(
                chains=[PoolChain("15", "a1", 1), PoolChain("15", "a2", 2)],
                payouts=[PayoutScheme("pps")],
            ).to_tags()
        with pytest.raises(InvalidEvent):
            PoolIdentity(chains=[PoolChain("15", "fc1q", 0)], payouts=[PayoutScheme()]).to_tags()

    def test_from_tags(self) -> None:
        pool = PoolIdentity.from_tags([
            ["a", "15", "fc1q", "200"], ["payout", "pplns", "n:5000"],
            ["sharenote", "30z00"], ["threshold", "15", "100000"],
        ])
        assert pool.chains[0].fee_bps == 200
        assert pool.payouts[0].params == ["n:5000"]
        assert pool.min_sharenote == "30z00"
        assert pool.thresholds[0].amount == 100000

    def test_from_tags_errors_and_defaults(self) -> None:
        with pytest.raises(InvalidEvent):
            PoolIdentity.from_tags([["payout", "pps"]])
        with pytest.raises(InvalidEvent):
            PoolIdentity.from_tags([["a", "15", "fc1q"], ["payout", "pps"]])  # pool 'a' needs 4
        pool = PoolIdentity.from_tags([["a", "15", "fc1q", "notanumber"], ["payout", "pps"]])
        assert pool.chains[0].fee_bps == 0

    def test_content_round_trip(self) -> None:
        pool = PoolIdentity(
            profile=PoolProfile(name="TestPool", about="A test pool",
                                picture="https://pic.png", website="https://pool.io"),
            chains=[PoolChain("15", "fc1q", 200)],
            payouts=[PayoutScheme("pps")],
        )
        import json

        content = pool.to_content()
        assert json.loads(content) == {
            "name": "TestPool", "about": "A test pool",
            "picture": "https://pic.png", "website": "https://pool.io",
        }
        assert PoolIdentity.from_content(content) == pool.profile
        assert PoolIdentity.from_content("") == PoolProfile()

    def test_empty_profile_content_is_blank(self) -> None:
        pool = PoolIdentity(chains=[PoolChain("15", "fc1q", 0)], payouts=[PayoutScheme("pps")])
        assert pool.to_content() == ""

    def test_from_event_reads_tags_and_profile(self) -> None:
        pool = PoolIdentity(
            profile=PoolProfile(name="AlphaPool", website="https://alpha.io"),
            chains=[PoolChain("15", "fc1qpool", 200)],
            payouts=[PayoutScheme("pps")],
            min_sharenote="30z00",
        )
        parsed = PoolIdentity.from_event(pool.to_event())
        assert parsed.chains[0].fee_bps == 200
        assert parsed.payouts[0].scheme == "pps"
        assert parsed.min_sharenote == "30z00"
        assert parsed.profile.name == "AlphaPool"
        with pytest.raises(InvalidEvent):
            PoolIdentity.from_event({"kind": 1, "tags": []})

    def test_validate(self) -> None:
        # NIP-SN A6/A16: hex chain IDs, non-negative fee, >=1 payout, pplns n:.
        PoolIdentity(
            chains=[PoolChain("15", "fc1q", 150)],
            payouts=[PayoutScheme("pplns", ["fee:150", "n:5000"])],
        ).validate()
        with pytest.raises(InvalidEvent):  # no chains
            PoolIdentity(payouts=[PayoutScheme("pps")]).validate()
        with pytest.raises(InvalidEvent):  # no payouts
            PoolIdentity(chains=[PoolChain("15", "fc1q", 0)]).validate()
        with pytest.raises(InvalidEvent):  # non-hex chain id
            PoolIdentity(chains=[PoolChain("xz", "fc1q", 0)], payouts=[PayoutScheme("pps")]).validate()
        with pytest.raises(InvalidEvent):  # negative fee
            PoolIdentity(chains=[PoolChain("15", "fc1q", -1)], payouts=[PayoutScheme("pps")]).validate()
        with pytest.raises(InvalidEvent):  # duplicate chain id
            PoolIdentity(
                chains=[PoolChain("15", "a1", 0), PoolChain("15", "a2", 0)],
                payouts=[PayoutScheme("pps")],
            ).validate()
        with pytest.raises(InvalidEvent):  # pplns missing n:
            PoolIdentity(
                chains=[PoolChain("15", "fc1q", 0)],
                payouts=[PayoutScheme("pplns", ["fee:150"])],
            ).validate()

    def test_tags_round_trip_multi_scheme(self) -> None:
        pool = PoolIdentity(
            chains=[PoolChain("15", "fc1q", 150)],
            payouts=[PayoutScheme("pps", ["fee:300"]), PayoutScheme("pplns", ["fee:150", "n:5000"])],
        )
        parsed = PoolIdentity.from_tags(pool.to_tags())
        assert parsed.payouts == pool.payouts
        assert parsed.chains == pool.chains
