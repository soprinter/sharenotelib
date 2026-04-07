"""Tests for sharenotelib.snip05 (Kinds 10520-10521 - Sharenote Identity)."""

import json
import pytest
from sharenotelib.snip05 import (
    KIND_MINER_IDENTITY, KIND_POOL_IDENTITY,
    ChainAddress, MinerIdentity,
    PoolChain, PayoutScheme, PayoutThreshold, PoolProfile, PoolIdentity,
    marshal_miner_tags, unmarshal_miner_tags,
    marshal_pool_tags, unmarshal_pool_tags,
    marshal_pool_content, unmarshal_pool_content,
    marshal_tags, unmarshal_tags, Identity,
)


class TestConstants:
    def test_kind_miner_identity(self):
        assert KIND_MINER_IDENTITY == 10520

    def test_kind_pool_identity(self):
        assert KIND_POOL_IDENTITY == 10521


# ===================== Miner Identity =====================


class TestMinerMarshal:
    def test_single_chain(self):
        m = MinerIdentity(chains=[ChainAddress(chain_id="15", address="fc1qtest")])
        tags = marshal_miner_tags(m)
        assert ["a", "15", "fc1qtest"] in tags

    def test_multi_chain(self):
        m = MinerIdentity(chains=[
            ChainAddress(chain_id="15", address="fc1qtest"),
            ChainAddress(chain_id="01", address="bc1qtest"),
        ])
        tags = marshal_miner_tags(m)
        assert ["a", "15", "fc1qtest"] in tags
        assert ["a", "01", "bc1qtest"] in tags

    def test_with_preferred_payout(self):
        m = MinerIdentity(
            chains=[ChainAddress(chain_id="15", address="fc1q")],
            preferred_payout="pplns",
        )
        tags = marshal_miner_tags(m)
        assert ["payout", "pplns"] in tags

    def test_no_payout_tag_when_empty(self):
        m = MinerIdentity(chains=[ChainAddress(chain_id="15", address="fc1q")])
        tags = marshal_miner_tags(m)
        assert not any(t[0] == "payout" for t in tags)

    def test_no_chains_raises(self):
        with pytest.raises(ValueError, match="at least one chain"):
            marshal_miner_tags(MinerIdentity())

    def test_missing_chain_id_raises(self):
        with pytest.raises(ValueError, match="chain_id is required"):
            marshal_miner_tags(MinerIdentity(chains=[ChainAddress(address="fc1q")]))

    def test_missing_address_raises(self):
        with pytest.raises(ValueError, match="address is required"):
            marshal_miner_tags(MinerIdentity(chains=[ChainAddress(chain_id="15")]))

    def test_duplicate_chain_id_raises(self):
        with pytest.raises(ValueError, match="duplicate chain ID"):
            marshal_miner_tags(MinerIdentity(chains=[
                ChainAddress(chain_id="15", address="a1"),
                ChainAddress(chain_id="15", address="a2"),
            ]))


class TestMinerUnmarshal:
    def test_single_chain(self):
        tags = [["a", "15", "fc1qtest"]]
        m = unmarshal_miner_tags(tags)
        assert len(m.chains) == 1
        assert m.chains[0].chain_id == "15"
        assert m.chains[0].address == "fc1qtest"

    def test_multi_chain(self):
        tags = [["a", "15", "fc1q"], ["a", "01", "bc1q"]]
        m = unmarshal_miner_tags(tags)
        assert len(m.chains) == 2

    def test_with_payout(self):
        tags = [["a", "15", "fc1q"], ["payout", "pps"]]
        m = unmarshal_miner_tags(tags)
        assert m.preferred_payout == "pps"

    def test_no_a_tag_raises(self):
        with pytest.raises(ValueError, match="required tag 'a'"):
            unmarshal_miner_tags([])

    def test_short_a_tag_skipped(self):
        with pytest.raises(ValueError, match="required tag 'a'"):
            unmarshal_miner_tags([["a", "15"]])  # needs 3 elements

    def test_unknown_tags_ignored(self):
        tags = [["a", "15", "fc1q"], ["unknown", "val"]]
        m = unmarshal_miner_tags(tags)
        assert len(m.chains) == 1


