"""Build the bounded incident GraphRAG knowledge corpus without model calls.

Texts are reviewed paraphrases, not an automatic code-to-rule extractor. Local
provenance is verified against a fixed upstream commit before any output writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "simulator" / "opentelemetry-demo-3.1.0"
PIN = "dedc0178918e260823323b8d95005a8cb924b007"
REVIEW_DATE = "2026-10-13"
CORPUS_ID = "autotriager-incident-rag-v1"
OTEL = "https://opentelemetry.io/docs/specs/"
WEB_SOURCES = {
    "service": (OTEL + "semconv/resource/service/", "semantic-conventions 1.44.0; reviewed 2026-10-13"),
    "trace": (OTEL + "otel/trace/api/", "OpenTelemetry specification 1.61.0; reviewed 2026-10-13"),
    "rpc": (OTEL + "semconv/rpc/rpc-spans/", "semantic-conventions 1.44.0; RPC release candidate; reviewed 2026-10-13"),
    "logs": (OTEL + "otel/logs/data-model/", "OpenTelemetry specification 1.61.0; reviewed 2026-10-13"),
    "errors": (OTEL + "semconv/general/recording-errors/", "semantic-conventions 1.44.0; development guidance; reviewed 2026-10-13"),
    "provenance": ("https://www.w3.org/TR/2013/REC-prov-o-20130430/", "W3C recommendation 2013-04-30; reviewed 2026-10-13"),
}


def general(id_: str, title: str, text: str, source: str, section: str,
            caution: str) -> dict:
    url, version = WEB_SOURCES[source]
    return dict(id=id_, title=title, text=text, source_url=url,
                source_section=section, source_version=version,
                kind="general_rule", services=[], operations=[], entity_ids=[],
                scope="Telemetry interpretation across authorized services; apply the producer's actual convention version",
                rule_status="documented", text_kind="paraphrase",
                application_limit=caution, reviewed_on=REVIEW_DATE)


def platform(id_: str, title: str, text: str, path: str, start: int,
             end: int, services: list[str], operations: list[str], anchors: list[str],
             entity_ids: list[str] | None = None) -> dict:
    return dict(id=id_, title=title, text=text,
                source_url=f"https://github.com/open-telemetry/opentelemetry-demo/blob/{PIN}/{path}#L{start}-L{end}",
                source_path=path, line_start=start, line_end=end,
                source_version=PIN, kind="platform_context", services=services,
                operations=operations, entity_ids=entity_ids or [],
                scope="Official Shop source at the pinned commit; deployed-version equality and execution require incident evidence",
                rule_status="source_supported", text_kind="paraphrase",
                application_limit="Static source context is not proof that this path executed or caused a particular incident.",
                reviewed_on=REVIEW_DATE, _anchors=anchors)


def definitions() -> list[dict]:
    checkout = "src/checkout/main.go"
    proto = "pb/demo.proto"
    return [
        general("rule-service-identity", "Logical service and instance identity",
                "service.name identifies a logical service; service.namespace disambiguates groups. service.instance.id distinguishes its running instances. Several replicas may share one service.name.",
                "service", "Service, Service Instance, Service Namespace",
                "Do not merge different namespaces or infer that two records came from the same replica from service.name alone."),
        general("rule-service-version", "Service version is a separate attribute",
                "service.version describes the component version, and its format is not standardized. The logical service name alone does not identify the version.",
                "service", "Service attributes: service.version",
                "A source commit and a telemetry service-name match do not establish deployed-source equality."),
        general("rule-span-direction", "Client, server, and internal spans",
                "CLIENT spans describe outgoing requests; SERVER spans describe incoming request handling. INTERNAL spans describe work inside an application. Context propagation commonly makes a remote SERVER span a child of a CLIENT span; nested CLIENT spans are also possible.",
                "trace", "SpanKind",
                "Separate the emitting service from the service being called. Span kinds describe execution roles, not fault responsibility."),
        general("rule-trace-identity", "Trace context and parent linkage",
                "A span has its own SpanContext, a possible parent, timing, attributes, links, and status. SpanContext carries TraceId and SpanId. Links can connect spans across traces, separately from the parent relationship.",
                "trace", "SpanContext, Span, Link",
                "Build parent edges from preserved IDs within a trace; a call chain is not a causal attribution chain."),
        general("rule-span-status", "Error and unset span status",
                "Unset is the default span status. Error records an error in the operation; Ok records validated successful completion. Non-recording spans discard added data, and recording alone does not guarantee export to the backend.",
                "trace", "Set Status; IsRecording",
                "An ERROR span does not identify an initiating cause. Missing spans or attributes do not prove that the operation did not happen."),
        general("rule-rpc-context", "RPC method, outcome, and convention version",
                "RPC spans describe remote calls with method and outcome information. Client-side duration can include retries. The current conventions distinguish errors occurring before a response from returned error status codes and document migration behavior for older instrumentation.",
                "rpc", "RPC client span; migration notice; error.type",
                "Interpret original field names under their producer's convention version; do not assume a timeout proves a server-side code failure."),
        general("rule-log-correlation", "Log timestamps and optional trace fields",
                "Timestamp records when an event occurred; ObservedTimestamp records when collection observed it. TraceId and SpanId are optional correlation fields. Resource identifies the source entity; Body and Attributes carry event content.",
                "logs", "Log and Event Record Definition; Trace Context Fields",
                "Keep event time distinct from collection time. Similar wording or nearby timestamps alone do not establish a shared request."),
        general("rule-error-context", "Error classification depends on the operation",
                "An error code needs operation context: even HTTP 404 may be expected when checking existence. Current guidance says handled or retried errors should not mark an overall operation as failed when it completes gracefully.",
                "errors", "What constitutes an error",
                "This development guidance is interpretation context, not a guarantee that historical instrumentation complied with it."),
        general("rule-provenance", "A derived claim needs a source trail",
                "PROV-O distinguishes entities, activities, and agents. Derivation connects an entity to material used to construct it; qualified derivation can describe the producing activity in more detail.",
                "provenance", "3.1 Starting Point Terms; 4.3 Qualified Terms",
                "AutoTriager uses these ideas for traceable evidence. A citation proves source identity only after resolution; it does not by itself prove that a claim is supported."),
        platform("shop-frontend-checkout-entry", "Checkout HTTP entry and order request",
                 "The frontend accepts POST /api/checkout and delegates order placement to CheckoutGateway.placeOrder. Other HTTP methods receive 405. On success it enriches returned order items with product details before replying.",
                 "src/frontend/pages/api/checkout.ts", 20, 74,
                 ["frontend", "checkout", "product-catalog"], ["POST /api/checkout", "oteldemo.CheckoutService/PlaceOrder"],
                 ["case 'POST'", "CheckoutGateway.placeOrder", "res.status(405)"], ["op-api-checkout", "op-place"]),
        platform("shop-frontend-error-mapping", "Frontend classification of checkout errors",
                 "A failed PlaceOrder marks the frontend span ERROR. Its response mapping treats a charge-failure prefix without Unavailable or Internal as HTTP 422; other caught order-placement failures become HTTP 500. This is message-based classification, not independent cause verification.",
                 "src/frontend/pages/api/checkout.ts", 14, 47,
                 ["frontend", "checkout"], ["POST /api/checkout", "oteldemo.CheckoutService/PlaceOrder"],
                 ["PAYMENT_FAILURE_PREFIX", "SpanStatusCode.ERROR", "res.status(422)", "res.status(500)"], ["op-api-checkout", "op-place"]),
        platform("shop-frontend-checkout-address", "Frontend checkout RPC destination",
                 "CheckoutGateway constructs a CheckoutServiceClient from CHECKOUT_ADDR. It resolves the PlaceOrder promise on a successful callback and rejects it on an RPC error. The effective deployment address must be obtained separately.",
                 "src/frontend/gateways/rpc/Checkout.gateway.ts", 7, 16,
                 ["frontend", "checkout"], ["oteldemo.CheckoutService/PlaceOrder"],
                 ["CHECKOUT_ADDR", "client.placeOrder"], ["op-place"]),
        platform("shop-checkout-addresses", "Checkout downstream address configuration",
                 "Checkout initializes shipping, catalog, cart, currency, email, and payment clients from environment addresses. Kafka setup is conditional on a nonempty KAFKA_ADDR.",
                 checkout, 218, 255, ["checkout", "shipping", "product-catalog", "cart", "currency", "email", "payment", "kafka"],
                 ["oteldemo.CheckoutService/PlaceOrder"], ["SHIPPING_ADDR", "PAYMENT_ADDR", "KAFKA_ADDR"], ["op-place"]),
        platform("shop-checkout-prepare", "Preparation dependencies before charging",
                 "Preparation gets the cart, prepares item prices, obtains a shipping quote, and converts shipping cost. An error at any stage returns early.",
                 checkout, 433, 457, ["checkout", "cart", "product-catalog", "shipping", "currency"],
                 ["oteldemo.CheckoutService/PlaceOrder", "oteldemo.CartService/GetCart"],
                 ["cs.getUserCart", "cs.prepOrderItems", "cs.quoteShipping", "cs.convertCurrency"], ["op-place"]),
        platform("shop-checkout-charge", "Checkout invokes the charge RPC",
                 "The charge call sends amount and credit-card information to PaymentService.Charge. RPC errors return to the caller; successful replies expose a transaction identifier.",
                 checkout, 581, 588, ["checkout", "payment"], ["oteldemo.PaymentService/Charge", "oteldemo.CheckoutService/PlaceOrder"],
                 ["paymentService.Charge", "Amount:", "CreditCard:", "GetTransactionId"], ["op-place", "op-charge"]),
        platform("shop-checkout-order-sequence", "Charge precedes shipment",
                 "PlaceOrder prepares the order, charges the card, then ships it. Charge errors return Internal; shipment errors return Unavailable.",
                 checkout, 344, 377, ["checkout", "payment", "shipping"], ["oteldemo.CheckoutService/PlaceOrder", "oteldemo.PaymentService/Charge", "POST /ship-order"],
                 ["cs.chargeCard", "cs.shipOrder", "codes.Internal", "codes.Unavailable"], ["op-place", "op-charge"]),
        platform("shop-checkout-email-handling", "Confirmation failure has different handling",
                 "A confirmation-email error produces a warning rather than an immediate failed order response. Postprocessing is conditional on a configured Kafka address.",
                 checkout, 411, 424, ["checkout", "email", "kafka"], ["oteldemo.CheckoutService/PlaceOrder", "POST /send_order_confirmation"],
                 ["logger.Warn", "cs.kafkaBrokerSvcAddr", "return resp, nil"], ["op-place"]),
        platform("shop-shipping-quote-contract", "Shipping quote response contract",
                 "Checkout posts JSON to /get-quote, expects HTTP 200, parses JSON, and rejects a missing cost_usd value.",
                 checkout, 485, 524, ["checkout", "shipping"], ["POST /get-quote"],
                 ['"POST"', '"/get-quote"', "http.StatusOK", "quoteResp.CostUsd == nil"]),
        platform("shop-item-price-currency", "Item lookup and currency conversion",
                 "For each cart item, checkout retrieves the product and converts its USD price to the requested currency. Lookup or conversion errors abort preparation.",
                 checkout, 542, 570, ["checkout", "product-catalog", "currency"], ["oteldemo.ProductCatalogService/GetProduct", "oteldemo.CurrencyService/Convert"],
                 ["GetProduct", "cs.convertCurrency", "cs.currencySvcClient.Convert"], ["op-get-prod"]),
        platform("shop-payment-handler", "Payment handler records and returns failures",
                 "The PaymentService handler calls the charge implementation. If it throws, the handler logs the error, marks its active span ERROR, sets error.type, and returns the error through the RPC callback.",
                 "src/payment/index.js", 12, 31, ["payment"], ["oteldemo.PaymentService/Charge"],
                 ["charge.charge", "SpanStatusCode.ERROR", "ATTR_ERROR_TYPE", "callback(err)"], ["op-charge"]),
        platform("shop-money-contract", "Money representation and cross-field constraints",
                 "Money carries a currency code, integer units, and nanos in billionths of a unit. Nanos is bounded from -999999999 to 999999999. Positive units require nonnegative nanos; negative units require nonpositive nanos; zero units allow either sign.",
                 proto, 145, 160, ["payment", "currency", "checkout", "product-catalog"], ["oteldemo.PaymentService/Charge", "oteldemo.CurrencyService/Convert"],
                 ["message Money", "currency_code", "int64 units", "int32 nanos"], ["op-charge"]),
        platform("shop-payment-interface", "Payment RPC request and response",
                 "The declared PaymentService interface exposes Charge. Its request combines Money and CreditCardInfo; its response supplies a transaction_id. This interface describes message shape, without proving any request succeeded.",
                 proto, 175, 195, ["payment", "checkout"], ["oteldemo.PaymentService/Charge"],
                 ["service PaymentService", "rpc Charge", "message ChargeRequest", "transaction_id"], ["op-charge"]),
        platform("shop-platform-interface-catalog", "Additional declared RPC interfaces",
                 "The protocol file declares CartService AddItem/GetCart/EmptyCart, ProductCatalogService ListProducts/GetProduct/SearchProducts, and CurrencyService GetSupportedCurrencies/Convert. These signatures support interface lookup; a declaration alone does not establish a deployed or exercised dependency.",
                 proto, 21, 143, ["cart", "product-catalog", "currency"],
                 ["oteldemo.CartService/AddItem", "oteldemo.CartService/GetCart", "oteldemo.CartService/EmptyCart", "oteldemo.ProductCatalogService/ListProducts", "oteldemo.ProductCatalogService/GetProduct", "oteldemo.ProductCatalogService/SearchProducts", "oteldemo.CurrencyService/GetSupportedCurrencies", "oteldemo.CurrencyService/Convert"],
                 ["service CartService", "service ProductCatalogService", "service CurrencyService"], ["op-list-prod", "op-get-prod"]),
    ]


def _canonical(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def build_corpus(source_root: Path = DEFAULT_SOURCE) -> dict:
    source_root = source_root.resolve()
    actual_pin = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    if actual_pin != PIN:
        raise ValueError(f"Shop source HEAD differs from required pin: {actual_pin}")
    chunks = definitions()
    sources: dict[str, bytes] = {}
    for chunk in chunks:
        if chunk["kind"] != "platform_context":
            continue
        rel = chunk["source_path"]
        path = (source_root / rel).resolve()
        if source_root not in path.parents:
            raise ValueError("Source path escapes pinned checkout")
        if rel not in sources:
            expected = _canonical(subprocess.check_output(["git", "-C", str(source_root), "show", f"{PIN}:{rel}"]))
            actual = _canonical(path.read_bytes())
            if actual != expected:
                raise ValueError(f"Source contents differ from pin: {rel}")
            sources[rel] = actual
        content = sources[rel]
        lines = content.decode("utf-8").splitlines()
        start, end = chunk["line_start"], chunk["line_end"]
        if not (1 <= start <= end <= len(lines)):
            raise ValueError(f"Invalid source line range: {chunk['id']}")
        selected = "\n".join(lines[start - 1:end])
        for anchor in chunk.pop("_anchors"):
            if anchor not in selected:
                raise ValueError(f"Missing source anchor in {chunk['id']}: {anchor}")
        chunk["source_sha256"] = hashlib.sha256(content).hexdigest()
        chunk["source_slice_sha256"] = hashlib.sha256(selected.encode("utf-8")).hexdigest()
        chunk["hash_encoding"] = "UTF-8; CRLF normalized to LF; slice has no trailing newline"
    for chunk in chunks:
        chunk["text_sha256"] = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
    corpus = {
        "schema_version": "1.0", "corpus_id": CORPUS_ID, "source_pin": PIN,
        "reviewed_on": REVIEW_DATE,
        "purpose": "Retrieve telemetry interpretation and bounded platform contracts for AutoTriager incident investigations.",
        "boundaries": [
            "Knowledge context is not a root-cause label or an executable causal rule.",
            "Current incident observations stay separate and retain incident/time scope.",
            "No credentials, intervention settings, benchmark answers, or future recovery outcomes are ingested.",
            "Static source matching does not prove the deployed version or observed execution.",
            "Web sources were manually checked on reviewed_on; rebuilding does not revalidate their latest content.",
        ],
        "chunks": chunks,
    }
    validate(corpus)
    return corpus


def validate(corpus: dict) -> None:
    required = {"id", "title", "text", "source_url", "source_version", "kind", "services", "operations", "scope", "rule_status", "text_kind", "text_sha256"}
    ids: set[str] = set()
    for chunk in corpus["chunks"]:
        if required - chunk.keys():
            raise ValueError(f"Missing fields: {required - chunk.keys()}")
        if chunk["id"] in ids:
            raise ValueError(f"Duplicate chunk: {chunk['id']}")
        ids.add(chunk["id"])
        if chunk["kind"] not in {"general_rule", "platform_context"}:
            raise ValueError("Unknown knowledge kind")
        if chunk["rule_status"] not in {"documented", "source_supported"}:
            raise ValueError("Knowledge is not an observed incident conclusion")
        if not chunk["source_url"].startswith("https://"):
            raise ValueError("Source URL must be HTTPS")
        if chunk["text_sha256"] != hashlib.sha256(chunk["text"].encode()).hexdigest():
            raise ValueError("Text hash mismatch")
        for field in ("services", "operations", "entity_ids"):
            if not isinstance(chunk[field], list) or not all(isinstance(x, str) for x in chunk[field]):
                raise ValueError(f"Invalid list field: {field}")
        if chunk["kind"] == "platform_context" and chunk["source_version"] != PIN:
            raise ValueError("Unpinned platform context")
        forbidden = ("paymentfailure", "paymentunreachable", "badaddress:50051", "ground_truth", "injection_label", "recovery_outcome")
        if any(token in chunk["text"].lower() for token in forbidden):
            raise ValueError("Intervention or answer material entered retrieval text")


def serialize(corpus: dict) -> bytes:
    return (json.dumps(corpus, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "kg" / "rag_corpus.json")
    args = parser.parse_args()
    corpus = build_corpus(args.source_root)
    payload = serialize(corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    manifest = {"corpus_id": CORPUS_ID, "source_pin": PIN, "chunk_count": len(corpus["chunks"]),
                "kinds": dict(Counter(c["kind"] for c in corpus["chunks"])),
                "corpus_sha256": hashlib.sha256(payload).hexdigest(),
                "verified_source_files": sorted({c["source_path"] for c in corpus["chunks"] if "source_path" in c}),
                "checks": ["pinned HEAD", "local bytes match pinned files after newline normalization", "source line anchors", "schema and IDs", "retrieval text leakage denylist"],
                "limitation": "Checks validate construction, not diagnosis accuracy, complete leakage detection, or claim entailment."}
    manifest_dir = args.output.parent / "rag_corpus"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
