"""Synthetic backend log tests; they are not real incident experiments."""
import copy
import json

import pytest

from autotriager_shop.proxy_access import ProxyAccessCollector, matching_image_records, parse_access_record

TRACE = "a" * 32
PATH = "/images/products/Telescope.jpg"
START = "2026-10-02T10:00:00Z"
END = "2026-10-02T10:02:00Z"


def hit():
    return {"_id": "synthetic-doc", "_source": {"@timestamp": "2026-10-02T10:01:00Z",
        "traceId": TRACE, "resource": {"service.name": "frontend-proxy"},
        "attributes": {"url.path": PATH, "feature_flag_key": "imageSlowLoad", "source.address": "private-ip"},
        "body": f'[2026-10-02T10:01:00Z] "GET {PATH} HTTP/1.1" 200 - via_upstream - "-" 0 1000 5010 10 "private-ip" "private-agent" "d8276e60-a358-4ab3-9b2c-2d7235a73370" "private-host"'}}


def test_only_public_route_fields_survive():
    row = parse_access_record(hit())
    assert row["raw"]["duration_ms"] == 5010
    assert row["raw"]["upstream_duration_ms"] == 10
    assert row["trace_id"] == TRACE
    serialized = json.dumps(row)
    for secret in ("imageSlowLoad", "feature_flag", "private-ip", "private-agent", "private-host", "via_upstream"):
        assert secret not in serialized


@pytest.mark.parametrize("change", ["control_path", "wrong_resource", "path_mismatch", "nonfinite", "malformed", "bad_time"])
def test_wrong_or_invalid_sources_are_not_usable(change):
    value = hit()
    if change == "control_path": value["_source"]["attributes"]["url.path"] = "/feature/api/read"
    if change == "wrong_resource": value["_source"]["resource"]["service.name"] = "flagd"
    if change == "path_mismatch": value["_source"]["attributes"]["url.path"] = "/images/products/Other.jpg"
    if change == "nonfinite": value["_source"]["body"] = value["_source"]["body"].replace("5010", "nan")
    if change == "malformed": value["_source"]["body"] = 'broken "log'
    if change == "bad_time": value["_source"]["@timestamp"] = "unverified"
    assert parse_access_record(value) is None


def test_shared_time_or_path_does_not_link_another_trace():
    row = parse_access_record(hit())
    assert matching_image_records([row], {"image_path": PATH, "trace_id": TRACE}) == [row]
    assert matching_image_records([row], {"image_path": PATH, "trace_id": "b" * 32}) == []
    assert matching_image_records([row], {"image_path": "/images/products/Other.jpg", "trace_id": TRACE}) == []


def test_pinned_proxy_rewrite_retains_original_image_identity():
    value = hit()
    value["_source"]["attributes"]["url.path"] = PATH.removeprefix("/images")
    row = parse_access_record(value)
    assert row["raw"]["path"] == PATH
    assert row["trace_id"] == TRACE


def test_scoped_search_is_get_only_and_filters_records():
    urls = []
    def read(url):
        urls.append(url)
        other = copy.deepcopy(hit()); other["_source"]["traceId"] = "b" * 32
        return {"hits": {"hits": [hit(), other]}}
    result = ProxyAccessCollector(get_json=read)({"image_path": PATH, "trace_id": TRACE}, start_time=START, end_time=END)
    assert len(result["records"]) == 1 and result["status"] == "observed"
    assert urls[0].startswith("http://127.0.0.1:32772/otel-logs-*/_search?")
    assert "/feature" not in urls[0]


def test_partial_or_error_search_never_invents_logs():
    for response in ({"timed_out": True}, {"_shards": {"failed": 1}}, {}):
        result = ProxyAccessCollector(get_json=lambda url: response)({"image_path": PATH, "trace_id": TRACE}, start_time=START, end_time=END)
        assert result["records"] == [] and result["status"] == "error"
