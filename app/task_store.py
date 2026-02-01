import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TaskState:
    task_id: str
    status: str
    progress: int = 0
    step: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskState] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str) -> TaskState:
        state = TaskState(task_id=task_id, status="pending")
        with self._lock:
            self._tasks[task_id] = state
        return state

    def get(self, task_id: str) -> Optional[TaskState]:
        with self._lock:
            return self._tasks.get(task_id)

    def update(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        step: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskState]:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return None
            if status is not None:
                state.status = status
            if progress is not None:
                state.progress = progress
            if step is not None:
                state.step = step
            if result is not None:
                state.result = result
            if error is not None:
                state.error = error
            state.updated_at = time.time()
            return state

    def set_result(self, task_id: str, result: Dict[str, Any]) -> Optional[TaskState]:
        return self.update(
            task_id,
            status="completed",
            progress=100,
            step="Completed",
            result=result,
            error=None,
        )

    def set_error(self, task_id: str, error: str) -> Optional[TaskState]:
        return self.update(
            task_id,
            status="failed",
            step="Failed",
            error=error,
        )


task_store = TaskStore()
