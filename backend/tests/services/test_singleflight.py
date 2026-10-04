import asyncio

import pytest

from app.services.singleflight import SingleFlight


class Gate:
    """A job that runs once released, counting how many times it started."""

    def __init__(self) -> None:
        self.starts = 0
        self.release = asyncio.Event()

    async def job(self) -> int:
        self.starts += 1
        await self.release.wait()
        return self.starts


async def test_run_concurrent_callers_with_one_key_share_one_execution() -> None:
    flight = SingleFlight[int]()
    gate = Gate()

    callers = [asyncio.create_task(flight.run("k", gate.job)) for _ in range(5)]
    await asyncio.sleep(0)
    gate.release.set()

    assert await asyncio.gather(*callers) == [1] * 5
    assert gate.starts == 1


async def test_run_different_keys_run_independently() -> None:
    flight = SingleFlight[int]()
    gate = Gate()
    gate.release.set()

    await asyncio.gather(flight.run("a", gate.job), flight.run("b", gate.job))

    assert gate.starts == 2


async def test_run_after_the_job_finished_starts_a_fresh_one() -> None:
    flight = SingleFlight[int]()
    gate = Gate()
    gate.release.set()

    first = await flight.run("k", gate.job)
    second = await flight.run("k", gate.job)

    assert (first, second) == (1, 2)  # deduplicates overlap, never caches


async def test_run_error_reaches_every_caller_and_frees_the_key() -> None:
    flight = SingleFlight[int]()
    started = 0

    async def failing() -> int:
        nonlocal started
        started += 1
        await asyncio.sleep(0)
        raise RuntimeError("vendor down")

    results = await asyncio.gather(
        flight.run("k", failing), flight.run("k", failing), return_exceptions=True
    )
    with pytest.raises(RuntimeError):
        await flight.run("k", failing)

    assert all(isinstance(r, RuntimeError) for r in results)
    assert started == 2  # one shared run, then a fresh one after the key was freed


async def test_run_cancelling_one_caller_does_not_abort_the_shared_job() -> None:
    flight = SingleFlight[int]()
    gate = Gate()
    impatient = asyncio.create_task(flight.run("k", gate.job))
    patient = asyncio.create_task(flight.run("k", gate.job))
    await asyncio.sleep(0)

    impatient.cancel()
    await asyncio.sleep(0)
    gate.release.set()

    assert await patient == 1
    assert gate.starts == 1
