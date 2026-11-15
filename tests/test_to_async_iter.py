import asyncio
import threading

from reaktiv import signal, to_async_iter


def test_worker_thread_write_wakes_a_waiting_consumer():
    async def main() -> None:
        source = signal(0)
        received: list[int] = []
        waiting = asyncio.Event()

        async def consume() -> None:
            async for value in to_async_iter(source):
                received.append(value)
                if value == 0:
                    waiting.set()
                if value == 2:
                    return

        consumer = asyncio.create_task(consume())
        await waiting.wait()
        await asyncio.sleep(0.01)  # the consumer is now blocked on the queue

        def write() -> None:
            source.set(1)
            source.set(2)

        worker = threading.Thread(target=write)
        worker.start()
        worker.join()
        await asyncio.wait_for(consumer, timeout=2)
        assert received == [0, 1, 2]

    asyncio.run(main(), debug=True)


def test_values_from_owner_loop_and_worker_threads_keep_write_order():
    async def main() -> None:
        source = signal(0)
        received: list[int] = []

        async def consume() -> None:
            async for value in to_async_iter(source):
                received.append(value)
                if len(received) == 3:
                    return

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        worker = threading.Thread(target=lambda: source.set(1))
        worker.start()
        worker.join()
        source.set(2)  # written after the worker's value: must arrive after it
        await asyncio.wait_for(consumer, timeout=2)
        assert received == [0, 1, 2]

    asyncio.run(main(), debug=True)
