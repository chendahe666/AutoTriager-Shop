# GraphRAG coursework engineering verification

Author: Dahe Chen
Verification date: October 15, 2026

## Scope and result

The requested focused suite completed once with **118 passed in 14.54 seconds**.
It covered cloud import validation, GraphRAG retrieval/output contracts,
workbench routes, immutable model-attempt accounting, and corpus rebuilding.
The in-process network guard observed **zero external connection attempts**.
All **24 JSON files** in the two protected real attempt ledgers were unchanged
before and after the suite. Tests wrote only their temporary fixtures; they
did not reset a real ledger or generate an answer.

This is an engineering check, not semantic certification or evidence of user
benefit. The checking AI agent previously implemented the factual-answer and
retrieval changes, so this note is not presented as independent review of its
own code. Separate simulated semantic scrutiny is retained in
`results/graphrag-coursework-20261015/independent_review.json`.

## Actual test invocation

Working directory: `D:\项目\5588\AutoTriager-Shop`.

The suite ran through the existing `.venv-rag` interpreter. A unique workspace
scratch directory was selected and checked to be absent before pytest received
it. The process disabled bytecode and pytest cache writes. Its wrapper allowed
only loopback TCP connections and hashed both protected ledgers before/after.
The actual pytest argument list was:

```powershell
.\.venv-rag\Scripts\python.exe - `
  tests/test_cloud_graph_import.py `
  tests/test_graph_rag.py `
  tests/test_workbench.py `
  tests/test_workbench_graph_rag.py `
  tests/test_model_attempts.py `
  tests/test_rag_corpus.py `
  -q -p no:cacheprovider --basetemp $ragEngineeringTemp
```

The `-` consumed this wrapper through PowerShell standard input:

```python
import hashlib, json, socket, sys
from pathlib import Path
import pytest
root = Path.cwd()
ledger_dirs = [root / '.local-demo/cloud-rag-attempts',
               root / '.local-demo/graphrag-coursework-20261015-attempts']
def ledger_hashes():
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ledger_dirs for p in directory.glob('*.json')}
before = ledger_hashes()
connect = socket.socket.connect
blocked = []
def loopback_only(self, address):
    if isinstance(address, tuple) and address[0] not in {'127.0.0.1', '::1', 'localhost'}:
        blocked.append(str(address[0]))
        raise AssertionError('External connections are forbidden in engineering verification')
    return connect(self, address)
socket.socket.connect = loopback_only
code = pytest.main(sys.argv[1:])
after = ledger_hashes()
print(json.dumps({'blocked_external_connection_attempts': len(blocked),
                  'protected_ledger_files_before': len(before),
                  'protected_ledger_files_after': len(after),
                  'protected_ledgers_unchanged': before == after}))
