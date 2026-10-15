"""Build a static, source-backed review of the saved October 15 GraphRAG run.

Standard library only; no network, model calls, credentials, or private paths.
Missing receipts remain pending. This report replays saved results, not a live UI.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "results" / "graphrag-coursework-20261015"
TYPES = {
    "basic": ("01", "Basic factual question", "Interface knowledge"),
    "multihop": ("02", "Multi-hop question", "Incident, service, and operation pathway"),
    "research": ("03", "Research question", "Inspection priority and causal limits"),
}
RECEIPTS = ("context.json", "answer.json", "retrieval_checks.json",
            "explicit_two_hop.json", "answer_review.json", "failure.json")
PRIVATE_KEYS = {"password", "api_key", "apikey", "authorization", "credentials",
                "access_token", "refresh_token", "private_key", "secret", "secret_key"}

CSS = """
:root{color-scheme:light;font-family:Arial,Helvetica,sans-serif;color:#151515;background:#f2f2f2}
*{box-sizing:border-box}body{margin:0;line-height:1.6}a{color:inherit;text-underline-offset:3px}
.wrap{max-width:1280px;margin:auto;padding:0 38px}header{background:white;border-bottom:1px solid #ccc;padding:46px 0 32px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:#555}
h1{font-size:42px;line-height:1.12;letter-spacing:-.04em;margin:12px 0 18px;max-width:960px}
h2{font-size:30px;line-height:1.2;letter-spacing:-.025em;margin:8px 0 12px}h3{font-size:18px;margin:24px 0 12px}
h4{font-size:15px;margin:0 0 8px}p{margin:10px 0 16px}.lede{font-size:18px;max-width:960px}
.muted,.meta{color:#555;font-size:13px}.meta{overflow-wrap:anywhere}.banner{border-left:4px solid #111;background:#f2f2f2;padding:14px 18px;font-size:14px}
nav{position:sticky;top:0;z-index:10;background:#171717;color:#fff;border-bottom:1px solid #000}
nav .wrap{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding-top:11px;padding-bottom:11px}
nav a{font-size:14px;font-weight:700;padding:7px 12px;border:1px solid #666;text-decoration:none}nav a:hover,nav a:focus{background:#fff;color:#111}
main{padding-top:28px;padding-bottom:60px}.question-section{scroll-margin-top:90px;background:#fff;border:1px solid #c8c8c8;margin-bottom:34px;padding:30px}
.question{border-left:4px solid #111;padding:14px 20px;margin:20px 0;background:#f5f5f5;font-size:19px;line-height:1.5}
.receipt{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #bbb;margin:20px 0}
.receipt div{padding:12px 15px;border-right:1px solid #ddd;overflow-wrap:anywhere}.receipt div:last-child{border:0}
.receipt span{display:block;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:.06em}.receipt strong{display:block;font-size:15px;margin-top:5px}
.columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}.columns>div{min-width:0}
.evidence{border:1px solid #ccc;padding:16px;margin:0 0 14px;scroll-margin-top:100px}.evidence blockquote{margin:10px 0;font-size:15px;white-space:pre-wrap}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#555;font-weight:700}.limit{font-size:13px;border-top:1px solid #ddd;padding-top:10px;margin-bottom:0}
code{font-family:Consolas,monospace;font-size:.88em;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:#f7f7f7;border:1px solid #ddd;padding:14px;line-height:1.5;font-size:12px;max-height:560px;overflow:auto}
.claims{list-style:none;padding:0;counter-reset:claims;margin:0}.claims li{counter-increment:claims;padding:13px 0;border-bottom:1px solid #ddd}.claims li:first-child{padding-top:0}.claim-number:before{content:counter(claims) ". ";font-weight:bold}.claims p{margin:7px 0 9px}
.citations{display:flex;flex-wrap:wrap;gap:5px}.citations a,.citation-missing{border:1px solid #bbb;padding:2px 6px;font:11px Consolas,monospace;text-decoration:none;overflow-wrap:anywhere}
.citation-missing{border-style:dashed}.pending{border:1px dashed #777;background:#fafafa;padding:14px 18px}.warning{border:2px solid #222;padding:14px;margin:16px 0}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.5;margin:12px 0 20px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #ddd;padding:10px;overflow-wrap:anywhere}th{background:#eee;font-size:11px;text-transform:uppercase;letter-spacing:.04em}td pre{margin:0;font-size:11px;min-width:220px}
details{border:1px solid #d0d0d0;padding:12px 15px;margin:12px 0}summary{cursor:pointer;font-size:14px;font-weight:700}details[open] summary{margin-bottom:12px}.artifact-links{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px}.review-block{border-top:2px solid #222;margin-top:26px;padding-top:5px}ul,ol{padding-left:23px}li{margin:6px 0}.footer{font-size:12px;color:#555;margin:20px 0}.full-record{scroll-margin-top:100px}
@media(max-width:850px){.wrap{padding:0 18px}.question-section{padding:20px}.columns{grid-template-columns:1fr}.receipt{grid-template-columns:1fr 1fr}.receipt div{border-bottom:1px solid #ddd}h1{font-size:33px}h2{font-size:26px}.question{font-size:17px}nav .wrap{gap:6px}nav a{font-size:12px;padding:5px 8px}}
@media print{nav{position:static}body{background:white}.wrap{max-width:none;padding:0}.question-section{break-before:page;border:0;padding:15px 0}.columns{grid-template-columns:1fr 1fr}details{display:block}pre{max-height:none}a{color:black}header{padding:20px 0}.receipt{break-inside:avoid}.evidence,.claims li{break-inside:avoid}}
"""


def public(value):
    """Defensive field redaction; token usage counters are not credentials."""
    if isinstance(value, dict):
        return {key: ("[redacted private field]" if str(key).lower() in PRIVATE_KEYS else public(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [public(item) for item in value]
    return value


def dumps(value):
    return json.dumps(public(value), ensure_ascii=False, indent=2)


def esc(value):
    return html.escape(str(value), quote=True)


def anchor(name, ident):
    return name + "-" + re.sub(r"[^a-zA-Z0-9_-]", "-", str(ident))


def safe_source(value):
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username and not parsed.password:
            return str(value)
    except ValueError:
        pass
    return None


def source_html(row):
    url = safe_source(row.get("source_url") or row.get("source_locator", ""))
    label = row.get("source_path") or row.get("source_section") or "Original source"
    if row.get("line_start") is not None:
        label += f":{row['line_start']}–{row.get('line_end', row['line_start'])}"
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>' if url else esc(label)


def read_json(path, errors):
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("expected a JSON object")
        return public(value)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{path.name}: unreadable receipt ({type(exc).__name__}).")
        return None


def human_entry(record, name):
    if not isinstance(record, dict):
        return None
    for field in ("questions", "evaluations", "responses", "answers"):
        items = record.get(field)
        if isinstance(items, dict) and name in items:
            return items[name]
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and any(item.get(key) == name for key in ("question_type", "id", "question", "type")):
                    return item
    return record.get(name)


def human_status(entry):
    if entry is None:
        return "Pending"
    if isinstance(entry, dict):
        for key in ("status", "evaluation_status", "assessment", "decision", "verdict"):
            if isinstance(entry.get(key), str):
                return entry[key]
    return "Recorded entry; inspect below"


def review_binding(review, sections, revision):
    """Apply qualitative review only to its exact revision and preserved bytes."""
    if review is None:
        return {"status":"pending", "reasons":["No overall independent review file is available."]}
    # The current review stores its revision in this explicit receipt path.
    audit=review.get("multihop_path_audit",{})
    graph_receipt=audit.get("separate_graph_receipt",{}) if isinstance(audit,dict) else {}
    receipt=graph_receipt.get("path","") if isinstance(graph_receipt,dict) else ""
    match=re.fullmatch(r"(v[1-9][0-9]*)/multihop/explicit_two_hop\.json",str(receipt))
    bound_revision=match[1] if match else None
    reasons=[]
    if bound_revision != revision:
        reasons.append("The review's recorded revision does not match the displayed revision.")
    cases=review.get("cases",{})
    for section in sections:
        name=section["name"]
        case=cases.get(name,{}) if isinstance(cases,dict) else {}
        case=case if isinstance(case,dict) else {}
        hashes=case.get("file_byte_sha256",{})
        packet=section["records"]["context.json"] or {}
        answer=section["records"]["answer.json"] or {}
        if (not case.get("packet_id") or case["packet_id"] != packet.get("packet_id")
                or answer.get("packet_id") != packet.get("packet_id")):
            reasons.append(f"{name}: review, answer, and packet identities do not match.")
        for filename in ("context.json","answer.json"):
            expected=hashes.get(filename) if isinstance(hashes,dict) else None
            try:
                actual=hashlib.sha256((section["directory"]/filename).read_bytes()).hexdigest()
            except OSError:
                actual=None
            if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected) or actual != expected:
                reasons.append(f"{name}: {filename} is missing or differs from the reviewed file hash.")
    return {"status":"applicable" if not reasons else "stale_or_not_applicable",
            "review_revision":bound_revision,"requested_revision":revision,"reasons":reasons}


def gather(base, revision):
    errors = []
    plan = read_json(base / "execution_plan.json", errors) or {}
    human = read_json(base / "human_evaluation.json", errors)
    ai = read_json(base / "independent_review.json", errors)
    ai_markdown = None
    if (base / "INDEPENDENT_REVIEW.md").is_file():
        ai_markdown = (base / "INDEPENDENT_REVIEW.md").read_text(encoding="utf-8-sig")
    sections = []
    for name in TYPES:
        directory = base / revision / name
        local_errors = []
        records = {filename: read_json(directory / filename, local_errors) for filename in RECEIPTS}
        packet = records["context.json"] or {}
        checks = records["retrieval_checks.json"] or {}
        required = plan.get("required_evidence", {}).get(name, {})
        if not required:
            required = {kind: sorted(set(data.get("found", []) + data.get("missing", [])))
                        for kind, data in checks.get("required_evidence", {}).items()}
        sections.append({"name": name, "directory": directory, "records": records,
                         "question": packet.get("question") or plan.get("questions", {}).get(name) or "Question receipt pending.",
                         "required": required, "human": human_entry(human, name), "errors": local_errors})
    binding=review_binding(ai,sections,revision)
    if binding["status"] != "applicable":
        ai=None
        ai_markdown=None
        for section in sections:
            # Do not expose companion qualitative scores under an inapplicable review.
            section["records"]["answer_review.json"]=None
    return {"base": base, "revision": revision, "plan": plan, "human": human,
            "ai": ai, "ai_markdown": ai_markdown, "ai_review_binding":binding,"sections": sections, "errors": errors,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def evidence_groups(section):
    records = section["records"]
    packet = records["context.json"] or {}
    answer = records["answer.json"] or {}
    cited = {ident for claim in answer.get("claims", []) for ident in claim.get("citation_ids", [])}
    groups = {}
    for kind in ("knowledge", "observations"):
        rows = packet.get(kind, [])
        required = set(section["required"].get(kind, []))
        groups[kind] = [row for row in rows if row.get("id") in required]
        groups["extra_" + kind] = [row for row in rows if row.get("id") in cited - required]
        groups["missing_" + kind] = sorted(required - {row.get("id") for row in rows})
    return groups


def json_details(title, value, ident=None):
    attr = f' id="{esc(ident)}" class="full-record"' if ident else ""
    return f'<details{attr}><summary>{esc(title)}</summary><pre>{esc(dumps(value))}</pre></details>'


def knowledge_html(name, row):
    return (f'<article class="evidence" id="{esc(anchor(name, row.get("id", "")))}">'
            f'<div class="label">{esc(row.get("kind", "Knowledge"))} · {esc(row.get("text_kind", "stored text"))}</div>'
            f'<h4>{esc(row.get("title", "Knowledge passage"))}</h4><code>{esc(row.get("id", ""))}</code>'
            f'<blockquote>{esc(row.get("text", "Text missing from receipt."))}</blockquote>'
            f'<div class="meta">{source_html(row)}<br>Version: {esc(row.get("source_version", "not recorded"))}</div>'
            f'<p class="limit"><strong>Application limit:</strong> {esc(row.get("application_limit", "Not recorded."))}</p></article>')


def observations_html(name, rows):
    if not rows:
        return '<p class="muted">No observations required or cited in this group.</p>'
    body = []
    for row in rows:
        raw = row.get("raw", {})
        fields = {key: row[key] for key in ("timestamp", "trace_id", "span_id") if key in row}
        fields["raw"] = raw
        body.append(f'<tr id="{esc(anchor(name, row.get("id", "")))}"><td><code>{esc(row.get("id", ""))}</code><br>{esc(row.get("service", ""))}<br><span class="muted">{esc(row.get("kind", ""))}</span></td>'
                    f'<td>{esc(row.get("summary", ""))}<pre>{esc(dumps(fields))}</pre></td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>Original record / emitter</th><th>Saved observation fields (literal)</th></tr></thead><tbody>' + "".join(body) + '</tbody></table></div>'


def citations_html(name, ids, available):
    output = []
    for ident in ids:
        if ident in available:
            output.append(f'<a href="#{esc(anchor(name, ident))}">{esc(ident)}</a>')
        else:
            output.append(f'<span class="citation-missing">{esc(ident)} · unresolved in packet</span>')
    return '<div class="citations">' + "".join(output) + '</div>'


def list_html(items):
    return '<ul>' + "".join(f'<li>{esc(item)}</li>' for item in items) + '</ul>' if items else '<p class="muted">None recorded.</p>'


def claims_html(section):
    name = section["name"]
    records = section["records"]
    answer = records["answer.json"]
    if not answer:
        text = '<div class="pending"><strong>Generated answer pending.</strong><br>No answer.json is available for this revision. No answer has been invented.</div>'
        return text + (json_details("Saved generation failure", records["failure.json"]) if records["failure.json"] else "")
    packet = records["context.json"] or {}
    available = {row.get("id") for kind in ("knowledge", "observations") for row in packet.get(kind, [])}
    output = []
    if answer.get("packet_id") != packet.get("packet_id"):
        output.append('<p class="warning">The answer and displayed packet do not have matching packet IDs. Do not treat them as a verified evidence pair.</p>')
    output.append('<p class="muted">Verbatim saved model claims. Citation links open packet evidence; a valid ID does not establish claim support.</p><ol class="claims">')
    for claim in answer.get("claims", []):
        output.append(f'<li><span class="label claim-number">{esc(claim.get("kind", "unspecified role"))}</span><p>{esc(claim.get("text", ""))}</p>{citations_html(name, claim.get("citation_ids", []), available)}</li>')
    output.append('</ol><h4 style="margin-top:20px">Recorded uncertainties</h4>' + list_html(answer.get("uncertainties", [])))
    output.append('<h4>Suggested read-only checks — not executed by this report</h4>' + list_html(answer.get("next_checks", [])))
    return "".join(output)


def graph_html(section):
    packet = section["records"]["context.json"] or {}
    relations = packet.get("relations", [])
    output = ['<h3>Graph context</h3><p class="muted">These are the relationships stored in the actual context packet. Static calls and candidate dependencies do not establish incident causation.</p>']
    if relations:
        rows = []
        for row in relations:
            rows.append('<tr>' + "".join(f'<td>{esc(row.get(key, "not recorded"))}</td>' for key in ("from", "kind", "to", "condition", "evidence_status")) + '</tr>')
        output.append('<div class="table-wrap"><table><thead><tr><th>From</th><th>Relation</th><th>To</th><th>Condition</th><th>Evidence status</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')
    else:
        output.append('<p class="pending">No graph relationships recorded in the available packet.</p>')
    twohop = section["records"]["explicit_two_hop.json"]
    if twohop:
        output.append('<h3>Additional executed Cypher query</h3><p class="muted">' + esc(twohop.get("role", "Saved query receipt; inspect its recorded scope.")) + '</p><pre>' + esc(twohop.get("statement", "Statement not recorded.")) + '</pre>')
        rows = twohop.get("rows", [])
        columns = list(dict.fromkeys(key for row in rows for key in row))
        if columns:
            output.append('<div class="table-wrap"><table><thead><tr>' + "".join(f'<th>{esc(key)}</th>' for key in columns) + '</tr></thead><tbody>' + "".join('<tr>' + "".join(f'<td>{esc(row.get(key, ""))}</td>' for key in columns) + '</tr>' for row in rows) + '</tbody></table></div>')
        else:
            output.append('<p>No returned rows in the saved query receipt.</p>')
    return "".join(output)


def coverage_text(section, kind):
    packet = section["records"]["context.json"]
    required = set(section["required"].get(kind, []))
    if packet is None:
        return "pending"
    found = {row.get("id") for row in packet.get(kind, [])}
    return f"{len(required & found)}/{len(required)} required IDs present"


def section_html(section, revision):
    name = section["name"]
    number, title, subtitle = TYPES[name]
    records = section["records"]
    packet = records["context.json"] or {}
    answer = records["answer.json"] or {}
    groups = evidence_groups(section)
    output = [f'<section class="question-section" id="{name}"><div class="eyebrow">Question {number} · {esc(subtitle)}</div><h2>{esc(title)}</h2><blockquote class="question">{esc(section["question"])}</blockquote>']
    output.append('<div class="receipt">' + "".join(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in (
        ("Recorded answer status", answer.get("status", "pending")), ("Required knowledge", coverage_text(section, "knowledge")),
        ("Required observations", coverage_text(section, "observations")), ("Human evaluation", human_status(section["human"])))) + '</div>')
    output.append(f'<p class="meta">Revision: {esc(revision)} · Packet: {esc(packet.get("packet_id", "pending"))}<br>Recorded model: {esc(answer.get("model", "pending"))} · Receipt source: {esc(answer.get("source", "pending"))} · Recorded latency: {esc(answer.get("latency_ms", "not recorded"))} ms</p>')
    for error in section["errors"]:
        output.append(f'<p class="warning">{esc(error)}</p>')
    output.append('<div class="columns"><div><h3>Required retrieved knowledge</h3><p class="muted">Literal stored text, shown in full. Corpus paraphrases are not verbatim quotations from the source files.</p>')
    output.extend(knowledge_html(name, row) for row in groups["knowledge"])
    if groups["missing_knowledge"]:
        output.append('<div class="pending">Required knowledge missing from the available packet: ' + esc(", ".join(groups["missing_knowledge"])) + '</div>')
    if not section["required"].get("knowledge"):
        output.append('<p class="pending">Required knowledge set not yet recorded.</p>')
    output.append('</div><div><h3>Saved generated answer</h3>' + claims_html(section) + '</div></div>')
    output.append(graph_html(section))
    output.append('<h3>Required original observations</h3>' + observations_html(name, groups["observations"]))
    if groups["missing_observations"]:
        output.append('<p class="pending">Required observations missing: ' + esc(", ".join(groups["missing_observations"])) + '</p>')
    if groups["extra_knowledge"]:
        output.append('<h3>Additional knowledge cited by the answer</h3>' + "".join(knowledge_html(name, row) for row in groups["extra_knowledge"]))
    if groups["extra_observations"]:
        output.append('<h3>Additional observations cited by the answer</h3>' + observations_html(name, groups["extra_observations"]))
    output.append('<div class="review-block"><h3>Student evidence evaluation</h3>')
    if section["human"] is None:
        output.append('<p class="pending"><strong>Pending.</strong> No question-level human evaluation is recorded. Dahe Chen should judge the claims against the displayed evidence as supported, partially supported, unsupported, or unsure; skip is permitted. This page does not submit or fabricate an evaluation.</p>')
    else:
        output.append('<p class="muted">Verbatim entry from human_evaluation.json. The report does not infer approval from its presence.</p><pre>' + esc(dumps(section["human"])) + '</pre>')
    output.append('<h3>Independent simulated AI review</h3>')
    if records["answer_review.json"]:
        output.append(json_details("Recorded question-level AI review", records["answer_review.json"]))
    else:
        output.append('<p class="muted">No question-level answer_review.json found. See the separate <a href="#independent-review">overall review record</a>. AI review does not replace the student evaluation.</p>')
    output.append('</div><h3>Original receipts</h3><div class="artifact-links">')
    for filename in RECEIPTS:
        if records[filename] is not None:
            output.append(f'<a href="{quote(revision + "/" + name + "/" + filename)}">{esc(filename)}</a>')
    output.append('</div>')
    for filename in ("retrieval_checks.json", "context.json", "answer.json"):
        if records[filename] is not None:
            output.append(json_details("Expand complete " + filename, records[filename]))
    output.append('</section>')
    return "".join(output)


def render_html(data):
    revision = data["revision"]
    output = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoTriager — Three GraphRAG Questions</title><style>' + CSS + '</style></head><body>']
    output.append('<header id="top"><div class="wrap"><div class="eyebrow">CS 5588 · Dahe Chen · October 15, 2026</div><h1>Three questions. Inspectable evidence.</h1><p class="lede">AutoTriager GraphRAG connects archived Shop observations with sourced platform knowledge. Review what was retrieved, what the model said, and what remains unconfirmed.</p><div class="banner"><strong>Saved execution replay.</strong> This is a static review of preserved execution receipts, not a live API or a new model run. Missing files remain pending. Reference integrity is separate from claim support, and an inspection priority is not root-cause proof.</div>')
    output.append(f'<p class="meta">Displayed revision: {esc(revision)} · Report built: {esc(data["built_at"])}<br>Scope: {esc(data["plan"].get("evaluation_scope", "See the saved execution plan; no general performance claim."))}</p></div></header>')
    output.append('<nav aria-label="Question navigation"><div class="wrap"><a href="#basic">01 Basic</a><a href="#multihop">02 Multi-hop</a><a href="#research">03 Research</a><a href="#human-review">Human evaluation</a><a href="#independent-review">AI review</a><a href="THREE_QUERIES.md">Markdown record</a></div></nav><main class="wrap">')
    output.extend(f'<p class="warning">{esc(error)}</p>' for error in data["errors"])
    output.extend(section_html(section, revision) for section in data["sections"])
    output.append('<section class="question-section" id="human-review"><div class="eyebrow">Separate decision record</div><h2>Human evaluation</h2>')
    if data["human"] is None:
        output.append('<p class="pending"><strong>Student evidence evaluation pending.</strong> No human_evaluation.json was supplied. Prior acceptance of evidence-state separation does not approve these new answers.</p>')
    else:
        output.append('<p>Recorded data from human_evaluation.json. No approval or semantic score has been inferred.</p>' + json_details("Complete human evaluation record", data["human"]))
    output.append('</section><section class="question-section" id="independent-review"><div class="eyebrow">Independent simulated scrutiny</div><h2>AI review and remaining limits</h2><p>Independent AI review is simulated scrutiny, not expert certification or the student\'s personal evaluation. A review must apply to the actual answer and packet being inspected.</p>')
    binding=data["ai_review_binding"]
    if binding["status"]=="stale_or_not_applicable":
        output.append('<div class="warning"><strong>Review stale or not applicable to these displayed receipts.</strong><p>Qualitative assessments and scores are withheld.</p>'+list_html(binding["reasons"])+ '</div>')
    elif binding["status"]=="applicable":
        output.append('<p class="meta">Review binding verified: displayed revision, packet identities, and all three context/answer file hashes match the recorded review.</p>')
    if data["ai"] is not None:
        output.append(json_details("Complete independent_review.json", data["ai"]))
    if data["ai_markdown"] is not None:
        output.append('<pre>' + esc(data["ai_markdown"]) + '</pre>')
    if binding["status"]=="pending":
        output.append('<p class="pending">No overall independent review file is available yet.</p>')
    output.append('<p class="muted">Three development questions on one previously inspected incident do not establish held-out diagnosis accuracy, comparative GraphRAG benefit, investigation-time savings, or production reliability.</p></section><p class="footer">Built only from named public result files. Source passages and observation fields are copied literally; omitted packet items remain available in the complete JSON receipts. This report makes no network requests.</p></main></body></html>')
    return "\n".join(output)


def fenced(value, language="json"):
    text = dumps(value) if language == "json" else str(value)
    fence = "`" * max(3, max((len(match.group()) + 1 for match in re.finditer(r"`+", text)), default=3))
    return f"\n{fence}{language}\n{text}\n{fence}\n"


def render_markdown(data):
    output = ["# AutoTriager: three GraphRAG questions", "", "Author: Dahe Chen. CS 5588. October 15, 2026.", "",
              f"Displayed revision: `{data['revision']}`. Report built: {data['built_at']}.", "",
              "**Saved execution replay.** This is a static report of preserved receipts, not a new model run. Missing results remain pending. Valid citation IDs do not establish semantic support or root cause.", "",
              data["plan"].get("evaluation_scope", "Evaluation scope is not yet recorded."), ""]
    output.extend(data["errors"])
    for section in data["sections"]:
        name = section["name"]
        records = section["records"]
        packet = records["context.json"] or {}
        answer = records["answer.json"]
        groups = evidence_groups(section)
        output += [f"## {TYPES[name][0]}. {TYPES[name][1]}", "", section["question"], "",
                   f"Required knowledge: {coverage_text(section, 'knowledge')}. Required observations: {coverage_text(section, 'observations')}.", "",
                   f"Packet ID: `{packet.get('packet_id', 'pending')}`.", "", "### Required knowledge", ""]
        output.extend(section["errors"])
        for row in groups["knowledge"] + groups["extra_knowledge"]:
            is_required = row in groups["knowledge"]
            output += [f"#### {row.get('id', '')} ({'required' if is_required else 'additional cited knowledge'})", "",
                       f"{row.get('title', '')} — stored {row.get('text_kind', 'text')}, copied in full.", "", row.get("text", "Text missing from receipt."), ""]
            url = safe_source(row.get("source_url", ""))
            if url:
                output += [f"[Original source]({url})", ""]
            output += [f"Source version: `{row.get('source_version', 'not recorded')}`.", "", "Application limit: " + row.get("application_limit", "Not recorded."), ""]
        if groups["missing_knowledge"]:
            output += ["Required knowledge missing: " + ", ".join(groups["missing_knowledge"]), ""]
        output += ["### Saved generated answer", ""]
        if answer:
            output += [f"Recorded status: `{answer.get('status', 'not recorded')}`; model: `{answer.get('model', 'not recorded')}`; source: `{answer.get('source', 'not recorded')}`; latency: {answer.get('latency_ms', 'not recorded')} ms.", ""]
            if answer.get("packet_id") != packet.get("packet_id"):
                output += ["**Warning: answer and displayed packet IDs do not match.**", ""]
            for i, claim in enumerate(answer.get("claims", []), 1):
                output += [f"{i}. **{claim.get('kind', 'unspecified')}** — {claim.get('text', '')}", "", "   Citations: " + ", ".join(f"`{ident}`" for ident in claim.get("citation_ids", [])), ""]
            output += ["Recorded uncertainties:", ""] + ["- " + item for item in answer.get("uncertainties", [])]
            output += ["", "Suggested checks (not executed by this report):", ""] + ["- " + item for item in answer.get("next_checks", [])] + [""]
        else:
            output += ["**Answer pending:** no answer.json for this revision. No response is invented.", ""]
            if records["failure.json"]:
                output += ["Saved failure:", fenced(records["failure.json"])]
        output += ["### Graph context", "", "Literal saved relationships; possible calls and candidate dependencies do not establish cause.", fenced(packet.get("relations", []))]
        if records["explicit_two_hop.json"]:
            output += ["Additional executed query and rows (see the recorded role; these are not additional model input):", fenced(records["explicit_two_hop.json"])]
        output += ["### Original observations", "", "Required and additional cited records, copied in full:", fenced(groups["observations"] + groups["extra_observations"])]
        if groups["missing_observations"]:
            output += ["Required observations missing: " + ", ".join(groups["missing_observations"]), ""]
        output += ["### Student evidence evaluation", ""]
        output += [fenced(section["human"])] if section["human"] is not None else ["**Pending.** No question-level human judgment recorded. AI review is separate.", ""]
        if records["answer_review.json"]:
            output += ["### Independent simulated question review", fenced(records["answer_review.json"])]
        output += ["### Original receipts", ""]
        for filename in RECEIPTS:
            if records[filename] is not None:
                link = quote(data["revision"] + "/" + name + "/" + filename)
                output.append(f"- [{filename}]({link})")
        output.append("")
    output += ["## Full human evaluation record", ""]
    output += [fenced(data["human"])] if data["human"] is not None else ["**Student evaluation pending.** No human_evaluation.json found.", ""]
    output += ["## Independent simulated AI review", "", "Simulated scrutiny is not expert certification or student approval.", ""]
    binding=data["ai_review_binding"]
    if binding["status"]=="stale_or_not_applicable":
        output += ["**Review stale or not applicable to these displayed receipts. Qualitative assessments and scores are withheld.**", ""]
        output += ["- "+reason for reason in binding["reasons"]]
    elif binding["status"]=="applicable":
        output += ["Review binding verified: displayed revision, packet identities, and all three context/answer file hashes match the recorded review.", ""]
    if data["ai"] is not None:
        output.append(fenced(data["ai"]))
    if data["ai_markdown"] is not None:
        output.append(data["ai_markdown"])
    if binding["status"]=="pending":
        output.append("Overall independent review pending; no matching review file found.")
    output += ["", "No held-out accuracy, comparative benefit, investigation-time savings, or user benefit is established by this report.", ""]
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS, help="Public coursework result directory")
    parser.add_argument("--revision", choices=("v1", "v2"), default="v2")
    args = parser.parse_args()
    base = args.results_dir.resolve()
    data = gather(base, args.revision)
    base.mkdir(parents=True, exist_ok=True)
    outputs = {"review.html": render_html(data), "THREE_QUERIES.md": render_markdown(data)}
    for filename, content in outputs.items():
        path = base / filename
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
