"""OS-backed lease for the dedicated Douyin tab, shared by API and crawler.

Hold the lease for a complete operation (including pagination and cleanup).
The lock file is deliberately never deleted: replacing it would break flock.
"""

import asyncio
import errno
import os
from contextvars import ContextVar
from pathlib import Path


class DouyinBrowserBusyError(RuntimeError):
    error_code = "browser_busy"


class CollectionStoppedError(RuntimeError):
    error_code = "user_stop"


_current_lease = ContextVar("douyin_tab_lease", default=None)


class DouyinTabLease:
    def __init__(self, path=None, timeout=30, should_stop=None, on_wait=None):
        self.path = Path(path) if path else Path(__file__).resolve().parents[1] / "browser_data" / "douyin-tab.lock"
        self.timeout = timeout
        self.should_stop = should_stop or (lambda: False)
        self.on_wait = on_wait
        self._file = None
        self._token = None
        self.active = False
        self._borrowed = False

    def _try_lock(self):
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            return False

    async def __aenter__(self):
        if self.should_stop():
            raise CollectionStoppedError("已请求停止")
        parent = _current_lease.get()
        if parent and parent.active and parent.path.resolve() == self.path.resolve():
            self._borrowed = True
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        # Windows byte-range locks require at least one byte in the file.
        if self.path.stat().st_size == 0:
            self._file.write(b"\0")
            self._file.flush()
        deadline = asyncio.get_running_loop().time() + self.timeout
        notified = False
        try:
            while not self._try_lock():
                if not notified and self.on_wait:
                    self.on_wait()
                    notified = True
                if self.should_stop():
                    raise CollectionStoppedError("等待页签期间已停止")
                if asyncio.get_running_loop().time() >= deadline:
                    raise DouyinBrowserBusyError("抖音页签正在被其他任务使用，请稍后重试")
                await asyncio.sleep(0.1)
            self.active = True
            self._token = _current_lease.set(self)
            return self
        except BaseException:
            self._file.close()
            self._file = None
            raise

    async def __aexit__(self, *args):
        if self._borrowed or not self._file:
            return
        self.active = False
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
            _current_lease.reset(self._token)
