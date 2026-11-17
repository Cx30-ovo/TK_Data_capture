"""FIFO admission for automatic browser time slices; no storage or network."""
import asyncio
import time
from contextlib import asynccontextmanager


class MonitorScheduler:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._waiting = []
        self._active = None
        self._sequence = 0

    @asynccontextmanager
    async def turn(self, kind):
        self._sequence += 1
        entry = {'id': self._sequence, 'kind': kind, 'queued_at': time.time()}
        self._waiting.append(entry)
        acquired = False
        try:
            await self._lock.acquire()
            acquired = True
            self._waiting.remove(entry)
            self._active = {**entry, 'started_at': time.time()}
            yield
        finally:
            if acquired:
                self._active = None
                self._lock.release()
            elif entry in self._waiting:
                self._waiting.remove(entry)

    def snapshot(self):
        return {'active': dict(self._active) if self._active else None,
                'waiting': [dict(entry) for entry in self._waiting]}
