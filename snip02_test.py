"""Tests for sharenotelib.snip02 (Kind 35502 - Hashrate Telemetry)."""

import pytest
from sharenotelib.snip02 import (
    KIND_HASHRATE,
    Worker,
    Hashrate,
    marshal_tags,
    unmarshal_tags,
)


class TestConstants:
    def test_kind_hashrate(self):
        assert KIND_HASHRATE == 35502


class TestMarshalTags:
    def test_address_only(self):
        hr = Hashrate(address="fc1qtest")
        tags = marshal_tags(hr)
        assert tags == [["a", "fc1qtest"]]

    def test_total_hashrate_with_msn(self):
        hr = Hashrate(address="fc1q", total_hashrate="5000", mean_sharenote="33z55")
        tags = marshal_tags(hr)
        assert ["all", "5000", "msn:33z55"] in tags

    def test_total_hashrate_without_msn(self):
        hr = Hashrate(address="fc1q", total_hashrate="5000")
        tags = marshal_tags(hr)
        assert ["all", "5000"] in tags

    def test_h_tag_when_no_total(self):
        hr = Hashrate(address="fc1q", hashrate="1000", mean_sharenote="30z00")
        tags = marshal_tags(hr)
        assert any(t[0] == "h" for t in tags)
        assert not any(t[0] == "all" for t in tags)
        assert ["h", "1000", "msn:30z00"] in tags

    def test_h_tag_without_msn(self):
        hr = Hashrate(address="fc1q", hashrate="1000")
        tags = marshal_tags(hr)
        assert ["h", "1000"] in tags

    def test_total_takes_priority_over_h(self):
        hr = Hashrate(address="fc1q", total_hashrate="5000", hashrate="1000")
        tags = marshal_tags(hr)
        assert any(t[0] == "all" for t in tags)
        assert not any(t[0] == "h" for t in tags)

    def test_missing_address_raises(self):
        with pytest.raises(ValueError, match="address is required"):
            marshal_tags(Hashrate())

    def test_worker_with_all_fields(self):
        hr = Hashrate(
            address="fc1q",
            workers=[Worker(
                name="rig01", hashrate="2500", sharenote="33z53",
                mean_sharenote="33z50", count_sharenotes=42,
                count_rejected_sharenotes=3, mean_time_sec="4.2",
                last_accepted_unix=1700000000, user_agent="bmminer/2.0",
            )],
        )
        tags = marshal_tags(hr)
        w_tag = [t for t in tags if t[0].startswith("w:")][0]
        assert w_tag[0] == "w:rig01"
        assert "h:2500" in w_tag
        assert "sn:33z53" in w_tag
        assert "msn:33z50" in w_tag
        assert "csn:42" in w_tag
        assert "crsn:3" in w_tag
        assert "mt:4.2" in w_tag
        assert "lsn:1700000000" in w_tag
        assert "ua:bmminer/2.0" in w_tag

    def test_worker_with_minimal_fields(self):
        hr = Hashrate(address="fc1q", workers=[Worker(name="rig01")])
        tags = marshal_tags(hr)
        w_tag = [t for t in tags if t[0].startswith("w:")][0]
        assert w_tag[0] == "w:rig01"
        assert "csn:0" in w_tag
        assert not any(f.startswith("h:") for f in w_tag[1:])
        assert not any(f.startswith("crsn:") for f in w_tag[1:])

    def test_blank_worker_name_skipped(self):
        hr = Hashrate(address="fc1q", workers=[Worker(name="  ")])
        tags = marshal_tags(hr)
        assert not any(t[0].startswith("w:") for t in tags)

    def test_multiple_workers_order(self):
        hr = Hashrate(
            address="fc1q",
            workers=[Worker(name="rig01"), Worker(name="rig02"), Worker(name="rig03")],
        )
        tags = marshal_tags(hr)
        w_tags = [t for t in tags if t[0].startswith("w:")]
        assert len(w_tags) == 3
        assert w_tags[0][0] == "w:rig01"
        assert w_tags[1][0] == "w:rig02"
        assert w_tags[2][0] == "w:rig03"

    def test_crsn_omitted_when_zero(self):
        hr = Hashrate(address="fc1q", workers=[Worker(name="rig01", count_rejected_sharenotes=0)])
        tags = marshal_tags(hr)
        w_tag = [t for t in tags if t[0].startswith("w:")][0]
        assert not any(f.startswith("crsn:") for f in w_tag[1:])


