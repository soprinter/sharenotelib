"""Tests for operator messaging events (kind 35515, optional)."""

from __future__ import annotations

import pytest

from sharenotelib import InvalidEvent, Kind, OperatorMessage


def test_kind() -> None:
    assert OperatorMessage.KIND == 35515 == Kind.OPERATOR_MESSAGE


def test_to_tags_minimal() -> None:
    tags = OperatorMessage(counterparty="pub", thread_id="thread").to_tags()
    assert tags == [["p", "pub"], ["d", "thread"]]


def test_to_tags_with_context_and_subject() -> None:
    tags = OperatorMessage(
        counterparty="pub", thread_id="thread",
        chain_id="15", address="fc1q", subject="Payout threshold change",
    ).to_tags()
    assert ["a", "15", "fc1q"] in tags
    assert ["subject", "Payout threshold change"] in tags


def test_to_tags_requires_p_and_d() -> None:
    with pytest.raises(InvalidEvent):
        OperatorMessage(counterparty="", thread_id="t").to_tags()
    with pytest.raises(InvalidEvent):
        OperatorMessage(counterparty="p", thread_id="").to_tags()


def test_to_event_carries_ciphertext() -> None:
    msg = OperatorMessage(counterparty="pub", thread_id="t", content="<nip44 ciphertext>")
    event = msg.to_event()
    assert event["kind"] == 35515
    assert event["content"] == "<nip44 ciphertext>"


def test_round_trip_via_event() -> None:
    msg = OperatorMessage(
        counterparty="pub", thread_id="thread", content="cipher",
        chain_id="15", address="fc1q", subject="hi",
    )
    assert OperatorMessage.from_event(msg.to_event()) == msg


def test_from_tags_rejects_missing_or_duplicate_p_d() -> None:
    with pytest.raises(InvalidEvent):
        OperatorMessage.from_tags([["d", "t"]])
    with pytest.raises(InvalidEvent):
        OperatorMessage.from_tags([["p", "a"]])
    with pytest.raises(InvalidEvent):
        OperatorMessage.from_tags([["p", "a"], ["p", "b"], ["d", "t"]])


def test_from_event_wrong_kind() -> None:
    with pytest.raises(InvalidEvent):
        OperatorMessage.from_event({"kind": 1, "tags": [["p", "a"], ["d", "t"]]})
