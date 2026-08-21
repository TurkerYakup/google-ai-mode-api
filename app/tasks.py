"""Async gorev kuyrugu: AI Mode cevaplari olculen ~10-15 sn (uc durumda daha uzun)
cogu HTTP istemcisinde zaman asimina dusuyor. Gorev ac, ID al, sonra sonucu cek."""

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .models import TaskInfo

log = logging.getLogger(__name__)

Runner = Callable[["TaskRecord"], Awaitable[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskRecord:
    def __init__(self, kind: str, payload: Any, tag: Optional[str], postback_url: Optional[str]) -> None:
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.payload = payload
        self.tag = tag
        self.postback_url = postback_url
        self.status = "queued"
        self.created_at = _now()
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.progress: Optional[str] = None
        self.result: Any = None
        self.error: Optional[Dict[str, str]] = None
        self.done_at: Optional[float] = None
        """Bitis zamani (monotonic) -- saklama suresi dolunca temizlemek icin."""

    def info(self, include_result: bool = True) -> TaskInfo:
        return TaskInfo(
            task_id=self.id,
            status=self.status,  # type: ignore[arg-type]
            kind=self.kind,  # type: ignore[arg-type]
            tag=self.tag,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            progress=self.progress,
            result=self.result if include_result else None,
            error=self.error,
        )


class TaskQueue:
    """Tek isci: Google'a paralel yuklenmemek icin gorevler sirayla islenir."""

    def __init__(
        self,
        runner: Runner,
        max_records: int = 200,
        postback: Optional[Callable] = None,
        retention: float = 3600.0,
    ) -> None:
        self._runner = runner
        self._postback = postback
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self._records: "OrderedDict[str, TaskRecord]" = OrderedDict()
        self._max = max_records
        self._retention = retention
        self._worker: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._loop(), name="task-worker")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def submit(self, kind: str, payload: Any, tag: Optional[str], postback_url: Optional[str]) -> TaskRecord:
        rec = TaskRecord(kind, payload, tag, postback_url)
        self._records[rec.id] = rec
        self._purge()
        self._q.put_nowait(rec.id)
        return rec

    def _purge(self) -> None:
        """Sonuclar RAM'de duruyor; suresi dolanlari ve fazlaligi at."""
        if self._retention > 0:
            cutoff = time.monotonic() - self._retention
            for tid in [t for t, r in self._records.items() if r.done_at and r.done_at < cutoff]:
                self._records.pop(tid, None)
        while len(self._records) > self._max:
            self._records.popitem(last=False)

    def get(self, task_id: str) -> Optional[TaskRecord]:
        return self._records.get(task_id)

    def list(self, status: Optional[str] = None, limit: int = 50) -> List[TaskRecord]:
        items = list(self._records.values())[::-1]
        if status:
            items = [r for r in items if r.status == status]
        return items[:limit]

    def pending(self) -> int:
        return self._q.qsize()

    async def _loop(self) -> None:
        while True:
            task_id = await self._q.get()
            rec = self._records.get(task_id)
            if rec is None:
                continue
            rec.status = "running"
            rec.started_at = _now()
            try:
                rec.result = await self._runner(rec)
                rec.status = "done"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # gorev hatasi isciyi oldurmemeli
                code = getattr(exc, "code", "internal_error")
                rec.status = "error"
                rec.error = {"code": code, "message": str(exc)}
                log.warning("Gorev %s basarisiz: %s", rec.id, exc)
            finally:
                rec.finished_at = _now()
                rec.done_at = time.monotonic()
                self._purge()

            if rec.postback_url and self._postback:
                try:
                    await self._postback(rec)
                except Exception as exc:
                    log.warning("Postback gonderilemedi (%s): %s", rec.postback_url, exc)
