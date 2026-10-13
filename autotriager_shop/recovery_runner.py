"""Bounded customer/backend checks after an explicitly authorized local action."""
from __future__ import annotations

import copy
import threading
import time

from .closed_loop import utc_now


class RecoveryRunner:
    """No model calls or control writes; failures cannot mark an incident resolved."""
    def __init__(self):
        self.stop_event = threading.Event()
        self._status = {"state": "not_started", "checks": 0}
        self._thread = None

    def status(self) -> dict:
        return copy.deepcopy(self._status)

    def start(self, run_id, check, state) -> None:
        if self._thread and self._thread.is_alive():
            raise ValueError("A bounded recovery check is already running.")
        self.stop_event.clear()
        self._status = {"state": "waiting_for_post_action_window", "checks": 0,
                        "run_id": run_id, "started_at": utc_now(),
                        "initial_wait_seconds": 125, "interval_seconds": 30,
                        "max_checks": 6, "deadline_seconds": 300}
        self._thread = threading.Thread(target=self.run, args=(run_id, check, state), daemon=True)
        self._thread.start()

    def run(self, run_id, check, state, *, wait=None, clock=time.monotonic) -> dict:
        """Inject clocks/waits only for contract tests, never replace actual results."""
        wait = wait or self.stop_event.wait
        started = clock()
        if wait(125):
            self._status["state"] = "stopped"
            return self.status()
        for _ in range(6):
            current = state()
            if current.get("run_id") != run_id or current["state"] == "resolved":
                if current.get("run_id") != run_id:
                    self._status["state"] = "incident_changed"
                else:
                    # A manual check may resolve while the worker waits. The
                    # worker has no earlier completion receipt, so use this
                    # conservative observed time rather than claiming timeliness.
                    late = clock() - started >= 300
                    self._status.update(state="resolved_after_deadline" if late else "resolved",
                                        resolved_before_deadline=not late)
                break
            if clock() - started >= 300:
                self._status["state"] = "deadline_reached_unresolved"
                break
            step_started = clock()
            self._status["state"] = "checking_customer_and_backend"
            self._status["checks"] += 1
            try:
                checked = check()
                if checked["incident"]["state"] == "resolved":
                    late = clock() - started >= 300
                    self._status.update(state="resolved_after_deadline" if late else "resolved",
                                        resolved_before_deadline=not late)
                    break
            except Exception:
                # Do not expose transport/credential details or fabricate a pass.
                self._status["last_error"] = "Recovery collection or verification failed; incident remains unresolved."
            self._status["state"] = "waiting_for_next_check"
            if wait(max(0, 30 - (clock() - step_started))):
                self._status["state"] = "stopped"
                break
        else:
            self._status["state"] = "check_limit_reached_unresolved"
        self._status["finished_at"] = utc_now()
        return self.status()

    def stop(self) -> None:
        self.stop_event.set()