class TestMinerRoundTrip:
    def test_single_chain(self):
        m = MinerIdentity(chains=[ChainAddress(chain_id="15", address="fc1qtest")])
        parsed = unmarshal_miner_tags(marshal_miner_tags(m))
        assert parsed.chains[0].chain_id == "15"
        assert parsed.chains[0].address == "fc1qtest"

    def test_multi_chain_with_payout(self):
        m = MinerIdentity(
            chains=[
                ChainAddress(chain_id="15", address="fc1q"),
                ChainAddress(chain_id="01", address="bc1q"),
            ],
            preferred_payout="pplns",
        )
        parsed = unmarshal_miner_tags(marshal_miner_tags(m))
        assert len(parsed.chains) == 2
        assert parsed.preferred_payout == "pplns"


# ===================== Pool Identity =====================


class TestPoolMarshal:
    def test_simple_pps_pool(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1qpool", fee_bps=200)],
            payouts=[PayoutScheme(scheme="pps")],
        )
        tags = marshal_pool_tags(p)
        assert ["a", "15", "fc1qpool", "200"] in tags
        assert ["payout", "pps"] in tags

    def test_multi_chain_different_fees(self):
        p = PoolIdentity(
            chains=[
                PoolChain(chain_id="15", address="fc1q", fee_bps=150),
                PoolChain(chain_id="01", address="bc1q", fee_bps=200),
            ],
            payouts=[PayoutScheme(scheme="pplns", params=["n:10000"])],
        )
        tags = marshal_pool_tags(p)
        assert ["a", "15", "fc1q", "150"] in tags
        assert ["a", "01", "bc1q", "200"] in tags

    def test_pplns_with_params(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=100)],
            payouts=[PayoutScheme(scheme="pplns", params=["n:5000"])],
        )
        tags = marshal_pool_tags(p)
        assert ["payout", "pplns", "n:5000"] in tags

    def test_multi_scheme(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=150)],
            payouts=[
                PayoutScheme(scheme="pps", params=["fee:300"]),
                PayoutScheme(scheme="pplns", params=["fee:150", "n:5000"]),
            ],
        )
        tags = marshal_pool_tags(p)
        payout_tags = [t for t in tags if t[0] == "payout"]
        assert len(payout_tags) == 2
        assert ["payout", "pps", "fee:300"] in tags
        assert ["payout", "pplns", "fee:150", "n:5000"] in tags

    def test_solo_pool(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=100)],
            payouts=[PayoutScheme(scheme="solo")],
        )
        tags = marshal_pool_tags(p)
        assert ["payout", "solo"] in tags

    def test_zero_fee(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=0)],
            payouts=[PayoutScheme(scheme="prop")],
        )
        tags = marshal_pool_tags(p)
        assert ["a", "15", "fc1q", "0"] in tags

    def test_with_sharenote(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=200)],
            payouts=[PayoutScheme(scheme="pps")],
            min_sharenote="30z00",
        )
        tags = marshal_pool_tags(p)
        assert ["sharenote", "30z00"] in tags

    def test_with_thresholds(self):
        p = PoolIdentity(
            chains=[
                PoolChain(chain_id="15", address="fc1q", fee_bps=200),
                PoolChain(chain_id="01", address="bc1q", fee_bps=150),
            ],
            payouts=[PayoutScheme(scheme="pps")],
            thresholds=[
                PayoutThreshold(chain_id="15", amount=100000),
                PayoutThreshold(chain_id="01", amount=50000),
            ],
        )
        tags = marshal_pool_tags(p)
        assert ["threshold", "15", "100000"] in tags
        assert ["threshold", "01", "50000"] in tags

    def test_no_chains_raises(self):
        with pytest.raises(ValueError, match="at least one chain"):
            marshal_pool_tags(PoolIdentity(payouts=[PayoutScheme(scheme="pps")]))

    def test_no_payouts_raises(self):
        with pytest.raises(ValueError, match="at least one payout"):
            marshal_pool_tags(PoolIdentity(
                chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=0)],
            ))

    def test_negative_fee_raises(self):
        with pytest.raises(ValueError, match="fee must be non-negative"):
            marshal_pool_tags(PoolIdentity(
                chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=-1)],
                payouts=[PayoutScheme(scheme="pps")],
            ))

    def test_duplicate_chain_raises(self):
        with pytest.raises(ValueError, match="duplicate chain ID"):
            marshal_pool_tags(PoolIdentity(
                chains=[
                    PoolChain(chain_id="15", address="a1", fee_bps=100),
                    PoolChain(chain_id="15", address="a2", fee_bps=200),
                ],
                payouts=[PayoutScheme(scheme="pps")],
            ))

    def test_empty_scheme_raises(self):
        with pytest.raises(ValueError, match="payout scheme is required"):
            marshal_pool_tags(PoolIdentity(
                chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=0)],
                payouts=[PayoutScheme()],
            ))


