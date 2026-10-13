import React, { useEffect, useRef, useState } from 'react';
import { ApiError, request, safeSource } from './api';
import { CaseResponse, Language, Observation } from './types';
import './GraphRAGPanel.css';

interface KnowledgeItem {
  id: string; title?: string; text?: string; source_url?: string; source_locator?: string;
  version?: string; evidence_status?: string; text_kind?: string; application_limit?: string; [key: string]: unknown;
}
interface Packet {
  packet_id: string; snapshot_id: string; analysis_id: string;
  scope: Record<string, unknown>; observations: Observation[]; knowledge: KnowledgeItem[];
  relations: Record<string, unknown>[]; gaps: string[]; stages: unknown[];
  [key: string]: unknown;
}
interface RagAnswer {
  status: string; answer: string; claims: { kind?: string; text: string; citation_ids: string[] }[];
  uncertainties: string[]; model?: string; latency_ms?: number; packet_id: string;
  snapshot_id: string; analysis_id: string; next_checks?: unknown[];
  validation?: { citation_ids_valid?: boolean; claim_support?: string; causal_confirmation?: boolean };
  semantic_review?: {
    status: string; reviewer: string;
    findings: { claim_index?: number | null; section?: string; item_index?: number; severity: string; text: string }[]; limitations?: string;
  };
  [key: string]: unknown;
}
interface RagStatus { enabled?: boolean; model_enabled?: boolean; remaining_attempts?: number; backend?: string; reason?: string }

const words = {
  en: {
    title: 'Investigate with GraphRAG', intro: 'Connect this incident’s captured observations with sourced system knowledge. Inspect the evidence before asking Gemini to explain it.',
    question: 'Investigation question', placeholder: 'What could explain these observations, and which check would distinguish the alternatives?',
    scope: 'Selected services', all: 'All services in this incident', retrieve: '1. Retrieve evidence', retrieving: 'Retrieving from the graph…',
    generate: '2. Ask Gemini', generating: 'Generating an evidence-bound answer…', modelNotice: 'This separate action sends the displayed evidence packet to Gemini and counts against the local attempt budget.',
    disabled: 'GraphRAG is not enabled on this server.', unavailable: 'GraphRAG status is unavailable. The recorded investigation remains usable.',
    modelDisabled: 'New model calls are currently unavailable. You can still inspect the retrieved evidence.', remaining: 'Remaining generation attempts',
    source: 'Open source', knowledge: 'Retrieved system knowledge', observations: 'Selected runtime observations', relations: 'Retrieved relationships',
    gaps: 'Knowledge and observation gaps', noKnowledge: 'No matching knowledge was retrieved. This limits the explanation.', noObservations: 'No runtime observations were selected.',
    answer: 'New GraphRAG answer', claims: 'Claims and citations', uncertainty: 'Uncertainties', scopeDetail: 'Exact investigation scope',
    packet: 'Full evidence packet', trace: 'Retrieval receipt', inspect: 'Inspect original record', citationMissing: 'Citation not found in the displayed packet',
    boundary: 'A dependency or a matching citation does not prove a cause. Review the evidence and remaining gaps.',
    step1: 'Scope', step1sub: 'Incident + question', step2: 'Retrieve', step2sub: 'Graph + source passages',
    step3: 'Inspect', step3sub: 'Observations + limitations', step4: 'Explain', step4sub: 'Cited answer + checks',
    details: 'Source and applicability', rawAnswer: 'Full generation receipt', retry: 'Refresh status', unknown: 'Unspecified',
    paraphrase: 'Source-based paraphrase', nextChecks: 'Suggested read-only checks',
    referenceCheck: 'Citation IDs resolve to the supplied evidence. Whether that evidence supports each claim still requires human review.',
    validation: 'Validation boundary',
    reviewFlagged: 'Simulated review found issues — do not treat this as a verified finding.',
    reviewedClaim: 'Claim', reviewedCheck: 'Next check', reviewedOutput: 'Output', reviewNote: 'The original model answer is preserved below for inspection.',
  },
  zh: {
    title: '用 GraphRAG 继续调查', intro: '将这次故障的运行观察与有来源的系统知识连接起来。先查看检索结果，再让 Gemini 基于这些证据分析。',
    question: '调查问题', placeholder: '哪些机制可能解释这些观察？下一项检查如何区分不同解释？',
    scope: '所选服务', all: '本次故障中的全部服务', retrieve: '1. 检索证据', retrieving: '正在检索图谱…',
    generate: '2. 让 Gemini 分析', generating: '正在生成有依据的回答…', modelNotice: '这项独立操作会将展示的证据包发送给 Gemini，并计入本地模型调用次数。',
    disabled: '当前服务器未启用 GraphRAG。', unavailable: '暂时无法读取 GraphRAG 状态。已有的历史调查仍然可用。',
    modelDisabled: '目前不能发起新的模型调用。仍然可以查看检索到的证据。', remaining: '剩余生成次数',
    source: '打开原始来源', knowledge: '检索到的系统知识', observations: '选取的运行观察', relations: '检索到的关系',
    gaps: '知识与观测缺口', noKnowledge: '未检索到匹配的系统知识，因此解释能力有限。', noObservations: '未选取到运行观察。',
    answer: '本次 GraphRAG 回答', claims: '具体主张与引用', uncertainty: '不确定性', scopeDetail: '准确的调查范围',
    packet: '完整证据包', trace: '检索过程记录', inspect: '查看原始记录', citationMissing: '当前证据包中没有找到该引用',
    boundary: '依赖关系或有效引用不等于因果证明。请核查证据及仍然存在的缺口。',
    step1: '限定范围', step1sub: '故障与问题', step2: '检索', step2sub: '图关系与原文',
    step3: '检查', step3sub: '观测与限制', step4: '解释', step4sub: '引用与下一项检查',
    details: '来源与适用条件', rawAnswer: '完整生成记录', retry: '刷新状态', unknown: '未说明',
    paraphrase: '基于来源的转述', nextChecks: '建议的只读核查',
    referenceCheck: '引用编号已对应到提供的证据，但证据是否真正支持每条主张，仍需人工核查。',
    validation: '验证边界',
    reviewFlagged: '模拟评审发现问题，请勿将此回答当作已验证的结论。',
    reviewedClaim: '主张', reviewedCheck: '下一项检查', reviewedOutput: '输出', reviewNote: '下方保留模型原始回答，供逐项检查。',
  },
};

