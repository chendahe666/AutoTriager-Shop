"""Publish review sidecars and a transparent comparison without changing answers."""
from __future__ import annotations
import html
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from autotriager_shop.graph_rag import answer_content_id, prepare_evidence_packet, validate_answer

OUT=ROOT/'results/p1-graphrag-20261026'


def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(data,indent=2,ensure_ascii=False)+'\n'
    if path.exists() and path.read_text(encoding='utf-8')!=encoded:
        raise ValueError('Review artifact differs; preserve and explicitly version a new review.')
    path.write_text(encoded,encoding='utf-8',newline='\n')


if __name__=='__main__':
    review=json.loads((OUT/'independent_support_review.json').read_text(encoding='utf-8'))
    sections=[]
    checks=[]
    esc=html.escape
    for label,case in review['cases'].items():
        arm,name=label.split('_',1)
        answer=json.loads((OUT/arm/name/'answer.json').read_text(encoding='utf-8'))
        packet=json.loads((OUT/arm/name/'context.json').read_text(encoding='utf-8'))
        assert case['answer_content_sha256']==answer_content_id(answer)
        sidecar={'status':'issues_identified' if case['semantic_review_findings'] else 'reviewed_with_limits',
            'reviewer':'Independent simulated AI review; same-family, provisional',
            'packet_id':answer['packet_id'], 'answer_content_sha256':answer_content_id(answer),
            'findings':case['semantic_review_findings'],
            'limitations':'Three inspected development questions, one incident. This review is not domain-expert certification or a student judgment.'}
        dump(OUT/'semantic_reviews'/f"{answer['model_request_id']}.json",sidecar)
        dump(ROOT/'reviews/graph-rag'/f"{answer['model_request_id']}.json",sidecar)
        enriched=packet if packet.get('evidence_chain') else prepare_evidence_packet(packet)
        checked=validate_answer(answer,enriched)
        dump(OUT/'posthoc_checks'/f'{label}.json',{
            'mode':'Post-hoc development replay; not a new generation or held-out detector evaluation',
            'original_answer_preserved':True,
            'checks':checked['validation']['grounding_checks']})
        checks.append({'case':label,'review_identity_matches':True,'original_answer_preserved':True})
        claims=''.join(f"<li><b>{esc(c['kind'])}</b>: {esc(c['text'])}<br><code>{esc(', '.join(c['citation_ids']))}</code></li>" for c in answer['claims'])
        paths=''.join(f"<li>{esc(c['text'])}<br><code>{esc(', '.join(c['citation_ids']))}</code></li>" for c in answer.get('path_explanations',[]))
        findings=''.join(f"<li>{esc(c['text'])}</li>" for c in case['semantic_review_findings']) or '<li>No whole-claim issue found within this limited review.</li>'
        sections.append(f"<section id='{label}'><h2>{esc(arm.title())}: {esc(name)}</h2><p>{esc(packet['question'])}</p><h3>Unchanged raw main claims</h3><ol>{claims}</ol><h3>Raw model path explanations</h3><ol>{paths}</ol><h3>Independent review</h3><ul>{findings}</ul><p>Latency: {answer['latency_ms']} ms. <a href='{arm}/{name}/context.json'>Exact context</a> · <a href='{arm}/{name}/answer.json'>Original answer</a> · <a href='{arm}/{name}/raw_model_response.json'>Raw response</a> · <a href='posthoc_checks/{label}.json'>Current check replay</a></p></section>")
    dump(OUT/'review_binding_checks.json',{'checks':checks,'count':len(checks),'fresh_model_calls':0})
    totals=review['totals']
    rows=[]
    for arm in ('baseline','candidate'):
        t=totals[arm]
        rows.append(f"<tr><td>{arm}</td><td>{t['whole_claims']['pass']} supported / {t['whole_claims']['partial']} partial / {t['whole_claims']['denominator']} total</td><td>{t['atomic_propositions']['pass']} supported / {t['atomic_propositions']['denominator']} total</td><td>{t['prompt_tokens']} / {t['output_tokens']}</td></tr>")
    page="""<!doctype html><html lang='en'><meta charset='utf-8'><title>AutoTriager P1: online GraphRAG comparison</title><style>body{font:18px Arial,sans-serif;line-height:1.5;max-width:1120px;margin:38px auto;color:#111;background:#fff}h1{font-size:32px}h2{font-size:26px}section{border-top:2px solid #333;margin-top:34px;padding-top:20px}table{border-collapse:collapse;width:100%;font-size:16px}th,td{text-align:left;border-bottom:1px solid #aaa;padding:10px}code{overflow-wrap:anywhere;font-size:14px}li{margin:12px 0}.decision{border:2px solid #333;padding:16px}a{color:#333}</style>"""
    page+="<h1>AutoTriager: online GraphRAG P1 comparison</h1><p>Dahe Chen · October 26, 2026 · Six fresh calls, three inspected questions, one archived incident.</p><p class='decision'><b>Retain the engineering repair and observed path-completeness gain.</b> No general diagnosis or semantic-accuracy improvement is established. Cloud retrieval is online; the preserved incident is historical.</p>"
    page+="<table><tr><th>Measurement</th><th>Baseline</th><th>Candidate</th></tr><tr><td>Raw explanation of four fixed primary links</td><td>0/4</td><td>4/4</td></tr><tr><td>Raw static-condition retention</td><td>0/2</td><td>0/2</td></tr><tr><td>Programmatic chain display</td><td>No explicit chain</td><td>20 recorded links / four traces</td></tr></table><p>The 20-link display is a separate software result, not the denominator for raw LLM reasoning.</p>"
    page+="<table><tr><th>Arm</th><th>Main claim review</th><th>Main atomic propositions</th><th>Input / output tokens</th></tr>"+''.join(rows)+"</table><p>Different claim counts prevent treating these as a simple matched accuracy percentage. Candidate research retains a citation-scope error; its investigation-priority explanation is partial. Same-family AI review is provisional.</p>"
    page+="<p>Fresh multihop latency: baseline 1.986 s, candidate 17.157 s. Single observations, not latency guarantees. Original validation missed semantic gaps; later targeted warning checks are evaluated only as post-hoc replay.</p>"
    page+="<nav>"+' · '.join(f"<a href='#{k}'>{k}</a>" for k in review['cases'])+"</nav>"+''.join(sections)
    (OUT/'review.html').write_text(page,encoding='utf-8',newline='\n')
    print(json.dumps({'bound_reviews':len(checks),'review_html':str(OUT/'review.html'),'model_calls':0}))