class TestPoolUnmarshal:
    def test_simple(self):
        tags = [["a", "15", "fc1q", "200"], ["payout", "pps"]]
        p = unmarshal_pool_tags(tags)
        assert len(p.chains) == 1
        assert p.chains[0].fee_bps == 200
        assert len(p.payouts) == 1
        assert p.payouts[0].scheme == "pps"

    def test_payout_params(self):
        tags = [["a", "15", "fc1q", "100"], ["payout", "pplns", "n:5000"]]
        p = unmarshal_pool_tags(tags)
        assert p.payouts[0].params == ["n:5000"]

    def test_multi_scheme(self):
        tags = [
            ["a", "15", "fc1q", "150"],
            ["payout", "pps", "fee:300"],
            ["payout", "pplns", "fee:150", "n:5000"],
        ]
        p = unmarshal_pool_tags(tags)
        assert len(p.payouts) == 2

    def test_sharenote_parsed(self):
        tags = [["a", "15", "fc1q", "0"], ["payout", "pps"], ["sharenote", "30z00"]]
        p = unmarshal_pool_tags(tags)
        assert p.min_sharenote == "30z00"

    def test_thresholds_parsed(self):
        tags = [
            ["a", "15", "fc1q", "200"], ["payout", "pps"],
            ["threshold", "15", "100000"],
        ]
        p = unmarshal_pool_tags(tags)
        assert len(p.thresholds) == 1
        assert p.thresholds[0].amount == 100000

    def test_no_a_tag_raises(self):
        with pytest.raises(ValueError, match="required tag 'a'"):
            unmarshal_pool_tags([["payout", "pps"]])

    def test_short_a_tag_skipped(self):
        """Pool a tag needs 4 elements; 3-element tag is skipped."""
        with pytest.raises(ValueError, match="required tag 'a'"):
            unmarshal_pool_tags([["a", "15", "fc1q"], ["payout", "pps"]])

    def test_invalid_fee_defaults_zero(self):
        tags = [["a", "15", "fc1q", "notanumber"], ["payout", "pps"]]
        p = unmarshal_pool_tags(tags)
        assert p.chains[0].fee_bps == 0