export function GraphRAGPanel({ data, components, apiBase, lang, stale, onStale, onInspect }: {
  data: CaseResponse; components: string[]; apiBase: string; lang: Language; stale: boolean;
  onStale: () => void; onInspect: (id: string) => void;
}) {
  const t = words[lang];
  const [question, setQuestion] = useState('');
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [busy, setBusy] = useState<'retrieve' | 'answer' | null>(null);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const componentKey = components.join('|');
  useEffect(() => {
    const controller = new AbortController(); setStatusError(false);
    request<RagStatus>(apiBase, '/rag/status', controller.signal)
      .then(value => { if (!controller.signal.aborted) setStatus(value); })
      .catch(() => { if (!controller.signal.aborted) setStatusError(true); });
    return () => controller.abort();
  }, [apiBase, refresh]);
  useEffect(() => {
    pending.current?.abort(); sequence.current += 1;
    setPacket(null); setAnswer(null); setError(''); setBusy(null);
  }, [componentKey]);
  useEffect(() => () => { pending.current?.abort(); sequence.current += 1; }, []);

  async function run(action: 'retrieve' | 'answer') {
    if (busy || stale || !status?.enabled || (action === 'retrieve' && !question.trim()) || (action === 'answer' && !packet)) return;
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    const current = ++sequence.current; setBusy(action); setError(''); setAnswer(null);
    if (action === 'retrieve') setPacket(null);
    try {
      const result = await request<Packet | RagAnswer>(apiBase,
        `/cases/${encodeURIComponent(data.case.case_id)}/rag-${action}`, controller.signal, {
          snapshot_id: data.snapshot_id, analysis_id: data.analysis_id,
          ...(action === 'retrieve' ? { question: question.trim(), components } : { packet_id: packet!.packet_id }),
        });
      if (controller.signal.aborted || current !== sequence.current) return;
      if (result.snapshot_id !== data.snapshot_id || result.analysis_id !== data.analysis_id) { onStale(); return; }
      if (action === 'retrieve') setPacket(result as Packet); else setAnswer(result as RagAnswer);
    } catch (failure) {
      if (controller.signal.aborted || current !== sequence.current) return;
      setError(failure instanceof Error ? failure.message : t.unavailable);
      if (failure instanceof ApiError && failure.status === 409) onStale();
    } finally {
      if (!controller.signal.aborted && current === sequence.current) { setBusy(null); setRefresh(value => value + 1); }
    }
  }

  function citation(id: string) {
    const observation = packet?.observations.find(row => row.id === id);
    const item = packet?.knowledge.find(row => row.id === id);
    if (observation) return <button className="at-text-button at-mono" key={id} onClick={() => onInspect(id)}>{id}</button>;
    if (item) return <a className="at-mono" key={id} href={`#rag-knowledge-${encodeURIComponent(id)}`}>{id}</a>;
    return <span key={id} className="at-mono" title={t.citationMissing}>{id} (?)</span>;
  }

  return <section className="at-rag" aria-label={t.title}>
    <div className="at-rag-heading"><div><span className="at-eyebrow">GraphRAG / Neo4j</span><h2>{t.title}</h2></div><span className="at-outline-badge">{status?.backend ?? 'Graph + evidence'}</span></div>
    <p className="at-rag-intro">{t.intro}</p>
    <ol className="at-rag-stages" aria-label={t.trace}>{[
      [t.step1, t.step1sub, true], [t.step2, t.step2sub, !!packet], [t.step3, t.step3sub, !!packet], [t.step4, t.step4sub, !!answer],
    ].map(([title, subtitle, complete], index) => <li key={String(title)} className={complete ? 'ready' : ''}><span>{String(index + 1).padStart(2, '0')}</span><strong>{title}</strong><small>{subtitle}</small></li>)}</ol>
    <p className="at-rag-scope"><strong>{t.scope}:</strong> {components.length ? components.join(' · ') : t.all}<span className="at-mono">{data.case.case_id}</span></p>
    {statusError ? <p role="status" className="at-error">{t.unavailable} <button className="at-text-button" onClick={() => setRefresh(value => value + 1)}>{t.retry}</button></p> : status && !status.enabled ? <p className="at-fine-print">{t.disabled}</p> : null}
    <label className="at-rag-question" htmlFor="at-rag-question">{t.question}<textarea id="at-rag-question" rows={3} maxLength={2000} value={question} placeholder={t.placeholder} disabled={!!busy || stale} onChange={event => { setQuestion(event.target.value); setPacket(null); setAnswer(null); setError(''); }}/></label>
    <div className="at-rag-actions"><button className="at-button at-button-primary" onClick={() => run('retrieve')} disabled={!!busy || stale || !status?.enabled || !question.trim()}>{busy === 'retrieve' ? t.retrieving : t.retrieve}</button>{status?.remaining_attempts !== undefined && <span className="at-fine-print">{t.remaining}: {status.remaining_attempts}</span>}</div>
    {busy && <p role="status" className="at-fine-print">{busy === 'retrieve' ? t.retrieving : t.generating}</p>}
    {error && <p role="alert" className="at-error">{error}</p>}
    {packet && <div className="at-rag-packet">
      <details><summary>{t.scopeDetail}</summary><pre>{JSON.stringify(packet.scope, null, 2)}</pre></details>
      <div className="at-rag-counts"><span><strong>{packet.observations.length}</strong>{t.observations}</span><span><strong>{packet.knowledge.length}</strong>{t.knowledge}</span><span><strong>{packet.relations.length}</strong>{t.relations}</span></div>
      <h3>{t.knowledge}</h3>
      {!packet.knowledge.length && <p className="at-fine-print">{t.noKnowledge}</p>}
      {packet.knowledge.map(item => { const source = safeSource(item.source_url ?? ''); return <article className="at-rag-knowledge" key={item.id} id={`rag-knowledge-${encodeURIComponent(item.id)}`}>
        <span className="at-mono">{item.id}</span><h4>{item.title ?? item.id}</h4><p>{item.text ?? ''}</p>
        <div className="at-rag-tags"><span>{item.evidence_status ?? t.unknown}</span>{item.text_kind === 'paraphrase' && <span>{t.paraphrase}</span>}{item.version && <span>{item.version}</span>}</div>
        {item.application_limit && <p className="at-fine-print">{item.application_limit}</p>}
        {source && <a href={source} target="_blank" rel="noopener noreferrer">{t.source} ↗</a>}
        <details><summary>{t.details}</summary><pre>{JSON.stringify(item, null, 2)}</pre></details>
      </article>; })}
      <details><summary>{t.observations} ({packet.observations.length})</summary>{!packet.observations.length ? <p>{t.noObservations}</p> : packet.observations.map(row => <div key={row.id} className="at-rag-observation"><strong>{row.service}</strong><p>{row.summary}</p><button className="at-text-button at-mono" onClick={() => onInspect(row.id)}>{t.inspect} · {row.id}</button></div>)}</details>
      <details><summary>{t.relations} ({packet.relations.length})</summary><pre>{JSON.stringify(packet.relations, null, 2)}</pre></details>
      <div className="at-rag-gaps"><h3>{t.gaps}</h3><ul>{packet.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>
      <details><summary>{t.trace}</summary><pre>{JSON.stringify(packet.stages, null, 2)}</pre></details>
      <details><summary>{t.packet}</summary><pre>{JSON.stringify(packet, null, 2)}</pre></details>
      <p className="at-fine-print">{t.modelNotice}</p>
      {!status?.model_enabled && <p className="at-fine-print">{t.modelDisabled}</p>}
      <button className="at-button at-button-primary" disabled={!!busy || stale || !status?.model_enabled || status.remaining_attempts === 0} onClick={() => run('answer')}>{busy === 'answer' ? t.generating : t.generate}</button>
    </div>}
    {answer && <div className="at-rag-answer">
      {answer.semantic_review?.status === 'flagged' && <div className="at-rag-review-warning" role="alert"><strong>{t.reviewFlagged}</strong><p>{t.reviewNote}</p><ul>{answer.semantic_review.findings.map((finding, index) => <li key={index}><span>{finding.section === 'next_checks' && typeof finding.item_index === 'number' ? `${t.reviewedCheck} ${finding.item_index + 1}` : typeof finding.claim_index === 'number' ? `${t.reviewedClaim} ${finding.claim_index + 1}` : t.reviewedOutput} · {finding.severity}</span>{finding.text}</li>)}</ul><p className="at-fine-print">{answer.semantic_review.reviewer}{answer.semantic_review.limitations ? ` · ${answer.semantic_review.limitations}` : ''}</p></div>}
      <span className="at-eyebrow">{t.answer} · {answer.status}</span><h3>{answer.model ?? 'Gemini'}</h3><p>{answer.answer}</p>
      {answer.validation?.citation_ids_valid === true && <div className="at-rag-gaps"><h4>{t.validation}</h4><p>{t.referenceCheck}</p>{answer.validation.claim_support && <p className="at-fine-print">{answer.validation.claim_support}</p>}</div>}
      <h4>{t.claims}</h4>{answer.claims.map((claim, index) => <div className="at-rag-claim" key={index}>{claim.kind && <span className="at-eyebrow">{claim.kind}</span>}<p>{claim.text}</p><div className="at-rag-citations">{claim.citation_ids.map(citation)}</div></div>)}
      <h4>{t.uncertainty}</h4><ul>{answer.uncertainties.map((item, index) => <li key={index}>{item}</li>)}</ul><p className="at-fine-print">{t.boundary}</p>
      {Array.isArray(answer.next_checks) && answer.next_checks.some(item => typeof item === 'string') && <><h4>{t.nextChecks}</h4><ol>{answer.next_checks.filter((item): item is string => typeof item === 'string').map((item, index) => <li key={index}>{item}</li>)}</ol></>}
      <details><summary>{t.rawAnswer}</summary><pre>{JSON.stringify(answer, null, 2)}</pre></details>
    </div>}
  </section>;
}
