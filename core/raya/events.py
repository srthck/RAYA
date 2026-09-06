"""The pipeline event log.

Two things depend on this module, and both matter:

1. The frontend renders progress from these events over SSE. Nothing in the UI
   is driven by a timer -- if a stage is on screen, the backend actually
   reached it.
2. `/replay/{id}` reconstructs a past run from the persisted log. Replay is
   therefore a recording, not a re-animation.

Because the log is the source of truth for both, events are append-only and
carry monotonically increasing sequence numbers.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable


class EventType:
    """Stable event names. The frontend switches on these strings."""

    PIPELINE_STARTED = "pipeline.started"

    INPUT_RECEIVED = "input.received"
    INPUT_HASHED = "input.hashed"

    FACE_DETECTING = "face.detecting"
    FACE_DETECTED = "face.detected"
    FACE_SELECTED = "face.selected"
    FACE_ENCODED = "face.encoded"

    SEARCH_PREPARING = "search.preparing"
    SEARCH_STARTED = "search.started"
    SEARCH_COMPLETED = "search.completed"

    CANDIDATE_DISCOVERED = "candidate.discovered"
    CANDIDATE_CLASSIFIED = "candidate.classified"
    CANDIDATE_EVALUATING = "candidate.evaluating"
    CANDIDATE_FETCHED = "candidate.fetched"
    CANDIDATE_FACE_FOUND = "candidate.face_found"
    CANDIDATE_COMPARED = "candidate.compared"
    CANDIDATE_VERIFIED = "candidate.verified"
    CANDIDATE_REJECTED = "candidate.rejected"

    MATCH_SELECTED = "match.selected"

    EVIDENCE_CREATED = "evidence.created"
    EVIDENCE_HASHED = "evidence.hashed"

    IPFS_UPLOADING = "ipfs.uploading"
    IPFS_UPLOADED = "ipfs.uploaded"

    BLOCKCHAIN_SUBMITTING = "blockchain.submitting"
    BLOCKCHAIN_SUBMITTED = "blockchain.submitted"
    BLOCKCHAIN_CONFIRMED = "blockchain.confirmed"

    READBACK_STARTED = "readback.started"
    READBACK_COMPLETED = "readback.completed"

    INTEGRITY_CHECKING = "integrity.checking"
    INTEGRITY_VERIFIED = "integrity.verified"
    INTEGRITY_FAILED = "integrity.failed"

    STAGE_FAILED = "stage.failed"
    VERIFICATION_COMPLETED = "verification.completed"
    VERIFICATION_FAILED = "verification.failed"


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    at: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "type": self.type, "at": self.at, "data": self.data}


_SENTINEL = object()


class EventBus:
    """Append-only log with fan-out to live subscribers.

    A late subscriber receives the full backlog before any new event, so a
    browser that connects mid-run still renders the earlier stages instead of
    starting from a blank workspace.
    """

    def __init__(self, verification_id: str):
        self.verification_id = verification_id
        self._log: list[Event] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._seq = 0
        self._closed = False
        self._hooks: list[Callable[[Event], None]] = []

    # ---- producing ---------------------------------------------------------

    def emit(self, event_type: str, **data: Any) -> Event:
        if self._closed:
            raise RuntimeError("cannot emit on a closed event bus")
        self._seq += 1
        event = Event(seq=self._seq, type=event_type, at=time.time(), data=data)
        self._log.append(event)
        for hook in self._hooks:
            hook(event)
        for queue in list(self._subscribers):
            queue.put_nowait(event)
        return event

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for queue in list(self._subscribers):
            queue.put_nowait(_SENTINEL)

    def add_hook(self, hook: Callable[[Event], None]) -> None:
        """Register a synchronous observer, e.g. a persistence writer."""
        self._hooks.append(hook)

    # ---- consuming ---------------------------------------------------------

    @property
    def log(self) -> list[Event]:
        return list(self._log)

    @property
    def closed(self) -> bool:
        return self._closed

    async def subscribe(self) -> AsyncIterator[Event]:
        """Yield the backlog, then live events until the bus closes."""
        queue: asyncio.Queue = asyncio.Queue()
        backlog = list(self._log)
        already_closed = self._closed
        if not already_closed:
            self._subscribers.add(queue)
        try:
            for event in backlog:
                yield event
            if already_closed:
                return
            seen = backlog[-1].seq if backlog else 0
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    return
                # Guard against duplicating an event that was both in the
                # backlog snapshot and delivered to the queue.
                if item.seq > seen:
                    seen = item.seq
                    yield item
        finally:
            self._subscribers.discard(queue)
