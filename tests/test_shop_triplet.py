"""Offline operator tests; fake flag transport and captures are not live evidence."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from autotriager_shop.capture import CaptureError
from scripts import run_shop_triplet as triplet


@pytest.fixture
def tmp_path():
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    path = owner / uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        if not path.resolve().is_relative_to(owner):
            raise RuntimeError("test cleanup escaped its intended directory")
        shutil.rmtree(path)


def flags():
    return {"flags": {
        "paymentFailure": {"defaultVariant": "off", "state": "ENABLED", "description": "charge failures",
                           "variants": {"off": 0, "100%": 1}, "metadata": {"preserve": [1, 2]}},
        "adFailure": {"defaultVariant": "off", "state": "ENABLED", "variants": {"off": False, "on": True}},
        "other": {"targeting": {"if": [{"==": [{"var": "product_id"}, "value"]}, "off", "off"]}},
    }}


class OperatorShop:
    def __init__(self):
        self.state = flags()
        self.writes = []
        self.captures = []
        self.fail_phase = None
        self.interrupt_phase = None
        self.drift_phase = None
        self.restore_write_error = False
        self.ambiguous_write = False
        self.delay_write = False
        self.pending = None
        self.pending_reads = 0

    def get(self, url):
        assert url == "http://localhost:8080/feature/api/read"
        old = copy.deepcopy(self.state)
        if self.pending is not None:
            if self.pending_reads:
                self.state = self.pending
                self.pending = None
                return copy.deepcopy(self.state)
            self.pending_reads += 1
        return old

    def post(self, url, body):
        assert url == "http://localhost:8080/feature/api/write"
        assert set(body) == {"data"} and isinstance(body["data"], dict)
        self.writes.append(copy.deepcopy(body))
        target = body["data"]["flags"]["paymentFailure"]["defaultVariant"]
        if self.restore_write_error and target == "off":
            raise OSError("simulated restoration transport failure")
        if self.delay_write:
            self.pending = copy.deepcopy(body["data"])
            self.pending_reads = 0
        else:
            self.state = copy.deepcopy(body["data"])
        if self.ambiguous_write and target == "100%":
            raise OSError("write applied but response timed out")
        return {}

    def capture(self, config):
        expected = "100%" if config.phase == "fault" else "off"
        assert self.state["flags"]["paymentFailure"]["defaultVariant"] == expected
        assert (config.warmup_seconds, config.duration_seconds, config.settle_seconds) == (180, 180, 75)
        self.captures.append(config)
        if self.interrupt_phase == config.phase:
            raise KeyboardInterrupt()
        if self.drift_phase == config.phase:
            self.state["flags"]["adFailure"]["defaultVariant"] = "on"
            raise CaptureError("flag configuration changed during capture")
        if self.fail_phase == config.phase:
            raise CaptureError("fault path lacks required payment ERROR span")
        destination = config.public_root / config.case_id
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "incident.json").write_text(json.dumps({"case_id": config.case_id}), encoding="utf-8")
        (destination / "observations.json").write_text(json.dumps({"observations": []}), encoding="utf-8")
        manifest = config.private_root / f"{config.case_id}.json"
        manifest.write_text(json.dumps({"phase": config.phase, "expected_variant": expected}), encoding="utf-8")
        return destination, manifest


def run(shop, root, **kwargs):
    return triplet.run_triplet("neutral-001", scheduler_stopped=True, repo_root=root,
                              get_json=shop.get, post_json=shop.post, capture=shop.capture,
                              sleep=lambda seconds: None, **kwargs)


def receipt(root):
    path = root / "evaluation" / "private" / "triplet-neutral-001" / "triplet.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_order_timing_baseline_label_isolation_and_flags_preserved(tmp_path):
    shop = OperatorShop()
    original = copy.deepcopy(shop.state)
    out = run(shop, tmp_path)
    assert [c.case_id for c in shop.captures] == ["neutral-001-a", "neutral-001-b", "neutral-001-c"]
    assert [c.phase for c in shop.captures] == ["normal", "fault", "recovery"]
    assert shop.captures[0].baseline_case is None
    assert all(c.baseline_case == tmp_path / "cases" / "neutral-001-a" for c in shop.captures[1:])
    assert [body["data"]["flags"]["paymentFailure"]["defaultVariant"] for body in shop.writes] == ["100%", "off"]
    for body in shop.writes:
        assert triplet._without_variant(body["data"]) == triplet._without_variant(original)
    assert shop.state == original
    saved = receipt(tmp_path)
    assert saved["status"] == "complete" and saved["accepted_captures"] == 3
    assert saved["attempted_phases"] == 3
    assert saved["restoration"]["status"] == "verified"
    assert saved["restoration"]["other_flags_unchanged"]
    assert len(list(out.glob("*.attempt.json"))) == 3
    for case in (tmp_path / "cases").iterdir():
        for file in case.iterdir():
            public = file.read_text(encoding="utf-8")
            assert "expected_variant" not in public and "paymentFailure" not in public
            assert all(phase not in public for phase in ("normal", "fault", "recovery"))


def test_initial_on_refuses_without_mutation_or_capture(tmp_path):
    shop = OperatorShop()
    shop.state["flags"]["paymentFailure"]["defaultVariant"] = "100%"
    with pytest.raises(triplet.TripletError, match="Starting paymentFailure"):
        run(shop, tmp_path)
    assert not shop.writes and not shop.captures
    saved = receipt(tmp_path)
    assert saved["status"] == "failed" and saved["attempted_phases"] == 0
    assert all(r["status"] == "not_attempted" for r in saved["phases"])
    assert saved["restoration"]["status"] == "not_required"
    assert shop.state["flags"]["paymentFailure"]["defaultVariant"] == "100%"


def test_fault_failure_restores_off_without_recapture_or_recovery(tmp_path):
    shop = OperatorShop()
    shop.fail_phase = "fault"
    with pytest.raises(triplet.TripletError, match="required payment ERROR"):
        run(shop, tmp_path)
    assert [c.phase for c in shop.captures] == ["normal", "fault"]
    assert shop.state == flags()
    saved = receipt(tmp_path)
    assert saved["status"] == "failed" and saved["accepted_captures"] == 1
    assert saved["restoration"]["status"] == "verified"
    assert [r["status"] for r in saved["phases"]] == ["accepted", "failed", "not_attempted"]
    assert "required payment ERROR" in saved["phases"][1]["error"]["message"]
    assert not (tmp_path / "cases" / "neutral-001-b").exists()
    assert not (tmp_path / "evaluation" / "private" / "neutral-001-b.json").exists()


def test_interrupt_during_fault_preserves_failure_and_restores(tmp_path):
    shop = OperatorShop()
    shop.interrupt_phase = "fault"
    with pytest.raises(KeyboardInterrupt):
        run(shop, tmp_path)
    assert shop.state == flags()
    saved = receipt(tmp_path)
    assert saved["status"] == "failed"
    assert saved["phases"][1]["status"] == "interrupted"
    assert saved["restoration"]["status"] == "verified"


def test_ambiguous_fault_write_still_restores_and_never_starts_fault_capture(tmp_path):
    shop = OperatorShop()
    shop.ambiguous_write = True
    with pytest.raises(triplet.TripletError, match="write applied but response timed out"):
        run(shop, tmp_path)
    assert [c.phase for c in shop.captures] == ["normal"]
    assert shop.state == flags()
    assert receipt(tmp_path)["restoration"]["status"] == "verified"


def test_other_flag_drift_is_not_overwritten_and_cleanup_failure_visible(tmp_path):
    shop = OperatorShop()
    shop.drift_phase = "fault"
    with pytest.raises(triplet.TripletError, match="flag configuration changed"):
        run(shop, tmp_path)
    assert shop.state["flags"]["paymentFailure"]["defaultVariant"] == "off"
    assert shop.state["flags"]["adFailure"]["defaultVariant"] == "on"
    saved = receipt(tmp_path)
    assert saved["status"] == "failed"
    assert saved["restoration"]["status"] == "failed"
    assert saved["restoration"]["payment_restored"] is True
    assert saved["restoration"]["other_flags_unchanged"] is False
    assert saved["error"]["message"] == "flag configuration changed during capture"


def test_restoration_transport_failure_never_reports_complete(tmp_path, capsys):
    shop = OperatorShop()
    shop.fail_phase = "fault"
    shop.restore_write_error = True
    with pytest.raises(triplet.TripletError):
        run(shop, tmp_path)
    saved = receipt(tmp_path)
    assert saved["status"] == "failed"
    assert saved["restoration"]["status"] == "failed"
    assert saved["restoration"]["payment_restored"] is False
    assert "required payment ERROR" in saved["error"]["message"]
    assert "restoration transport failure" in saved["restoration"]["error"]["message"]
    assert "RESTORATION NOT VERIFIED" in capsys.readouterr().err


def test_delayed_write_ack_requires_readback_before_capture(tmp_path):
    shop = OperatorShop()
    shop.delay_write = True
    run(shop, tmp_path)
    assert len(shop.captures) == 3 and shop.state == flags()


def test_ack_without_applied_flag_never_starts_fault_capture(tmp_path):
    shop = OperatorShop()
    writes = []
    polls = []

    def ignored_post(url, body):
        writes.append(copy.deepcopy(body))
        return {}

    with pytest.raises(triplet.TripletError, match="21 readback polls"):
        triplet.run_triplet("neutral-001", scheduler_stopped=True, repo_root=tmp_path,
                            get_json=shop.get, post_json=ignored_post, capture=shop.capture,
                            sleep=lambda seconds: polls.append(seconds))
    assert [c.phase for c in shop.captures] == ["normal"]
    assert len(writes) == 1 and polls == [0.5] * 20
    assert receipt(tmp_path)["restoration"]["status"] == "verified"
    assert receipt(tmp_path)["accepted_captures"] == 1


def test_closed_stdout_does_not_prevent_fault_cleanup(tmp_path, monkeypatch):
    shop = OperatorShop()
    shop.fail_phase = "fault"

    def closed_print(*args, **kwargs):
        raise BrokenPipeError("simulated closed stdout")

    monkeypatch.setattr("builtins.print", closed_print)
    with pytest.raises(triplet.TripletError, match="required payment ERROR"):
        run(shop, tmp_path)
    assert shop.state == flags()
    assert receipt(tmp_path)["restoration"]["status"] == "verified"


def test_all_captures_accepted_but_final_flag_read_failure_is_not_complete(tmp_path):
    shop = OperatorShop()
    normal_get = shop.get
    final_reads = 0

    def cleanup_failure(url):
        nonlocal final_reads
        if len(shop.captures) == 3:
            final_reads += 1
            if final_reads >= 2:
                raise OSError("cleanup endpoint unavailable")
        return normal_get(url)

    with pytest.raises(triplet.TripletError, match="restoration was not verified"):
        triplet.run_triplet("neutral-001", scheduler_stopped=True, repo_root=tmp_path,
                            get_json=cleanup_failure, post_json=shop.post, capture=shop.capture,
                            sleep=lambda seconds: None)
    saved = receipt(tmp_path)
    assert saved["accepted_captures"] == 3 and saved["all_captures_accepted"] is True
    assert saved["status"] == "failed" and saved["restoration"]["status"] == "failed"
    assert saved["error"] is None
    assert "cleanup endpoint unavailable" in saved["restoration"]["error"]["message"]


@pytest.mark.parametrize("collision", ["public", "manifest", "receipt", "directory"])
def test_collision_any_phase_refuses_before_intervention(tmp_path, collision):
    private = tmp_path / "evaluation" / "private"
    private.mkdir(parents=True)
    if collision == "public":
        (tmp_path / "cases" / "neutral-001-c").mkdir(parents=True)
    elif collision == "manifest":
        (private / "neutral-001-b.json").write_text("existing private record", encoding="utf-8")
    elif collision == "receipt":
        (private / "triplet-neutral-001.json").write_text("existing rejected attempt", encoding="utf-8")
    else:
        (private / "triplet-neutral-001").mkdir()
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    shop = OperatorShop()
    with pytest.raises(FileExistsError):
        run(shop, tmp_path)
    assert not shop.writes and not shop.captures
    after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_failed_prefix_cannot_be_replaced_with_custom_metadata_dir(tmp_path):
    shop = OperatorShop()
    shop.fail_phase = "normal"
    with pytest.raises(triplet.TripletError):
        run(shop, tmp_path)
    with pytest.raises(FileExistsError):
        run(shop, tmp_path, output_dir=tmp_path / "evaluation" / "private" / "alternate")
    assert len(shop.captures) == 1


@pytest.mark.parametrize("kwargs", [{"scheduler_stopped": False}, {"shop_url": "https://example.org"},
                                    {"shop_url": "http://user:secret@localhost:8080"}])
def test_operator_confirmation_and_local_origin_required(tmp_path, kwargs):
    args = {"scheduler_stopped": True, "repo_root": tmp_path}
    args.update(kwargs)
    with pytest.raises(CaptureError):
        triplet.run_triplet("neutral-001", **args)
    assert not (tmp_path / "evaluation").exists()


def test_post_transport_uses_full_object_wrapper_and_timeout(monkeypatch):
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def fake_open(request, timeout):
        sent.update(url=request.full_url, method=request.method, body=json.loads(request.data), timeout=timeout,
                    content_type=request.get_header("Content-type"))
        return Reply()

    monkeypatch.setattr(triplet, "urlopen", fake_open)
    body = {"data": flags()}
    assert triplet._post_json("http://localhost:8080/feature/api/write", body) == {}
    assert sent == {"url": "http://localhost:8080/feature/api/write", "method": "POST", "body": body,
                    "timeout": 15, "content_type": "application/json"}
