"""SNIP-02: Hashrate & Telemetry Event Helpers (Kind 35502).

Provides types and marshal/unmarshal functions for hashrate telemetry
events broadcast by miners and pools over Nostr.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

KIND_HASHRATE = 35502

_WORKER_PREFIX = "w:"


@dataclass
class Worker:
    name: str
    hashrate: str = ""
    sharenote: str = ""
    mean_sharenote: str = ""
    count_sharenotes: int = 0
    count_rejected_sharenotes: int = 0
    mean_time_sec: str = ""
    last_accepted_unix: int = 0
    user_agent: str = ""


@dataclass
class Hashrate:
    address: str = ""
    total_hashrate: str = ""
    mean_sharenote: str = ""
    hashrate: str = ""
    workers: List[Worker] = field(default_factory=list)


Tags = List[List[str]]


def marshal_tags(hr: Hashrate) -> Tags:
    if not hr.address:
        raise ValueError("address is required")

    tags: Tags = [["a", hr.address]]

    if hr.total_hashrate:
        tag = ["all", hr.total_hashrate]
        if hr.mean_sharenote:
            tag.append(f"msn:{hr.mean_sharenote}")
        tags.append(tag)
    elif hr.hashrate:
        tag = ["h", hr.hashrate]
        if hr.mean_sharenote:
            tag.append(f"msn:{hr.mean_sharenote}")
        tags.append(tag)

    for w in hr.workers:
        tag = _marshal_worker(w)
        if tag:
            tags.append(tag)

    return tags


def unmarshal_tags(tags: Tags) -> Hashrate:
    hr = Hashrate()

    for tag in tags:
        if not tag:
            continue
        key = tag[0]

        if key == "a" and len(tag) >= 2:
            hr.address = tag[1]
        elif key == "all" and len(tag) >= 2:
            hr.total_hashrate = tag[1]
            hr.mean_sharenote = _extract_inline_msn(tag[2:])
        elif key == "h" and len(tag) >= 2:
            hr.hashrate = tag[1]
            if not hr.mean_sharenote:
                hr.mean_sharenote = _extract_inline_msn(tag[2:])
        elif key.startswith(_WORKER_PREFIX):
            name = key[len(_WORKER_PREFIX):]
            if not name:
                continue
            w = Worker(name=name)
            for f in tag[1:]:
                k, _, v = f.partition(":")
                if not v:
                    continue
                if k == "h":
                    w.hashrate = v
                elif k == "sn":
                    w.sharenote = v
                elif k == "msn":
                    w.mean_sharenote = v
                elif k == "csn":
                    w.count_sharenotes = int(v)
                elif k == "crsn":
                    w.count_rejected_sharenotes = int(v)
                elif k == "mt":
                    w.mean_time_sec = v
                elif k == "lsn":
                    w.last_accepted_unix = int(v)
                elif k == "ua":
                    w.user_agent = v
            hr.workers.append(w)

    if not hr.address:
        raise ValueError("missing address tag")

    return hr


def _marshal_worker(w: Worker) -> Optional[List[str]]:
    name = w.name.strip()
    if not name:
        return None

    tag = [f"{_WORKER_PREFIX}{name}"]
    if w.hashrate:
        tag.append(f"h:{w.hashrate}")
    if w.sharenote:
        tag.append(f"sn:{w.sharenote}")
    if w.mean_sharenote:
        tag.append(f"msn:{w.mean_sharenote}")
    tag.append(f"csn:{w.count_sharenotes}")
    if w.count_rejected_sharenotes > 0:
        tag.append(f"crsn:{w.count_rejected_sharenotes}")
    if w.mean_time_sec:
        tag.append(f"mt:{w.mean_time_sec}")
    if w.last_accepted_unix:
        tag.append(f"lsn:{w.last_accepted_unix}")
    if w.user_agent:
        tag.append(f"ua:{w.user_agent}")
    return tag


def _extract_inline_msn(fields: List[str]) -> str:
    for f in fields:
        if f.startswith("msn:"):
            return f[4:]
    return ""