class TestPoolContent:
    def test_marshal_full_profile(self):
        p = PoolIdentity(
            profile=PoolProfile(
                name="TestPool", about="A test pool",
                picture="https://pic.png", website="https://pool.io",
            ),
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=200)],
            payouts=[PayoutScheme(scheme="pps")],
        )
        content = marshal_pool_content(p)
        d = json.loads(content)
        assert d["name"] == "TestPool"
        assert d["about"] == "A test pool"
        assert d["picture"] == "https://pic.png"
        assert d["website"] == "https://pool.io"

    def test_marshal_empty_profile(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=0)],
            payouts=[PayoutScheme(scheme="pps")],
        )
        assert marshal_pool_content(p) == ""

    def test_marshal_partial_profile(self):
        p = PoolIdentity(
            profile=PoolProfile(name="Pool"),
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=0)],
            payouts=[PayoutScheme(scheme="pps")],
        )
        content = marshal_pool_content(p)
        d = json.loads(content)
        assert d["name"] == "Pool"
        assert "about" not in d

    def test_unmarshal_content(self):
        p = PoolIdentity()
        unmarshal_pool_content('{"name":"TestPool","about":"desc"}', p)
        assert p.profile.name == "TestPool"
        assert p.profile.about == "desc"
        assert p.profile.picture == ""

    def test_unmarshal_empty_content(self):
        p = PoolIdentity()
        unmarshal_pool_content("", p)
        assert p.profile.name == ""


class TestPoolRoundTrip:
    def test_pps_pool(self):
        p = PoolIdentity(
            profile=PoolProfile(name="AlphaPool", website="https://alpha.io"),
            chains=[PoolChain(chain_id="15", address="fc1qpool", fee_bps=200)],
            payouts=[PayoutScheme(scheme="pps")],
            min_sharenote="30z00",
        )
        tags = marshal_pool_tags(p)
        content = marshal_pool_content(p)
        parsed = unmarshal_pool_tags(tags)
        unmarshal_pool_content(content, parsed)

        assert parsed.chains[0].fee_bps == 200
        assert parsed.payouts[0].scheme == "pps"
        assert parsed.min_sharenote == "30z00"
        assert parsed.profile.name == "AlphaPool"

    def test_multi_chain_pplns(self):
        p = PoolIdentity(
            chains=[
                PoolChain(chain_id="15", address="fc1q", fee_bps=150),
                PoolChain(chain_id="01", address="bc1q", fee_bps=200),
            ],
            payouts=[PayoutScheme(scheme="pplns", params=["n:10000"])],
            thresholds=[
                PayoutThreshold(chain_id="15", amount=100000),
                PayoutThreshold(chain_id="01", amount=50000),
            ],
        )
        tags = marshal_pool_tags(p)
        parsed = unmarshal_pool_tags(tags)

        assert len(parsed.chains) == 2
        assert parsed.chains[0].fee_bps == 150
        assert parsed.chains[1].fee_bps == 200
        assert parsed.payouts[0].params == ["n:10000"]
        assert len(parsed.thresholds) == 2

    def test_multi_scheme(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=150)],
            payouts=[
                PayoutScheme(scheme="pps", params=["fee:300"]),
                PayoutScheme(scheme="pplns", params=["fee:150", "n:5000"]),
            ],
        )
        tags = marshal_pool_tags(p)
        parsed = unmarshal_pool_tags(tags)

        assert len(parsed.payouts) == 2
        assert parsed.payouts[0].scheme == "pps"
        assert parsed.payouts[0].params == ["fee:300"]
        assert parsed.payouts[1].scheme == "pplns"
        assert parsed.payouts[1].params == ["fee:150", "n:5000"]

    def test_solo_pool(self):
        p = PoolIdentity(
            chains=[PoolChain(chain_id="15", address="fc1q", fee_bps=100)],
            payouts=[PayoutScheme(scheme="solo")],
            min_sharenote="34z00",
        )
        parsed = unmarshal_pool_tags(marshal_pool_tags(p))
        assert parsed.payouts[0].scheme == "solo"
        assert parsed.payouts[0].params == []


# ===================== Backwards Compatibility =====================


class TestBackwardsCompat:
    def test_identity_alias(self):
        assert Identity is ChainAddress

    def test_marshal_tags_compat(self):
        tags = marshal_tags(ChainAddress(chain_id="15", address="fc1q"))
        assert ["a", "15", "fc1q"] in tags

    def test_unmarshal_tags_compat(self):
        tags = [["a", "15", "fc1qtest"]]
        ident = unmarshal_tags(tags)
        assert ident.chain_id == "15"
        assert ident.address == "fc1qtest"
