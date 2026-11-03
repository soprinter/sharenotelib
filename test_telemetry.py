"""Tests for hashrate telemetry events (kind 35502)."""

from __future__ import annotations

import pytest

from sharenotelib import InvalidEvent, Kind, Telemetry, Worker


def test_kind() -> None:
    assert Telemetry.KIND == 35502 == Kind.HASHRATE


class TestToTags:
    def test_address_only(self) -> None:
        assert Telemetry(address="fc1qtest").to_tags() == [["a", "fc1qtest"]]

    def test_total_hashrate_with_and_without_msn(self) -> None:
        with_msn = Telemetry(address="fc1q", total_hashrate="5000", mean_sharenote="33z55")
        assert ["all", "5000", "msn:33z55"] in with_msn.to_tags()
        without = Telemetry(address="fc1q", total_hashrate="5000")
        assert ["all", "5000"] in without.to_tags()

    def test_h_tag_used_when_no_total(self) -> None:
        tags = Telemetry(address="fc1q", hashrate="1000", mean_sharenote="30z00").to_tags()
        assert ["h", "1000", "msn:30z00"] in tags
        assert not any(t[0] == "all" for t in tags)

    def test_total_takes_priority_over_h(self) -> None:
        tags = Telemetry(address="fc1q", total_hashrate="5000", hashrate="1000").to_tags()
        assert any(t[0] == "all" for t in tags)
        assert not any(t[0] == "h" for t in tags)

    def test_missing_address_raises(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry(address="").to_tags()

    def test_worker_all_fields(self) -> None:
        tele = Telemetry(
            address="fc1q",
            workers=[
                Worker(
                    name="rig01", hashrate="2500", sharenote="33z53",
                    mean_sharenote="33z50", accepted=42, rejected=3,
                    mean_time_sec="4.2", last_accepted_unix=1700000000,
                    user_agent="bmminer/2.0",
                )
            ],
        )
        tag = [t for t in tele.to_tags() if t[0].startswith("w:")][0]
        assert tag[0] == "w:rig01"
        for field in ("h:2500", "sn:33z53", "msn:33z50", "csn:42", "crsn:3",
                      "mt:4.2", "lsn:1700000000", "ua:bmminer/2.0"):
            assert field in tag

    def test_worker_minimal_and_crsn_omitted_when_zero(self) -> None:
        tag = Telemetry(address="fc1q", workers=[Worker(name="rig01")]).to_tags()
        w_tag = [t for t in tag if t[0].startswith("w:")][0]
        assert "csn:0" in w_tag
        assert not any(f.startswith("crsn:") for f in w_tag[1:])

    def test_blank_worker_name_skipped(self) -> None:
        tags = Telemetry(address="fc1q", workers=[Worker(name="  ")]).to_tags()
        assert not any(t[0].startswith("w:") for t in tags)

    def test_worker_tags_sorted_by_name(self) -> None:
        # D6 / NIP-SN A15: the builder sorts worker tags alphabetically by name.
        tele = Telemetry(address="fc1q", workers=[Worker(name=n) for n in ("rig03", "rig01", "rig02")])
        names = [t[0] for t in tele.to_tags() if t[0].startswith("w:")]
        assert names == ["w:rig01", "w:rig02", "w:rig03"]


class TestFromTags:
    def test_missing_and_empty(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry.from_tags([["h", "1000"]])
        with pytest.raises(InvalidEvent):
            Telemetry.from_tags([])

    def test_skips_empty_and_short_tags(self) -> None:
        assert Telemetry.from_tags([[], ["a"], ["a", "fc1q"]]).address == "fc1q"

    def test_all_msn_priority_over_h(self) -> None:
        tele = Telemetry.from_tags(
            [["a", "fc1q"], ["all", "5000", "msn:33z55"], ["h", "1000", "msn:30z00"]]
        )
        assert tele.total_hashrate == "5000"
        assert tele.mean_sharenote == "33z55"

    def test_h_provides_msn_when_all_absent(self) -> None:
        tele = Telemetry.from_tags([["a", "fc1q"], ["h", "1000", "msn:30z00"]])
        assert tele.hashrate == "1000" and tele.mean_sharenote == "30z00"

    def test_worker_prefix_only_skipped(self) -> None:
        assert Telemetry.from_tags([["a", "fc1q"], ["w:", "h:100"]]).workers == []

    def test_worker_unknown_and_malformed_fields(self) -> None:
        tele = Telemetry.from_tags(
            [["a", "fc1q"], ["w:rig01", "unknown:v", "nocolon", "h:", "sn:33z53", "h:100"]]
        )
        worker = tele.workers[0]
        assert worker.hashrate == "100" and worker.sharenote == "33z53"


class TestValidate:
    def test_accepts_all_xor_h(self) -> None:
        Telemetry(address="fc1q", total_hashrate="5000",
                  workers=[Worker(name="rig01", hashrate="2500")]).validate()
        Telemetry(address="fc1q", hashrate="2500").validate()

    def test_rejects_missing_address(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry(address="", total_hashrate="5000").validate()

    def test_rejects_neither_all_nor_h(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry(address="fc1q").validate()

    def test_rejects_both_all_and_h(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry(address="fc1q", total_hashrate="5000", hashrate="2500").validate()

    def test_rejects_worker_without_hashrate(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry(address="fc1q", total_hashrate="5000",
                      workers=[Worker(name="rig01")]).validate()


class TestRoundTrip:
    def test_full(self) -> None:
        tele = Telemetry(
            address="fc1qtest", total_hashrate="5000", mean_sharenote="33z55",
            workers=[
                Worker(name="rig01", hashrate="2500", sharenote="33z53",
                       mean_sharenote="33z50", accepted=42, rejected=3,
                       mean_time_sec="4.2", last_accepted_unix=1700000000,
                       user_agent="bmminer/2.0"),
                Worker(name="rig02", hashrate="2500", accepted=38),
            ],
        )
        parsed = Telemetry.from_tags(tele.to_tags())
        assert parsed == tele

    def test_from_event(self) -> None:
        tele = Telemetry(address="fc1q", total_hashrate="1000")
        event = tele.to_event()
        assert event["kind"] == 35502 and event["content"] == ""
        assert Telemetry.from_event(event) == tele

    def test_from_event_wrong_kind(self) -> None:
        with pytest.raises(InvalidEvent):
            Telemetry.from_event({"kind": 1, "tags": [["a", "fc1q"]]})
