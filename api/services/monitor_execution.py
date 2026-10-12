"""In-memory operation state; the database remains the source of task truth."""

import time
import uuid


class MonitorExecution:
    def __init__(self, kind):
        self.run_id = uuid.uuid4().hex
        self.kind = kind
        self.state = "running"
        self.phase = "connecting"
        self.account_name = ""
        self.current_post = ""
        self.started_at = time.time()
        self.updated_at = self.started_at
        self.finished_at = None
        self.pages = 0
        self.scanned = 0
        self.saved = 0
        self.total = None
        self.processed = 0
        self.completed = 0
        self.retried = 0
        self.failed = 0
        self.skipped = 0
        self.error = None
        self.stop_requested = False
        self.result = None

    @property
    def active(self):
        return self.finished_at is None

    def update(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.updated_at = time.time()

    def snapshot(self):
        return {**vars(self), "active": self.active, "elapsed_seconds": int((self.finished_at or time.time()) - self.started_at)}
