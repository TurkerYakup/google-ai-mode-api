"""Sorgu sonuclari icin basit, surec ici TTL onbellegi."""

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


class TTLCache:
    def __init__(self, ttl: float, max_entries: int = 500) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    @staticmethod
    def key(parts: Dict[str, Any]) -> str:
        blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if self.ttl <= 0:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def clear(self) -> int:
        n = len(self._store)
        self._store.clear()
        return n
