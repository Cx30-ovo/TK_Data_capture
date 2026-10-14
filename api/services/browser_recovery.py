"""Bounded browser recovery state, separate from user pauses and risk cooldowns."""

import math
import time


class BrowserRecovery:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.state = "healthy"
        self.pending = False
        self.attempts = 0
        self.timeouts = 0
        self.retry_at = 0.0
        self.error = None
        self.reset_page = False
        self.last_recovered_at = None

    def observe(self, failure):
        if not self.enabled:
            return False
        if failure.error_code == "network_timeout":
            self.timeouts += 1
            if self.timeouts < 3:
                return False
            self.reset_page = True
        elif failure.error_code == "tab_changed":
            self.reset_page = True
        elif failure.error_code != "browser_disconnected":
            return False
        if not self.pending:
            self.pending = True
            self.state = "waiting"
            self.retry_at = time.time() + 15
        self.error = failure.as_dict()
        return True

    def successful_request(self):
        self.timeouts = 0

    def begin(self):
        self.state = "recovering"
        self.attempts += 1

    def failed(self, failure):
        self.pending = True
        self.error = failure.as_dict()
        self.state = "waiting"
        # After five failures, back off to 15 minutes rather than launch-looping.
        delay = 900 if self.attempts >= 5 else min(15 * 2 ** max(0, self.attempts - 1), 300)
        self.retry_at = time.time() + delay
        return delay

    def recovered(self):
        self.pending = False
        self.state = "healthy"
        self.attempts = self.timeouts = 0
        self.retry_at = 0.0
        self.error = None
        self.reset_page = False
        self.last_recovered_at = time.time()

    def wait_for_login(self, failure):
        self.pending = False
        self.state = "login_required"
        self.error = failure.as_dict()

    def snapshot(self):
        return {"enabled": self.enabled, "state": self.state, "pending": self.pending,
                "attempts": self.attempts, "retry_after_seconds": max(0, math.ceil(self.retry_at - time.time())) if self.pending else 0,
                "error": self.error, "last_recovered_at": self.last_recovered_at}
