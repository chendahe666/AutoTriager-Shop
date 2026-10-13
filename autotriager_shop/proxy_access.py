"""Read-only, field-allowlisted image-route records from local OpenSearch.

Only Envoy access records for an exact public image request are accepted.
Raw bodies include other fields and are discarded immediately after parsing;
headers, feature events, IPs, user agents and arbitrary messages are not kept.
This is a route-specific adapter, not a general log ingestion claim.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
from urllib.parse import urlencode

from .closed_loop import stamp, utc_now
from .live_snapshot import _get_json, _origin

_PATH = re.compile(r"/images/products/[A-Za-z0-9_.-]{1,150}\Z")
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_REQUEST = re.compile(r"[0-9a-f-]{32,36}\Z")


def parse_access_record(hit: dict) -> dict | None:
    """Keep only independently measured public image route fields."""
    try:
        source = hit["_source"]
        if source.get("resource", {}).get("service.name") != "frontend-proxy":
            return None
        attributes = source.get("attributes", {})
        forwarded_path = attributes.get("url.path")
        body = source.get("body")
        if not isinstance(body, str) or len(body) > 8000:
            return None
        tokens = shlex.split(body)
        method, body_path, protocol = tokens[1].split()
        # The pinned proxy rewrites /images/ to / for image-provider routing.
        # url.path is the forwarded path, while the access body deliberately
        # records X-ENVOY-ORIGINAL-PATH. Preserve the independently recorded
        # original path and verify its exact declared rewrite, never a guess.
        path = body_path
        if (method != "GET" or not _PATH.fullmatch(path)
                or forwarded_path not in {path, path.removeprefix("/images")}
                or protocol not in {"HTTP/1.0", "HTTP/1.1", "HTTP/2"}):
            return None
        status, duration = int(tokens[2]), float(tokens[9])
        upstream = None if tokens[10] == "-" else float(tokens[10])
        if (not 100 <= status <= 599 or not math.isfinite(duration) or duration < 0
                or upstream is not None and (not math.isfinite(upstream) or upstream < 0)):
            return None
        timestamp = source["@timestamp"]
        stamp(timestamp)
        trace_id = source.get("traceId", "")
        request_id = tokens[13]
        trace_id = trace_id if isinstance(trace_id, str) and _TRACE.fullmatch(trace_id) else None
        request_id = request_id if _REQUEST.fullmatch(request_id) else None
        if not trace_id and not request_id:
            return None
        source_id = hit["_id"]
        if not isinstance(source_id, str) or len(source_id) > 200:
            return None
        raw = {"method": "GET", "path": path, "http_status": status,
               "duration_ms": duration, "upstream_duration_ms": upstream,
               "request_id": request_id, "source_document_id": source_id,
               "timestamp_basis": "proxy_request_start", "filtered_fields": True}
        record = {"id": "live-proxy-" + hashlib.sha256(source_id.encode()).hexdigest()[:20],
                  "kind": "log", "service": "frontend-proxy", "timestamp": timestamp,
                  "summary": f"frontend-proxy: GET {path} — HTTP {status}, total {duration:.1f} ms",
                  "source_url": "local-opensearch:otel-logs:" + source_id,
                  "raw": raw}
        if trace_id:
            record["trace_id"] = trace_id
        return record
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def matching_image_records(observations: list[dict], receipt: dict) -> list[dict]:
    path, trace_id = receipt.get("image_path"), receipt.get("trace_id")
    if not isinstance(path, str) or not _PATH.fullmatch(path) or not isinstance(trace_id, str) or not _TRACE.fullmatch(trace_id):
        return []
    return [row for row in observations
            if row.get("kind") == "log" and row.get("service") == "frontend-proxy"
            and row.get("trace_id") == trace_id and row.get("raw", {}).get("path") == path
            and row.get("raw", {}).get("filtered_fields") is True]


class ProxyAccessCollector:
    def __init__(self, origin: str = "http://127.0.0.1:32772", *, get_json=_get_json):
        self.origin = _origin(origin, "opensearch_url")
        self.get_json = get_json

    def __call__(self, receipt: dict, *, start_time: str, end_time: str) -> dict:
        path, trace_id = receipt.get("image_path"), receipt.get("trace_id")
        if not isinstance(path, str) or not _PATH.fullmatch(path) or not isinstance(trace_id, str) or not _TRACE.fullmatch(trace_id):
            return {"records": [], "status": "unlinked", "fetched_at": utc_now()}
        query = {"size": 20, "sort": [{"@timestamp": "asc"}],
                 "_source": ["@timestamp", "traceId", "body", "attributes.url.path", "resource.service.name"],
                 "query": {"bool": {"filter": [
                     {"term": {"resource.service.name.keyword": "frontend-proxy"}},
                     {"terms": {"attributes.url.path.keyword": [path, path.removeprefix("/images")]}},
                     {"term": {"traceId.keyword": trace_id}},
                     {"range": {"@timestamp": {"gte": start_time, "lte": end_time}}}]}}}
        parameters = urlencode({"source_content_type": "application/json", "source": json.dumps(query)})
        url = self.origin + "/otel-logs-*/_search?" + parameters
        try:
            payload = self.get_json(url)
            if payload.get("timed_out") or payload.get("_shards", {}).get("failed", 0):
                raise ValueError("Partial log search")
            hits = payload["hits"]["hits"]
            if not isinstance(hits, list):
                raise ValueError("Invalid log search")
            rows = [row for hit in hits[:20] if isinstance(hit, dict) and (row := parse_access_record(hit))]
            rows = matching_image_records(rows, receipt)
            rows = [row for row in rows if stamp(start_time) <= stamp(row["timestamp"]) <= stamp(end_time)]
            for row in rows:
                row["source_url"] = url
            return {"records": rows, "status": "observed" if rows else "missing", "fetched_at": utc_now(),
                    "limit": 20, "source": "local_opensearch_proxy_access", "fields_allowlisted": True}
        except Exception:
            return {"records": [], "status": "error", "fetched_at": utc_now(),
                    "error": "Read-only scoped proxy access search failed; no log records invented."}
