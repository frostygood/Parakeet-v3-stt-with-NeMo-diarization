import asyncio
from typing import Any, Callable, Dict, Optional

from app.logging_config import get_logger

logger = get_logger(__name__)


class TaskQueue:
    def __init__(self, maxsize: int, workers: int) -> None:
        self._queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue(maxsize=maxsize)
        self._workers = workers
        self._worker_tasks: list[asyncio.Task] = []

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize

    def size(self) -> int:
        return self._queue.qsize()

    def full(self) -> bool:
        return self._queue.full()

    async def start(self) -> None:
        if self._worker_tasks:
            return
        for index in range(self._workers):
            task = asyncio.create_task(self._worker(index))
            self._worker_tasks.append(task)

    async def stop(self) -> None:
        if not self._worker_tasks:
            return
        for _ in range(self._workers):
            await self._queue.put(None)
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []

    def enqueue(self, func: Callable[..., Any], **kwargs: Any) -> bool:
        try:
            self._queue.put_nowait({"func": func, "kwargs": kwargs})
            return True
        except asyncio.QueueFull:
            return False

    async def _worker(self, index: int) -> None:
        logger.info("Task worker %s started", index)
        while True:
            job = await self._queue.get()
            if job is None:
                self._queue.task_done()
                break
            try:
                func = job["func"]
                kwargs = job.get("kwargs", {})
                await asyncio.to_thread(func, **kwargs)
            except Exception as exc:
                logger.error("Worker %s failed: %s", index, exc, exc_info=True)
            finally:
                self._queue.task_done()
        logger.info("Task worker %s stopped", index)