raise SystemExit(code or bool(blocked) or (before != after))
```

Observed output:

```text
118 passed in 14.54s
blocked_external_connection_attempts: 0
protected_ledger_files_before: 24
protected_ledger_files_after: 24
protected_ledgers_unchanged: true
```

The approved run used execution outside the Windows sandbox restriction to
permit existing atomic hard-link tests and local HTTP fixtures. The graph
tests use fake graph objects; the generation test replaces `requests.post`
with a synthetic response. Workbench HTTP requests target temporary loopback
servers. Ledger subprocess workers perform only local synthetic ledger work;
the socket guard is an in-process guard, not a system firewall.

Corpus rebuilding was included only after verifying the local source checkout:
`git -C ../simulator/opentelemetry-demo-3.1.0 rev-parse HEAD` returned
`dedc0178918e260823323b8d95005a8cb924b007`, and all five referenced source files
matched their preserved SHA-256 values after the corpus's CRLF normalization.
The rebuild tests additionally compare those files with the pinned Git blobs
and reproduce the committed corpus bytes. No upstream URL revalidation or
source modification was performed.

## Saved-result and status checks

A separate read-only check of the three v2 saved answers found:

| Check | Observed result |
| --- | --- |
| Packet content hashes and answer packet IDs | All three matched |
| Raw generated content after reversible reference mapping and summary composition | All three matched saved status, claims, uncertainties, next checks, and answer |
| Saved source labels | All three `fresh_gemini` |
| Prompt version in raw-response diagnostics | All three `incident-rag-v5-human-dependency-gate` |
| Saved statuses | Basic: `answered`; multi-hop: `answered`; research: `hypotheses` |
| Five October 13 terminal receipts | Hashes still match the October 15 execution plan |

These are checks of preserved receipts, not new calls. `answered` is a response
category and does not certify correctness or completeness. The report labels
itself a saved execution replay, shows full structured claims, distinguishes
static source relations from runtime observations, and identifies the separate
two-hop graph query as additional demonstration rather than model input.

The student's basic evaluation is **deferred: domain explanation requested**.
The other two evaluations are pending a guided walkthrough. Their semantic
verdicts remain null. Accepting the earlier existence-first dependency policy
does not constitute approval of any new answer.

## Two bounded repairs following review

### Review applicability

The initial report builder could show its global v2 AI review while rendering
v1 or changed receipt files. `scripts/build_coursework_review.py` now applies
that review only when:

- The requested revision matches the review's explicit
  `multihop_path_audit.separate_graph_receipt.path` revision.
- Every reviewed case's packet identity matches the displayed packet and answer.
- Current `context.json` and `answer.json` bytes for all three cases match the
  review's `cases.<name>.file_byte_sha256` bindings.

An absent binding, revision mismatch, missing file, or changed file produces a
visible stale/not-applicable warning and withholds qualitative assessments and
scores in HTML and Markdown. It does not rewrite original answers or reviews.

Five bounded offline checks passed: exact v2 applicability; v1 rejection;
simulated answer-byte change; simulated context-byte change; and a missing
answer hash. Byte changes were simulated by an in-memory read patch, leaving
the source files untouched. The exact-v2 check also confirmed null human
semantic verdicts. The broader suite was not repeated for this report-only fix.

### Fresh-clone receipt output

The published execution plan records five historical attempts. A fresh clone
without the private old ledger recomputes zero, so reusing that published output
directory would correctly refuse to overwrite the differing plan. The runner
now accepts an explicit new receipt directory:

```powershell
.\.venv-rag\Scripts\python.exe scripts/run_coursework_graphrag.py retrieve `
  --question all --revision v2 --output-dir results/graphrag-local-run
```

`--output-dir` must resolve to a strict subdirectory of this repository's
`results` directory. It affects preparation, retrieval receipts, and answer
receipts only. The model ledger constant and four-attempt ceiling remain
unchanged; changing the output directory creates no new quota or reset.

Three bounded offline fixture checks passed: a fresh-clone layout with the
published plan and no old ledger routes all three queries into a separate
directory; repeating preparation preserves its identical new plan; and paths
outside `results` or the `results` root itself are rejected. The fixture's
published plan bytes were unchanged, its new plan honestly recorded zero
available historical receipts, and no graph/model service was instantiated.
The temporary fixture was removed after verification.

## Remaining limits

- Required-evidence checks in the runner are advisory receipts, not an automatic
  pre-generation gate. The retained v2 examples satisfy their declared sets;
  a future runner invocation still needs that check before spending a model call.
- Citation/role validation does not verify entailment. The separate simulated
  review retains three partially supported structured claims, incomplete
  generated parent-link explanations, and limited discriminating value of the
  next check. Engineering tests do not repair those raw semantic limitations.
- The short application summary uses the first three claims; later source or
  limitation claims can be omitted. Full structured claims and material caveats
  must remain visible in the report and slides.
- These checks do not establish live deployed-source equality, root cause,
  retrieval precision, comparative GraphRAG benefit, or effective human review.
  Final slide rendering, publication, and instructor coverage are handled
  separately from this engineering verification.

## Selected publication-copy check

The parent agent then copied only the authorized coursework files into the
clean publication checkout, keeping its curated README and excluding unrelated
local modules and private state. In that checkout, the focused graph-import,
GraphRAG, and workbench-GraphRAG suites completed with **63 passed in 7.44 s**.
The command was `python -m pytest tests/test_graph_rag.py
tests/test_cloud_graph_import.py tests/test_workbench_graph_rag.py -q` with a
fresh workspace temporary directory. This checks the selected public package,
not a new live cloud/model experiment; its mocks do not demonstrate model
answer correctness.
