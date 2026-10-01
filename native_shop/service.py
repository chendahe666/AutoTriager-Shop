"""Four real HTTP services for a controlled local incident experiment.

Each service runs in its own Python process.  The output is append-only JSON
span/log records with trace and parent-span IDs; it is not presented as an
official OpenTelemetry Demo capture.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SERVICES = ("catalog", "payment", "checkout", "frontend")
# A fixed dependency timeout in every experimental phase. The delay
# intervention changes only the payment worker's response time.
PAYMENT_TIMEOUT_SECONDS = 0.25


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_record(path: Path, record: dict, lock: threading.Lock) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def serve(service: str, config_path: Path) -> None:
    if service not in SERVICES:
        raise ValueError(f"Unknown service: {service}")
    config = _read_json(config_path)
    ports = config["ports"]
    raw_dir = Path(config["raw_dir"])
    fault_path = Path(config["fault_path"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_lock = threading.Lock()
    capacity = threading.BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AutoTriagerLocalShop/0.1"

        def log_message(self, format: str, *args: object) -> None:
            # Records go into versioned JSON files instead of stderr.
            return

        def _send(self, status: int, body: dict | str, html: bool = False) -> None:
            data = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # A caller may time out during the controlled delay experiment.
                pass

        def _call(self, target: str, route: str, trace_id: str, parent_span_id: str,
                  timeout: float = 2.0) -> tuple[int, dict]:
            request = Request(
                f"http://127.0.0.1:{ports[target]}{route}",
                headers={"X-Trace-Id": trace_id, "X-Parent-Span-Id": parent_span_id},
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                except (ValueError, UnicodeError):
                    body = {"error": str(exc)}
                return exc.code, body
            except (URLError, TimeoutError) as exc:
                return 504, {"error": f"{target} request timed out or could not connect: {exc}"}

        def do_GET(self) -> None:  # noqa: N802 - HTTP handler interface
            if self.path == "/health":
                self._send(200, {"service": service, "status": "ok"})
                return

            started_at = utc_now()
            started = time.perf_counter()
            trace_id = self.headers.get("X-Trace-Id") or uuid.uuid4().hex
            parent_span_id = self.headers.get("X-Parent-Span-Id") or None
            span_id = uuid.uuid4().hex[:16]
            status = 404
            body: dict | str = {"error": "not found"}
            html = False
            reason = ""
            mode = _read_json(fault_path).get("mode", "none")

            if service == "catalog" and self.path == "/product":
                if mode == "catalog_error":
                    status, body, reason = 500, {"error": "catalog unavailable"}, "catalog request failed"
                else:
                    status, body = 200, {"id": "moon-mug", "name": "Moon Mug", "price_cents": 1999}
            elif service == "payment" and self.path == "/charge":
                if mode == "payment_error":
                    status, body, reason = 503, {"error": "payment rejected by service"}, "payment request failed"
                elif mode == "payment_delay":
                    time.sleep(0.55)
                    status, body = 200, {"charged": True}
                elif mode == "payment_capacity":
                    if capacity.acquire(blocking=False):
                        try:
                            time.sleep(0.12)
                            status, body = 200, {"charged": True}
                        finally:
                            capacity.release()
                    else:
                        status, body, reason = 503, {"error": "payment capacity exhausted"}, "capacity exhausted"
                else:
                    status, body = 200, {"charged": True}
            elif service == "checkout" and self.path == "/checkout":
                if mode == "checkout_error":
                    status, body, reason = 500, {"error": "checkout unavailable"}, "checkout request failed"
                else:
                    catalog_status, catalog_body = self._call("catalog", "/product", trace_id, span_id)
                    if catalog_status != 200:
                        status, body, reason = 502, {"error": "catalog dependency failed", "detail": catalog_body}, "catalog dependency failed"
                    else:
                        payment_status, payment_body = self._call(
                            "payment", "/charge", trace_id, span_id,
                            timeout=PAYMENT_TIMEOUT_SECONDS,
                        )
                        if payment_status != 200:
                            status, body, reason = 502, {"error": "payment dependency failed", "detail": payment_body}, "payment dependency failed"
                        else:
                            status, body = 200, {"order": "accepted", "product": catalog_body["id"]}
            elif service == "frontend" and self.path == "/api/checkout":
                downstream_status, downstream_body = self._call("checkout", "/checkout", trace_id, span_id)
                if downstream_status != 200:
                    status, body, reason = 502, {"error": "checkout failed", "detail": downstream_body}, "checkout dependency failed"
                else:
                    status, body = 200, downstream_body
            elif service == "frontend" and self.path == "/":
                status, html = 200, True
                body = """<!doctype html><html><head><title>AutoTriager Local Shop</title>
<style>body{font:18px system-ui;max-width:700px;margin:5rem auto;padding:0 1rem;color:#222}
button{padding:.8rem 1.2rem;font-size:1rem}pre{white-space:pre-wrap;background:#f3f3f3;padding:1rem}</style>
</head><body><h1>Moon Mug</h1><p>Local four-service shopping simulation.</p>
<p><strong>$19.99</strong></p><button id="buy">Place test order</button><pre id="result"></pre>
<script>document.getElementById('buy').onclick=async()=>{const r=await fetch('/api/checkout');
document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2)}</script>
</body></html>"""

            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            _write_record(raw_dir / f"{service}.spans.ndjson", {
                "timestamp": started_at, "service.name": service, "span_id": span_id,
                "parent_span_id": parent_span_id, "trace_id": trace_id,
                "http.route": self.path, "http.response.status_code": status,
                "duration_ms": duration_ms, "span.status": "ERROR" if status >= 500 else "OK",
                "error_reason": reason,
            }, file_lock)
            if status >= 500:
                _write_record(raw_dir / f"{service}.logs.ndjson", {
                    "timestamp": utc_now(), "service.name": service,
                    "severity_text": "ERROR", "trace_id": trace_id, "span_id": span_id,
                    "body": reason or f"HTTP {status} on {self.path}",
                    "http.route": self.path, "http.response.status_code": status,
                }, file_lock)
            self._send(status, body, html)

    server = ThreadingHTTPServer(("127.0.0.1", ports[service]), Handler)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=SERVICES, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    serve(args.service, args.config)


if __name__ == "__main__":
    main()
