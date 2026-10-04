"""Run one copy of an async job per key, however many callers ask at once."""

import asyncio
from collections.abc import Awaitable, Callable, Hashable


class SingleFlight[T]:
    """Concurrent callers with the same key share one execution and its result (or error).

    The job runs as its own task and callers await it through ``shield``, so a caller that is
    cancelled (a client hanging up) never aborts the work the others are waiting on. The key is
    forgotten the moment the job ends, so a later call starts a fresh run: this dedupes
    overlapping work, it does not cache.
    """

    def __init__(self) -> None:
        self._running: dict[Hashable, asyncio.Future[T]] = {}

    async def run(self, key: Hashable, job: Callable[[], Awaitable[T]]) -> T:
        flight = self._running.get(key)
        if flight is None:
            flight = asyncio.ensure_future(job())
            self._running[key] = flight
            flight.add_done_callback(lambda done: self._finished(key, done))
        return await asyncio.shield(flight)

    def _finished(self, key: Hashable, flight: asyncio.Future[T]) -> None:
        if self._running.get(key) is flight:
            del self._running[key]
        if not flight.cancelled():
            flight.exception()  # mark retrieved: every waiter may have been cancelled already
