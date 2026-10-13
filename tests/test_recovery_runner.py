"""Bounded automatic verification contract, not runtime-resolution experiments."""
from autotriager_shop.recovery_runner import RecoveryRunner


class Clock:
    def __init__(self):
        self.seconds = 0
        self.waits = []
    def __call__(self):
        return self.seconds
    def wait(self, seconds):
        self.waits.append(seconds)
        self.seconds += seconds
        return False


def runner():
    value = RecoveryRunner()
    value._status = {"state": "not_started", "checks": 0}
    return value


def test_three_distinct_checks_are_scheduled_and_stop_on_actual_resolved_state():
    value, clock, calls = runner(), Clock(), []
    def check():
        calls.append(clock.seconds)
        return {"incident": {"state": "resolved" if len(calls) == 3 else "verifying_recovery"}}
    result = value.run("a", check, lambda: {"run_id": "a", "state": "verifying_recovery"},
                       wait=clock.wait, clock=clock)
    assert calls == [125, 155, 185]
    assert result["state"] == "resolved" and result["checks"] == 3
    assert result["resolved_before_deadline"] is True


def test_six_collection_failures_never_become_success_and_details_are_sanitized():
    value, clock, calls = runner(), Clock(), []
    def failure():
        calls.append(clock.seconds)
        raise OSError("credential-shaped-secret")
    result = value.run("a", failure, lambda: {"run_id": "a", "state": "verification_failed"},
                       wait=clock.wait, clock=clock)
    assert result["state"] == "check_limit_reached_unresolved" and result["checks"] == 6
    assert calls[-1] == 275
    assert "credential-shaped-secret" not in str(result)


def test_incident_change_never_checks_a_new_incident_using_previous_authorization():
    value, clock = runner(), Clock()
    result = value.run("a", lambda: (_ for _ in ()).throw(AssertionError()),
        lambda: {"run_id": "b", "state": "verifying_recovery"}, wait=clock.wait, clock=clock)
    assert result["state"] == "incident_changed" and result["checks"] == 0


def test_slow_in_flight_recovery_is_true_recovery_but_not_success_before_deadline():
    value, clock = runner(), Clock()
    def check():
        clock.seconds = 350
        return {"incident": {"state": "resolved"}}
    result = value.run("a", check, lambda: {"run_id": "a", "state": "verifying_recovery"},
                       wait=clock.wait, clock=clock)
    assert result["state"] == "resolved_after_deadline"
    assert result["resolved_before_deadline"] is False


def test_stop_event_prevents_background_customer_requests():
    value = runner()
    value.stop()
    result = value.run("a", lambda: (_ for _ in ()).throw(AssertionError()),
                       lambda: {"run_id": "a", "state": "verifying_recovery"})
    assert result["state"] == "stopped" and result["checks"] == 0