class TestUnmarshalTags:
    def test_missing_address_raises(self):
        with pytest.raises(ValueError, match="missing address tag"):
            unmarshal_tags([["h", "1000"]])

    def test_empty_tags(self):
        with pytest.raises(ValueError, match="missing address tag"):
            unmarshal_tags([])

    def test_skips_empty_tag_arrays(self):
        tags = [[], ["a", "fc1q"]]
        hr = unmarshal_tags(tags)
        assert hr.address == "fc1q"

    def test_skips_short_tags(self):
        tags = [["a"], ["a", "fc1q"]]
        hr = unmarshal_tags(tags)
        assert hr.address == "fc1q"

    def test_all_tag_extracts_msn(self):
        tags = [["a", "fc1q"], ["all", "5000", "msn:33z55"]]
        hr = unmarshal_tags(tags)
        assert hr.total_hashrate == "5000"
        assert hr.mean_sharenote == "33z55"

    def test_all_tag_without_msn(self):
        tags = [["a", "fc1q"], ["all", "5000"]]
        hr = unmarshal_tags(tags)
        assert hr.total_hashrate == "5000"
        assert hr.mean_sharenote == ""

    def test_h_tag_provides_msn_if_all_absent(self):
        tags = [["a", "fc1q"], ["h", "1000", "msn:30z00"]]
        hr = unmarshal_tags(tags)
        assert hr.hashrate == "1000"
        assert hr.mean_sharenote == "30z00"

    def test_all_msn_takes_priority_over_h_msn(self):
        tags = [["a", "fc1q"], ["all", "5000", "msn:33z55"], ["h", "1000", "msn:30z00"]]
        hr = unmarshal_tags(tags)
        assert hr.mean_sharenote == "33z55"

    def test_worker_prefix_w_colon_only_skipped(self):
        tags = [["a", "fc1q"], ["w:", "h:100"]]
        hr = unmarshal_tags(tags)
        assert len(hr.workers) == 0

    def test_worker_unknown_fields_ignored(self):
        tags = [["a", "fc1q"], ["w:rig01", "unknown:val", "h:100"]]
        hr = unmarshal_tags(tags)
        assert len(hr.workers) == 1
        assert hr.workers[0].hashrate == "100"

    def test_worker_field_without_colon_ignored(self):
        tags = [["a", "fc1q"], ["w:rig01", "nocolon", "h:100"]]
        hr = unmarshal_tags(tags)
        assert hr.workers[0].hashrate == "100"

    def test_worker_field_with_empty_value_ignored(self):
        tags = [["a", "fc1q"], ["w:rig01", "h:", "sn:33z53"]]
        hr = unmarshal_tags(tags)
        assert hr.workers[0].hashrate == ""
        assert hr.workers[0].sharenote == "33z53"


class TestRoundTrip:
    def test_full_round_trip(self):
        hr = Hashrate(
            address="fc1qtest",
            total_hashrate="5000",
            mean_sharenote="33z55",
            workers=[
                Worker(
                    name="rig01", hashrate="2500", sharenote="33z53",
                    mean_sharenote="33z50", count_sharenotes=42,
                    count_rejected_sharenotes=3, mean_time_sec="4.2",
                    last_accepted_unix=1700000000, user_agent="bmminer/2.0",
                ),
                Worker(name="rig02", hashrate="2500", count_sharenotes=38),
            ],
        )
        tags = marshal_tags(hr)
        parsed = unmarshal_tags(tags)

        assert parsed.address == hr.address
        assert parsed.total_hashrate == hr.total_hashrate
        assert parsed.mean_sharenote == hr.mean_sharenote
        assert len(parsed.workers) == 2

        w0 = parsed.workers[0]
        assert w0.name == "rig01"
        assert w0.hashrate == "2500"
        assert w0.sharenote == "33z53"
        assert w0.mean_sharenote == "33z50"
        assert w0.count_sharenotes == 42
        assert w0.count_rejected_sharenotes == 3
        assert w0.mean_time_sec == "4.2"
        assert w0.last_accepted_unix == 1700000000
        assert w0.user_agent == "bmminer/2.0"

    def test_address_only_round_trip(self):
        hr = Hashrate(address="fc1q")
        parsed = unmarshal_tags(marshal_tags(hr))
        assert parsed.address == "fc1q"
        assert parsed.workers == []
        assert parsed.total_hashrate == ""
        assert parsed.hashrate == ""

    def test_no_workers_round_trip(self):
        hr = Hashrate(address="fc1q", total_hashrate="1000")
        parsed = unmarshal_tags(marshal_tags(hr))
        assert parsed.total_hashrate == "1000"
        assert parsed.workers == []
