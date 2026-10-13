# Incident GraphRAG knowledge corpus

Author: Dahe Chen. Source review: October 13, 2026.

## Purpose and scope

The corpus supplies missing interpretation and interface knowledge to the existing AutoTriager incident investigation. It is not a separate recommendation question-answering application. The first content uses interfaces represented in the archived checkout observations and their surrounding dependencies. The content format supports additional services, but this release is not a complete platform knowledge base.

The implemented corpus contains **23 manually reviewed paraphrase chunks: 9 general interpretations and 14 platform context chunks**. No LLM extracted or validated these rules. `general_rule` means documented interpretation guidance; it does not mean a universal causal rule, executable validator, or verified explanation of an incident.

## Structure and input/output contract

`kg/rag_corpus.json` contains `schema_version`, `corpus_id`, `source_pin`, boundaries, and a `chunks` array. Every chunk includes:

- Stable ID, title, retrieval text, text hash, and content kind.
- Primary source URL and source version or dated review.
- Applicable service/operation names, optional existing graph entity IDs, scope, and application limits.
- `documented` or `source_supported` status; `text_kind=paraphrase`.
- For local platform source: relative path, exact line range, canonical source and selected-slice SHA-256 hashes.

The corpus intentionally contains no current incident observations. The retriever joins separately scoped observations to relevant chunks and graph entities. Evaluator answers stay outside that path. Resolving a chunk ID proves retrieval provenance; testing whether its text supports a particular model claim is a separate evaluation.

## Reviewed primary sources

| Source | Corpus IDs | Reason for inclusion |
| --- | --- | --- |
| [OTel service conventions](https://opentelemetry.io/docs/specs/semconv/resource/service/) | `rule-service-identity`, `rule-service-version` | Distinguish component, replica, namespace, and revision. |
| [OTel tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/) | `rule-span-direction`, `rule-trace-identity`, `rule-span-status` | Interpret execution roles, trace identity, parent/link structure, and status without manufacturing cause. |
| [OTel RPC conventions](https://opentelemetry.io/docs/specs/semconv/rpc/rpc-spans/) | `rule-rpc-context` | Preserve caller/server interpretation and convention-version caveats. |
| [OTel logs data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) | `rule-log-correlation` | Separate event time, collection time, trace linkage, and content. |
| [OTel recording errors](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/) | `rule-error-context` | Retain operation-specific status meaning. The page is development guidance. |
| [W3C PROV-O](https://www.w3.org/TR/2013/REC-prov-o-20130430/) | `rule-provenance` | Motivate a source trail for derived material; no full ontology-compliance claim. |
| [Pinned official Shop source](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007) | `shop-*` | Provide platform-specific contracts and error propagation behavior. |

OTel pages displayed specification 1.61.0 or semantic-conventions 1.44.0 when read. Their URLs are live; the recorded review is not an immutable web snapshot. Rebuilding the local corpus does not refresh or reverify those websites. Historical telemetry may use older conventions and must not be silently renamed to the newest schema.

## Pinned platform evidence

The source commit is `dedc0178918e260823323b8d95005a8cb924b007`. The following files were checked against Git objects at that commit. Every chunk records narrower line references and its own text hash.

| File | Knowledge captured |
| --- | --- |
| `src/frontend/pages/api/checkout.ts` | Request entry, response handling, and error classification. |
| `src/frontend/gateways/rpc/Checkout.gateway.ts` | Destination configuration and callback behavior. |
| `src/checkout/main.go` | Preparation stages, downstream addresses, call order, conditions, and response contracts. |
| `src/payment/index.js` | Error recording and RPC callback handling. |
| `pb/demo.proto` | Message contracts, Money field relationships, and a bounded interface catalog. |

The observed source version is not proof that archived telemetry came from an identical deployment. These chunks therefore remain `source_supported`, even when an operation name matches a span. The retriever must carry this limit into the model context.

## Construction and reproduction

```powershell
python kg/build_rag_corpus.py
python -m unittest discover -s tests -p test_rag_corpus.py -v
```

The builder is deterministic and uses the Python standard library. It checks the source checkout's HEAD, compares selected local files with pinned Git bytes after CRLF-to-LF normalization, verifies line bounds and source anchors, checks chunk identities and required metadata, and emits `kg/rag_corpus/manifest.json`. The manifest records counts, source paths, corpus hash, checks, and limits. It does not contain account credentials or runtime addresses.

The negative tests reject a wrong checkout revision, changed source content, edited retrieval text with a stale hash, and a prohibited evaluator-answer token. Additional checks preserve conditions, provenance limits, and the separation from incident records. These tests establish construction behavior; they do not establish fault-localization accuracy or complete leakage detection.

## Deliberate exclusions

- Credentials, private configuration values, intervention settings, injection labels, benchmark answer files, and post-incident recovery results.
- Scenario solution pages or test cases that reveal the experiment's intended fault.
- Unverified historical model hypotheses presented as operational facts.
- Claims that a described source path actually executed during an incident.

Only the selected paraphrases enter the knowledge store. A full-file source hash anchors identity but does not import the full file's contents. Loading complete source files later requires a fresh inclusion and leakage review.

## Next evaluation

Measure retrieval coverage and irrelevant-context rate against source-anchored questions, then evaluate claim support separately from citation-ID validity. Compare current incident-only analysis with document retrieval and graph-assisted retrieval under a fixed model, incident set, and budget. Record missing-version and incomplete-evidence outcomes instead of assuming more context improves diagnosis. No benefit measurement is claimed by this corpus build.
