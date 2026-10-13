import React, { useEffect, useMemo, useRef, useState } from 'react';
import { request, safeSource } from './api';
import { Comparison, FollowUp, Language, Observation, ObservedLink, Query } from './types';
import './LiveDesk.css';

const LOCAL_ACTIONS = ['restore_payment_demo_configuration', 'restore_image_demo_configuration'];
const ACTIVE_VERIFICATION = ['waiting_for_post_action_window', 'checking_customer_and_backend', 'waiting_for_next_check'];
type ExecutionMode = 'human_approved' | 'incident_authorized_auto';
interface LiveAnalysis {
  status?: string; candidate_service?: string | null; reason?: string; evidence_ids?: string[];
  missing_evidence?: string[]; uncertainty?: string; model?: string;
  next_step?: { label?: string; instructions?: string[]; evidence_ids?: string[]; action_id?: string; basis?: string };
}
interface Proposal {
  proposal_id: string; action_id: string; snapshot_id: string; analysis_id: string;
  reason: string; evidence_ids: string[]; label: string; target_service: string; effect: string;
}
interface Verification {
  checked_at: string; passed: boolean; errors: string[]; snapshot_id: string;
}

interface CustomerReceipt {
  journey: string; business_success: boolean; status: string; reason: string; checked_at: string;
  trace_id: string; created_order?: boolean; synthetic_purchase?: boolean;
  duration_ms?: number | null; elapsed_ms?: number | null; image_threshold_ms?: number;
  browser_image_displayed?: boolean; browser_equivalent?: boolean; image_path?: string;
  requests: { method: string; path: string; http_status?: number; response?: unknown }[];
}
interface LiveStatus {
  mode: string; checked_at: string; model_calls_enabled: boolean; model_attempts: number | null;
  model_accounting?: { availability: 'available' | 'unavailable' };
  model_budget: number; restoration_enabled: boolean;
  action_catalog: Record<string, { label: string; target_service: string; effect: string; allowed_journeys?: string[] }>;
  automatic_verification?: { state: string; checks: number; initial_wait_seconds: number; interval_seconds: number; max_checks: number; deadline_seconds: number };
  incident: {
    run_id?: string; journey?: string; state: string; snapshot_id?: string; analysis_id?: string | null; analysis?: LiveAnalysis | null; analysis_source?: string;
    snapshot?: { case: { observations: Observation[] } };
    proposal?: Proposal | null;
    execution?: { outcome: string; completed_at: string; mode?: ExecutionMode } | null;
    verification?: Verification[];
    policy?: { min_successful_probes: number; sustained_seconds: number; metric_lookback_seconds: number };
    alert?: { state: string }; events: unknown[];
  };
  latest: null | { customer: CustomerReceipt; snapshot: null | {
    case: { case_id: string; start_time: string; end_time: string; observations: Observation[] };
    fetched_at: string; errors: { source: string; message: string }[];
    freshness: { overall: string; metrics: { status: string; age_seconds: number | null }; spans: { status: string; age_seconds: number | null } };
    coverage: { logs: string; scope_limited: boolean; observed_customer_trace_ids?: string[] };
  }; collection_error?: string };
}

interface EvidenceScope {
  scope_kind: 'current' | 'archive'; run_id: string; snapshot_id: string;
  analysis_id: string | null; analysis_source: string | null;
}
type ScopedComparison = Comparison & EvidenceScope & { read_only: true };
type ScopedFollowUp = FollowUp & EvidenceScope & { read_only: true };
interface HistoryEntry {
  run_id: string; opened_at: string; last_event_at: string; journey: string; product_id?: string;
  state: string; status: 'completed' | 'unresolved' | 'incomplete'; snapshot_id: string | null;
  analysis_id: string | null; analysis_source: string | null; record_count: number;
  recovery_check_count: number; closure: { recorded: boolean; verified_at?: string; policy_revalidated?: boolean; policy_status?: string }; errors: string[];
}
interface HistoryResponse {
  mode: string; read_only: true; entries: HistoryEntry[]; count: number; truncated: boolean; limitations: string[];
}
interface HistoryDetail extends HistoryEntry {
  read_only: true; actions_disabled: true; model_calls_enabled: false;
  snapshot: { case: { case_id: string; start_time: string; end_time: string; observations: Observation[] } } | null;
  failure: CustomerReceipt | null;
  analysis_versions: { analysis_id: string; analysis_source: string; attached_at: string; analysis: LiveAnalysis }[];
  recovery_checks: (Verification & { probe?: CustomerReceipt | null })[];
  events: { at: string; event: string }[]; limitations: string[];
}
type LocalText = (en: string, cn: string) => string;

function analysisSourceLabel(source: string | null | undefined, text: LocalText) {
  if (source === 'fresh_gemini') return text('Fresh model analysis', '新的模型分析');
  if (source === 'cached_exact_request') return text('Cached result · same frozen request', '缓存结果 · 同一份冻结请求');
  if (source === 'human_review') return text('Engineer review', '工程师核查');
  if (source === 'engineering_rehearsal') return text('Scripted engineering check', '预设工程检查');
  return source || text('No attached analysis', '尚未附加分析');
}

function OriginalRecord({ row, text }: { row: Observation; text: LocalText }) {
  const source = safeSource(row.source_url);
  const membership = row.model_input_membership;
  return <details className="at-live-citation at-live-original-record"><summary><span className="at-mono">{row.id}</span><small>{row.service} · {row.kind} · {row.timestamp}</small></summary>
    <p>{row.summary}</p>
    {membership && <p className="at-fine-print">{text('Model input', '模型输入')}: {membership === 'in_model_input' ? text('Included in the frozen selection', '包含在冻结选择中') : membership === 'outside_model_input' ? text('Outside the frozen selection', '不在冻结选择中') : membership === 'not_applicable' ? text('Not applicable to this analysis', '不适用于此分析') : text('Membership unknown', '是否包含尚不清楚')}{row.cited_by_current_result && <> · {text('Cited by the selected analysis', '被所选分析引用')}</>}</p>}
    {row.in_investigation_window === false && <p className="at-live-warning">{text('This preserved record is outside the declared incident time window.', '此保留记录不在已声明的事件时间窗口内。')}</p>}
    <pre>{JSON.stringify(row.raw, null, 2)}</pre>{source && <a href={source} target="_blank" rel="noopener noreferrer">{text('Open original source', '打开原始来源')} ↗</a>}
  </details>;
}

function RecordedLinks({ links, external = [], unresolved = [], text }: { links: ObservedLink[]; external?: ObservedLink[]; unresolved?: ObservedLink[]; text: LocalText }) {
  return <div className="at-live-observed-links"><p className="at-live-warning">{text('These links show observed parent–child trace structure. They do not establish fault propagation or causality.', '这些关联仅展示已观察到的追踪父子结构，不能证明故障传播或因果关系。')}</p>
    {links.length ? <ul>{links.map((link, index) => <li key={`${link.child_evidence_id}-${index}`}><strong>{link.parent_service ?? text('Unknown parent', '未知父节点')} → {link.child_service}</strong><small>{link.parent_evidence_id} → {link.child_evidence_id} · {link.trace_id} · {link.timestamp}</small></li>)}</ul> : <p className="at-fine-print">{text('No direct links were captured between these selected components. This is not proof of independence.', '这些所选组件之间未捕获直接关联，不能据此证明它们独立。')}</p>}
    {(external.length > 0 || unresolved.length > 0) && <details><summary>{external.length} {text('links outside this comparison', '条比较范围外关联')} · {unresolved.length} {text('unresolved parents', '条父节点未确定')}</summary><pre>{JSON.stringify({ external_links: external, unresolved_parents: unresolved }, null, 2)}</pre></details>}
  </div>;
}

function FrozenEvidenceWorkspace({ apiBase, scope, records, text }: { apiBase: string; scope: EvidenceScope; records: Observation[]; text: LocalText }) {
  const [components, setComponents] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ScopedComparison | null>(null);
  const [followUp, setFollowUp] = useState<ScopedFollowUp | null>(null);
  const [queryComponent, setQueryComponent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const services = [...new Set(records.map(row => row.service))].sort();
  const enough = components.length >= 2 && components.length <= 3;
  const selectedQueryComponent = components.includes(queryComponent) ? queryComponent : components[0] ?? '';
  useEffect(() => () => { generation.current += 1; controller.current?.abort(); }, []);
  function changeComponent(service: string) {
    generation.current += 1; controller.current?.abort(); setBusy(false); setError(''); setComparison(null); setFollowUp(null);
    setComponents(current => current.includes(service) ? current.filter(item => item !== service) : current.length < 3 ? [...current, service] : current);
  }
  async function inspect(query?: Query) {
    if (!enough) return;
    const ticket = ++generation.current;
    controller.current?.abort(); controller.current = new AbortController();
    setBusy(true); setError(''); setFollowUp(null);
    try {
      const value = await request<ScopedComparison | ScopedFollowUp>(apiBase, query ? '/live/follow-up' : '/live/compare', controller.current.signal, { ...scope, components, ...(query ? { query, ...(query === 'component_records' ? { component: selectedQueryComponent } : {}) } : {}) });
      if (ticket !== generation.current) return;
      if (!value.read_only || value.scope_kind !== scope.scope_kind || value.run_id !== scope.run_id || value.snapshot_id !== scope.snapshot_id || value.analysis_id !== scope.analysis_id || value.analysis_source !== scope.analysis_source) throw new Error(text('The returned evidence scope changed. Refresh before comparing again.', '返回的证据范围已变化，请刷新后重新比较。'));
      if (query) setFollowUp(value as ScopedFollowUp); else setComparison(value as ScopedComparison);
    } catch (issue) {
      if (ticket === generation.current && !(issue instanceof Error && issue.name === 'AbortError')) { setError(issue instanceof Error ? issue.message : String(issue)); setComparison(null); }
    } finally { if (ticket === generation.current) setBusy(false); }
  }
  const queries: [Query, string][] = [['component_records', text('Show component records', '查看组件记录')], ['observed_links', text('Inspect observed links', '核查已观察关联')], ['outside_recorded_input', text('Find records outside model input', '查找模型输入外记录')]];
  return <div className="at-live-frozen-workspace" aria-busy={busy}>
    <div className="at-live-scope-strip"><span className="at-outline-badge">{scope.scope_kind === 'archive' ? text('Archived · read only', '历史归档 · 只读') : text('Current incident · frozen input', '当前事件 · 冻结输入')}</span><span className="at-mono">{scope.run_id} / {scope.snapshot_id.slice(0, 12)}</span><small>{scope.analysis_id ? `${text('Analysis', '分析')}: ${scope.analysis_id.slice(0, 12)}` : text('Original evidence only · no selected analysis', '仅原始证据 · 未选择分析')}</small></div>
    <p className="at-fine-print">{text('Choose two or three components to compare the original incident records. These preset questions inspect saved evidence; they do not call a model, collect new data, or execute a repair.', '选择两到三个组件，比较原始事件记录。这些预设问题仅核查已保存证据，不调用模型、不采集新数据，也不执行修复。')}</p>
    <div className="at-live-component-choices" role="group" aria-label={text('Components for evidence comparison', '证据比较组件')}>{services.map(service => <button key={service} className="at-button at-button-small" aria-pressed={components.includes(service)} disabled={!components.includes(service) && components.length >= 3} onClick={() => changeComponent(service)}>{service}<span>{records.filter(row => row.service === service).length}</span></button>)}</div>
    {services.length < 2 && <p className="at-live-warning">{text('This snapshot has fewer than two observed components. No cross-component comparison is available.', '此快照观察到的组件不足两个，无法进行跨组件比较。')}</p>}
    <div className="at-live-query-controls"><button className="at-button at-button-primary at-live-compare-button" disabled={!enough || busy} onClick={() => inspect()}>{text('Compare frozen evidence', '比较冻结证据')}</button><span className="at-fine-print">{components.length} / 3 {text('components selected', '个已选组件')}</span></div>
    {components.length > 0 && <label className="at-live-query-component">{text('Component for the record question', '记录问题对应的组件')}<select value={selectedQueryComponent} onChange={e => { generation.current += 1; controller.current?.abort(); setBusy(false); setFollowUp(null); setQueryComponent(e.target.value); }}>{components.map(service => <option key={service} value={service}>{service}</option>)}</select></label>}
    <div className="at-live-preset-queries">{queries.map(([query, label]) => <button className="at-button at-button-small" key={query} disabled={!enough || busy} onClick={() => inspect(query)}>{label}</button>)}</div>
    {busy && <p className="at-fine-print" role="status">{text('Reading this frozen evidence scope…', '正在读取此冻结证据范围…')}</p>}
    {error && <p className="at-error" role="alert">{error}</p>}
    {comparison && <div className="at-live-comparison-result"><div className="at-live-comparison-cards">{comparison.summaries.map(item => <article className="at-live-component-summary" key={item.service}><h3>{item.service}</h3><strong>{item.record_count}<small>{text('original records', '条原始记录')}</small></strong><dl><dt>{text('Metrics / spans / logs', '指标 / 追踪 / 日志')}</dt><dd>{item.counts_by_kind.metric} / {item.counts_by_kind.span} / {item.counts_by_kind.log}</dd><dt>{text('Error-status spans', '错误状态追踪')}</dt><dd>{item.error_span_count}</dd><dt>{text('Records cited by this analysis', '被此分析引用的记录')}</dt><dd>{item.cited_record_count}</dd></dl></article>)}</div>
      <p className="at-fine-print">{text('Model input visibility', '模型输入可见性')}: {comparison.model_input_visibility === 'frozen_selection' ? text('Exact frozen selection retained', '保留了准确的冻结选择') : comparison.model_input_visibility === 'not_applicable' ? text('Not applicable · no model input for this selected analysis', '不适用 · 所选分析无模型输入') : text('Unknown · exact selection was not retained', '未知 · 未保留准确的输入选择')}</p>
      <RecordedLinks links={comparison.links} external={comparison.external_links} unresolved={comparison.unresolved_parents} text={text} /><details className="at-live-comparison-records"><summary>{text('Inspect original comparison records', '核查原始比较记录')} ({comparison.records.length})</summary>{comparison.records.map(row => <OriginalRecord row={row} text={text} key={row.id} />)}</details>
    </div>}
    {followUp && <div className="at-live-preset-result" role="region" aria-label={text('Preset evidence query result', '预设证据查询结果')}><h3>{queries.find(([query]) => query === followUp.query)?.[1]}</h3><span className="at-outline-badge">{followUp.status}</span>{followUp.status === 'unknown' && <p className="at-live-warning">{text('Exact model-input selection is unavailable. No record can be classified as outside that input.', '准确的模型输入选择不可用，无法判定任何记录在该输入之外。')}</p>}{followUp.status === 'not_applicable' && <p className="at-fine-print">{text('The selected analysis did not use a model input. Outside-model-input filtering does not apply.', '所选分析没有使用模型输入，因此模型输入外筛选不适用。')}</p>}{followUp.records?.map(row => <OriginalRecord row={row} text={text} key={row.id} />)}{followUp.links && <RecordedLinks links={followUp.links} external={followUp.external_links} unresolved={followUp.unresolved_parents} text={text} />}{followUp.records?.length === 0 && followUp.status !== 'unknown' && followUp.status !== 'not_applicable' && <p className="at-fine-print">{text('No matching records in this frozen scope.', '此冻结范围内没有匹配记录。')}</p>}</div>}
  </div>;
}

function LiveInvestigationHistory({ apiBase, text }: { apiBase: string; text: LocalText }) {
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState('');
  const [versionId, setVersionId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  async function load(signal?: AbortSignal) {
    try { setHistory(await request<HistoryResponse>(apiBase, '/live/history', signal)); } catch (issue) { if (!(issue instanceof Error && issue.name === 'AbortError')) setError(issue instanceof Error ? issue.message : String(issue)); }
  }
  useEffect(() => { const pending = new AbortController(); load(pending.signal); return () => { pending.abort(); controller.current?.abort(); generation.current += 1; }; }, [apiBase]);
  async function open(runId: string) {
    const ticket = ++generation.current; controller.current?.abort(); controller.current = new AbortController();
    setSelectedRun(runId); setDetail(null); setVersionId(''); setError(''); setBusy(true);
    try {
      const value = await request<HistoryDetail>(apiBase, `/live/history/${encodeURIComponent(runId)}`, controller.current.signal);
      if (ticket !== generation.current) return;
      if (value.run_id !== runId || !value.read_only || !value.actions_disabled || value.model_calls_enabled !== false) throw new Error(text('The archive did not return the requested read-only scope.', '归档没有返回所请求的只读范围。'));
      setDetail(value);
    } catch (issue) { if (ticket === generation.current && !(issue instanceof Error && issue.name === 'AbortError')) setError(issue instanceof Error ? issue.message : String(issue)); }
    finally { if (ticket === generation.current) setBusy(false); }
  }
  const versionOptions = detail?.analysis_versions.map((item, index) => ({ ...item, key: JSON.stringify([item.analysis_id, item.analysis_source, item.attached_at, index]) })) ?? [];
  const version = versionOptions.find(item => item.key === versionId);
  const records = detail?.snapshot?.case.observations ?? [];
  const byId = new Map(records.map(row => [row.id, row]));
  const archiveScope: EvidenceScope | null = detail?.snapshot_id && detail.snapshot ? { scope_kind: 'archive', run_id: detail.run_id, snapshot_id: detail.snapshot_id, analysis_id: version?.analysis_id ?? null, analysis_source: version?.analysis_source ?? null } : null;
  return <section className="at-live-panel at-live-history" aria-labelledby="at-live-history-title"><div className="at-live-section-heading"><span className="at-eyebrow">{text('Archive / read only', '归档 / 只读')}</span><h2 id="at-live-history-title">{text('Reopen the evidence, not the action.', '重新核查证据，不恢复执行。')}</h2><p className="at-fine-print">{text('Saved live investigations survive a restart. Opening an archive does not restore consent, resume checks, create customer requests, or call a model.', '已保存的实时调查可在重启后查看。打开归档不会恢复授权、继续检查、产生客户请求或调用模型。')}</p></div>
    <button className="at-button at-button-small" onClick={() => { setError(''); load(); }}>{text('Refresh saved investigations', '刷新已保存调查')}</button>
    {error && <p className="at-error" role="alert">{error}</p>}
    {!history && !error && <p className="at-fine-print">{text('Reading saved investigation index…', '正在读取已保存调查索引…')}</p>}
    {history?.entries.length === 0 && <p className="at-live-empty">{text('No persisted live investigations in this workspace yet.', '此工作区尚无已保存的实时调查。')}</p>}
    {history && <div className="at-live-history-layout"><nav className="at-live-history-index" aria-label={text('Saved live investigations', '已保存实时调查')}>{history.entries.map(entry => <button className="at-live-history-entry" key={entry.run_id} aria-pressed={entry.run_id === selectedRun} onClick={() => open(entry.run_id)}><span>{entry.journey} <small>{entry.status === 'completed' ? text('Recorded lifecycle completed', '记录生命周期已结束') : entry.status === 'unresolved' ? text('Recorded lifecycle unresolved', '记录生命周期未解决') : text('Archive incomplete', '归档不完整')}</small></span><strong className="at-mono">{entry.run_id}</strong><time>{entry.opened_at}</time><small>{entry.record_count} {text('records', '条记录')} · {entry.recovery_check_count} {text('recovery checks', '次恢复检查')}</small></button>)}</nav>
      <div className="at-live-history-detail" aria-busy={busy}>{busy ? <p className="at-fine-print" role="status">{text('Reading the selected archive…', '正在读取所选归档…')}</p> : !detail ? <p className="at-live-empty">{text('Select a saved investigation to inspect its original records.', '选择已保存调查，核查其原始记录。')}</p> : <><div className="at-live-scope-strip"><span className="at-outline-badge">{text('Archive only · actions disabled', '仅归档 · 禁止执行')}</span><span className="at-mono">{detail.run_id}</span></div>
        <dl><dt>{text('Recorded state / closure', '记录状态 / 结束记录')}</dt><dd>{detail.state} / {detail.closure.recorded ? text('Recovery recorded for this past incident', '此历史事件已记录恢复') : text('No closure event recorded', '尚无结束事件记录')}</dd><dt>{text('Original observation window', '原始观察窗口')}</dt><dd>{detail.snapshot ? `${detail.snapshot.case.start_time} → ${detail.snapshot.case.end_time}` : text('Original snapshot unavailable', '原始快照不可用')}</dd></dl><p className="at-live-warning">{text('A recorded closure describes this past incident only. It does not establish the platform’s present health.', '结束记录仅描述此历史事件，不能证明平台目前健康。')} {detail.closure.recorded && detail.closure.policy_revalidated !== true && text('Historical closure recorded; original verification policy unavailable. It has not been revalidated from this archive.', '已记录历史结束事件，但原始验证策略不可用，尚未根据此归档重新验证。')}</p>
        {detail.failure && <details><summary>{text('Original customer symptom', '原始客户症状')}</summary><p>{detail.failure.reason}</p><pre>{JSON.stringify(detail.failure, null, 2)}</pre></details>}
        <label className="at-live-version-label" htmlFor="at-live-archive-version">{text('Choose the preserved analysis version', '选择保留的分析版本')}</label><select id="at-live-archive-version" className="at-live-version-select" value={versionId} onChange={e => setVersionId(e.target.value)}><option value="">{text('Original evidence only', '仅原始证据')}</option>{versionOptions.map((item, index) => <option key={item.key} value={item.key}>{index + 1} · {analysisSourceLabel(item.analysis_source, text)} · {item.attached_at}</option>)}</select>
        {version && <div className="at-live-archived-analysis"><span className="at-outline-badge">{text('Preserved public response', '保留的公开结果')} · {analysisSourceLabel(version.analysis_source, text)}</span><h3>{version.analysis.candidate_service ?? text('No supported candidate', '无充分支持的候选')}</h3><p>{version.analysis.reason}</p>{version.analysis.uncertainty && <p className="at-live-warning">{version.analysis.uncertainty}</p>}{version.analysis.evidence_ids?.map(id => byId.get(id) ? <OriginalRecord key={id} row={byId.get(id)!} text={text} /> : <p className="at-live-warning" key={id}>{text('Citation absent from the original snapshot', '原始快照中缺少此引用')}: <span className="at-mono">{id}</span></p>)}<details><summary>{text('Saved public analysis', '已保存的公开分析')}</summary><p className="at-fine-print">{text('The analysis ID identifies the preserved original. This displayed JSON is its public projection, with private and non-public fields omitted.', '分析标识对应保留的原始结果。此处的 JSON 是其公开投影，省略了私有和非公开字段。')}</p><pre>{JSON.stringify(version.analysis, null, 2)}</pre></details></div>}
        {archiveScope ? <FrozenEvidenceWorkspace key={`${archiveScope.run_id}:${archiveScope.snapshot_id}:${versionId || 'evidence-only'}`} apiBase={apiBase} scope={archiveScope} records={records} text={text} /> : <p className="at-live-warning">{text('The original frozen snapshot is missing or invalid. Evidence comparison is unavailable for this archive.', '原始冻结快照缺失或无效，此归档无法进行证据比较。')}</p>}
        <details className="at-live-archived-recovery"><summary>{text('Later recovery records · separate from original evidence', '后续恢复记录 · 与原始证据分开')} ({detail.recovery_checks.length})</summary>{detail.recovery_checks.map((check, index) => <div key={`${check.checked_at}-${index}`}><strong>{check.passed ? text('Passed this recorded check', '此记录检查通过') : text('Recovery not established by this check', '此检查未证明恢复')}</strong><time>{check.checked_at}</time><p className="at-mono">{check.errors.join('; ') || text('No recorded blockers', '无已记录阻断项')}</p><details><summary>{text('Saved recovery receipt', '已保存恢复记录')}</summary><pre>{JSON.stringify(check, null, 2)}</pre></details></div>)}</details>
        {(detail.errors.length > 0 || detail.limitations.length > 0) && <details open><summary>{text('Archive gaps and limitations', '归档缺口与限制')}</summary><ul>{[...detail.errors, ...detail.limitations].map((item, index) => <li key={index}>{item}</li>)}</ul></details>}
      </>}</div></div>}
    {history?.truncated && <p className="at-fine-print">{text('This bounded index is truncated; it does not list every saved incident.', '此限定索引已截断，不包含所有已保存事件。')}</p>}
  </section>;
}

export function LiveDesk({ apiBase, host }: { apiBase: string; host: 'standalone' | 'grafana' }) {
  const [lang, setLang] = useState<Language>('en');
  const [data, setData] = useState<LiveStatus | null>(null);
  const [journey, setJourney] = useState('product_catalog');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [evidenceService, setEvidenceService] = useState('payment');
  const [actionId, setActionId] = useState(LOCAL_ACTIONS[0]);
  const [mode, setMode] = useState<ExecutionMode>('human_approved');
  const [approved, setApproved] = useState(false);
  const [automaticChecks, setAutomaticChecks] = useState(true);
  const zh = lang === 'zh';
  const text = (en: string, cn: string) => zh ? cn : en;
  const historyOnly = data?.mode === 'history_only_archive';
  useEffect(() => {
    const controller = new AbortController();
    request<LiveStatus>(apiBase, '/live/status', controller.signal).then(setData)
      .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [apiBase]);
  useEffect(() => { setSelectedIds([]); setReason(''); }, [data?.incident.snapshot_id]);
  useEffect(() => {
    const next = data?.incident.journey === 'product_images' ? LOCAL_ACTIONS[1] : LOCAL_ACTIONS[0];
    setActionId(next); setEvidenceService(data?.action_catalog?.[next]?.target_service ?? (next === LOCAL_ACTIONS[1] ? 'frontend-proxy' : 'payment'));
  }, [data?.incident.snapshot_id, data?.incident.journey]);
  useEffect(() => { setApproved(false); }, [data?.incident.proposal?.proposal_id, mode]);
  useEffect(() => {
    if (!ACTIVE_VERIFICATION.includes(data?.automatic_verification?.state ?? '')) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      request<LiveStatus>(apiBase, '/live/status', controller.signal).then(setData)
        .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message); });
    }, 5000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [apiBase, data?.automatic_verification?.state]);
  async function act(action: 'observe' | 'analyze' | 'propose' | 'execute' | 'verify' | 'status') {
    if (historyOnly && action !== 'status') { setError(text('This archive preview is read only. Live operations are disabled.', '此归档预览为只读，实时操作已禁用。')); return; }
    setBusy(true); setError('');
    let body: unknown;
    if (action === 'observe') body = { journey, product_id: '0PUK6V6EV0' };
    if (action === 'analyze') body = { snapshot_id: data?.incident.snapshot_id };
    if (action === 'propose') body = { snapshot_id: data?.incident.snapshot_id, action_id: actionId, reason: reason.trim(), evidence_ids: selectedIds };
    if (action === 'execute') body = { proposal_id: data?.incident.proposal?.proposal_id, mode, approved, verify_automatically: automaticChecks };
    if (action === 'verify') body = {};
    try {
      setData(await request<LiveStatus>(apiBase, `/live/${action}`, undefined, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      try { setData(await request<LiveStatus>(apiBase, '/live/status')); } catch { /* Keep the original failure visible. */ }
    }
    finally { setBusy(false); }
  }
  const latest = data?.latest;
  const source = latest?.snapshot;
  const incident = data?.incident;
  const analysis = incident?.analysis;
  const proposal = incident?.proposal;
  const frozenRecords = incident?.snapshot?.case.observations ?? [];
  const byId = useMemo(() => new Map(frozenRecords.map(row => [row.id, row])), [frozenRecords]);
  const selectedAction = data?.action_catalog?.[actionId];
  const availableActions = LOCAL_ACTIONS.filter(id => data?.action_catalog?.[id] && (!data.action_catalog[id].allowed_journeys || data.action_catalog[id].allowed_journeys!.includes(incident?.journey ?? '')));
  const targetService = selectedAction?.target_service ?? (actionId === LOCAL_ACTIONS[1] ? 'frontend-proxy' : 'payment');
  const services = [...new Set([targetService, ...frozenRecords.map(row => row.service)])].sort();
  const visibleRecords = frozenRecords.filter(row => evidenceService === 'all' || row.service === evidenceService);
  const selectedHasTarget = selectedIds.some(id => byId.get(id)?.service === targetService);
  const canPropose = !historyOnly && incident?.state === 'analysis_ready' && data?.restoration_enabled && availableActions.includes(actionId);
  const canExecute = !historyOnly && incident?.state === 'awaiting_approval' && data?.restoration_enabled
    && LOCAL_ACTIONS.includes(proposal?.action_id ?? '') && proposal?.snapshot_id === incident.snapshot_id;
  const verificationRunning = ACTIVE_VERIFICATION.includes(data?.automatic_verification?.state ?? '');
  const canVerify = !historyOnly && ['verifying_recovery', 'verification_failed'].includes(incident?.state ?? '') && data?.restoration_enabled && !verificationRunning;
  const checks = incident?.verification ?? [];
  const lastCheck = checks[checks.length - 1];
  const tail = [...checks].reverse().findIndex(check => !check.passed);
  const consecutiveChecks = tail === -1 ? checks.length : tail;
  const displayedJourney = incident?.snapshot_id && incident.state !== 'resolved'
    ? incident.journey ?? latest?.customer.journey ?? journey : journey;
  const recoveryJourney = incident?.journey ?? latest?.customer.journey ?? displayedJourney;
  const hasIncident = Boolean(incident?.snapshot_id) && incident?.state !== 'idle';
  const hasActionContext = Boolean(proposal || incident?.execution || (analysis && availableActions.includes(actionId)));
  const accountingUnavailable = data?.model_accounting?.availability === 'unavailable' || (Boolean(data) && data?.model_attempts == null);
  const currentScope: EvidenceScope | null = incident?.run_id && incident.snapshot_id ? {
    scope_kind: 'current', run_id: incident.run_id, snapshot_id: incident.snapshot_id,
    analysis_id: incident.analysis_id ?? null, analysis_source: incident.analysis_source ?? null,
  } : null;
  function toggleEvidence(id: string) { setSelectedIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]); }
  function citation(id: string) {
    const row = byId.get(id);
    const url = row && safeSource(row.source_url);
    return <details className="at-live-citation" key={id}><summary><span className="at-mono">{id}</span><small>{row ? `${row.service} · ${row.kind}` : text('Outside frozen input', '不在冻结输入中')}</small></summary>{row && <><p>{row.summary}</p><small>{row.timestamp}</small><pre>{JSON.stringify(row.raw, null, 2)}</pre>{url && <a href={url} target="_blank" rel="noopener noreferrer">{text('Open original source', '打开原始来源')} ↗</a>}</>}</details>;
  }
  const actualTrace = latest && source?.coverage.observed_customer_trace_ids?.includes(latest.customer.trace_id);
  const phases = [
    [text('Customer request', '客户操作'), Boolean(latest)],
    [text('Backend evidence', '后台证据'), Boolean(source?.case.observations.length)],
    [text('Evidence review', '证据分析'), Boolean(data?.incident.analysis)],
    [text('Approved action', '授权处理'), data?.incident.execution?.outcome === 'confirmed'],
    [text('Verified recovery', '验证恢复'), data?.incident.state === 'resolved'],
  ] as const;
  return <div className={`at-workbench at-live-desk at-host-${host}`} lang={zh ? 'zh-CN' : 'en'} aria-busy={busy}>
    <header className="at-topbar"><div className="at-brand">AutoTriager<span className="at-brand-sub">{text('Live incident desk', '实时事件工作台')}</span></div><span className="at-outline-badge">{text('Local testbed', '本地仿真平台')}</span><div className="at-language"><button className={!zh ? 'active' : ''} onClick={() => setLang('en')}>EN</button><button className={zh ? 'active' : ''} onClick={() => setLang('zh')}>中文</button></div></header>
    <main className="at-live-main">
      <div className="at-product-heading"><span className="at-eyebrow">{text('Observe → investigate → act → verify', '观测 → 调查 → 处理 → 验证')}</span><h1>{historyOnly ? text('Inspect the preserved customer outcome.', '核查保留的客户结果。') : text('Follow the customer outcome.', '从客户结果确认问题是否解决。')}</h1><p>{historyOnly ? text('Preserved original evidence, analysis versions and later recovery receipts. Live operations remain disabled in this preview.', '保留的原始证据、分析版本及后续恢复记录。此预览中的实时操作保持禁用。') : text('Actual customer requests and new backend records. An action alone cannot close an incident.', '实际客户请求与新的后台记录。完成一次操作，不等于故障已经恢复。')}</p></div>
      {historyOnly && <p className="at-live-warning at-live-history-only-banner" role="status">{text('Read-only archive preview. Live observation, model calls, customer orders, restoration and recovery checks are disabled. Recorded outcomes do not describe current platform health.', '只读归档预览。实时观察、模型调用、客户订单、恢复操作和恢复检查均已禁用。已记录结果不能说明平台当前健康状况。')}</p>}
      {!historyOnly && <>
      <ol className="at-live-phases">{phases.map(([label, complete], index) => <li className={complete ? 'complete' : ''} key={label}><span>{String(index + 1).padStart(2, '0')}</span><strong>{label}</strong><small>{complete ? text('Observed', '已观察') : text('Pending', '待完成')}</small></li>)}</ol>
      <section className="at-live-controls"><div><span className="at-eyebrow">{text('Customer journey', '客户操作路径')}</span><label htmlFor="at-live-journey">{text('Choose a local check', '选择本地检查')}</label><select id="at-live-journey" value={displayedJourney} disabled={busy || Boolean(data?.incident.snapshot_id && incident?.state !== 'resolved')} onChange={e => setJourney(e.target.value)}><option value="product_catalog">{text('Browse product catalog', '浏览商品目录')}</option><option value="product_images">{text('Load a catalog image in the storefront', '在购物前端加载商品图片')}</option><option value="checkout">{text('Place a synthetic order', '提交仿真订单')}</option></select></div><button className="at-button at-button-primary" disabled={historyOnly || busy || verificationRunning} onClick={() => act('observe')}>{busy ? text('Working…', '正在处理…') : text('Check customer + backend', '检查客户与后台')}</button><a className="at-button" href="http://127.0.0.1:8080/" target="_blank" rel="noopener noreferrer">{text('Open Astronomy Shop', '打开购物平台')} ↗</a><button className="at-button" disabled={busy} onClick={() => act('status')}>{text('Refresh recorded status', '刷新已记录状态')}</button></section>
      <p className="at-fine-print">{text('Checks run only when requested. Order checks use an isolated synthetic customer and create a local test order. A successful probe is not proof that every platform function is healthy.', '点击后才进行检查。订单检查使用隔离的仿真用户并产生本地测试订单；单条路径成功不能证明整个平台健康。')}</p>
      {error && <div className="at-error" role="alert">{error}</div>}
      <div className="at-live-columns">
        <section className="at-live-card"><span className="at-eyebrow">01 / {text('Customer result', '客户结果')}</span><h2>{!latest ? text('No live check yet', '尚未进行实时检查') : latest.customer.business_success ? text('Selected journey succeeded', '选定操作成功') : latest.customer.status === 'unavailable' ? text('Customer source unavailable', '客户数据源不可用') : latest.customer.status === 'degraded' ? text('Selected journey is too slow', '选定操作耗时过长') : text('Selected journey failed', '选定操作失败')}</h2>{latest && <><p>{latest.customer.reason}</p><dl><dt>{text('Observed at', '观察时间')}</dt><dd>{latest.customer.checked_at}</dd>{latest.customer.journey === 'product_images' && <><dt>{text('Image request duration / threshold', '图片请求耗时 / 阈值')}</dt><dd>{(latest.customer.elapsed_ms ?? latest.customer.duration_ms)?.toFixed(1) ?? '—'} ms / {latest.customer.image_threshold_ms ?? 1500} ms</dd><dt>{text('Actual storefront image displayed', '购物前端实际显示图片')}</dt><dd>{latest.customer.browser_image_displayed ? text('Observed', '已观察') : text('Not established', '尚未确认')}</dd></>}<dt>{text('Trace correlation', '请求追踪关联')}</dt><dd>{actualTrace ? text('Request trace observed in backend', '后台已观察到此请求') : text('Not yet confirmed', '尚未确认')}</dd></dl><details><summary>{text('Actual request outcomes', '实际请求结果')}</summary><pre>{JSON.stringify(latest.customer, null, 2)}</pre></details></>}</section>
        <section className="at-live-card"><span className="at-eyebrow">02 / {text('Backend evidence', '后台证据')}</span><h2>{source ? `${source.case.observations.length} ${text('preserved observations', '条保留记录')}` : latest?.collection_error ? text('Backend collection failed', '后台采集失败') : text('Waiting for a check', '等待检查')}</h2>{latest?.collection_error && <p className="at-live-warning" role="status">{latest.collection_error}</p>}{source && <><dl><dt>{text('Metrics / traces', '指标 / 调用追踪')}</dt><dd>{source.freshness.metrics.status} / {source.freshness.spans.status}</dd><dt>{text('Source age', '源数据年龄')}</dt><dd>{source.freshness.metrics.age_seconds?.toFixed(1) ?? '—'}s / {source.freshness.spans.age_seconds?.toFixed(1) ?? '—'}s</dd><dt>{text('Coverage', '覆盖范围')}</dt><dd>{source.freshness.overall} · {source.coverage.scope_limited ? text('bounded sample', '有采样限制') : text('queried scope', '已查询范围')}</dd></dl><p className="at-fine-print">{text('Additional log coverage', '补充日志覆盖')}: {source.coverage.logs}</p><details><summary>{text('Preserved telemetry', '保留的遥测证据')}</summary><pre>{JSON.stringify(source, null, 2)}</pre></details></>}</section>
        <section className="at-live-card"><span className="at-eyebrow">03 / {text('Incident handling', '事件处理')}</span><h2>{data?.incident.state ?? text('Connecting', '正在连接')}</h2><dl><dt>{text('Fresh model attempts', '新的模型调用')}</dt><dd>{data ? data.model_attempts == null ? text('Unknown', '未知') : data.model_attempts : '—'} / {data?.model_budget ?? '—'}</dd><dt>{text('Local alert', '本地告警')}</dt><dd>{data?.incident.alert?.state ?? text('No incident opened', '尚未建立事件')}</dd><dt>{text('Local restoration adapter', '本地恢复执行器')}</dt><dd>{data?.restoration_enabled ? text('Connected; approval required', '已接入，执行需要授权') : text('Disabled', '未启用')}</dd></dl><button className="at-button" disabled={historyOnly || busy || accountingUnavailable || !data?.model_calls_enabled || incident?.state !== 'evidence_ready'} onClick={() => act('analyze')}>{text('Analyze this live incident', '分析此实时事件')}</button>{accountingUnavailable && <p className="at-live-warning">{text('Model accounting is unavailable. New model calls are blocked until its state can be verified.', '模型调用记录暂不可用。在确认其状态前，新的模型调用已阻止。')}</p>}<p className="at-fine-print">{text('Fresh model calls require an authorized budget. An exact-request cached result is labeled as reuse, never a new model call.', '新的模型调用需要授权额度。同一请求的缓存结果会明确标为复用，不会计为新的模型调用。')}</p>{incident?.snapshot_id && <p className="at-fine-print">{text('Analysis stays bound to the original incident snapshot. Newer observations do not silently change its conclusion.', '分析绑定原事件快照；新观测不会自动改变该结论。')} <span className="at-mono">{incident.snapshot_id.slice(0, 12)}</span></p>}</section>
      </div>

      <section className="at-live-panel at-live-evidence-workspace" aria-labelledby="at-live-evidence-title"><div className="at-live-section-heading"><span className="at-eyebrow">{text('Investigation / original evidence', '调查 / 原始证据')}</span><h2 id="at-live-evidence-title">{text('Compare the components before choosing a next step.', '先比较组件证据，再选择下一步。')}</h2></div>{currentScope ? <FrozenEvidenceWorkspace key={`${currentScope.run_id}:${currentScope.snapshot_id}:${currentScope.analysis_id ?? 'evidence-only'}:${currentScope.analysis_source ?? 'none'}`} apiBase={apiBase} scope={currentScope} records={frozenRecords} text={text} /> : <p className="at-live-empty">{text('A captured failing journey opens the original evidence workspace. Latest observations are shown separately above.', '捕获失败的客户操作后，才会建立原始证据工作区。最新观测单独展示在上方。')}</p>}</section>

      <div className="at-live-investigation">
        <section className="at-live-panel" aria-labelledby="at-analysis-title">
          <div className="at-live-section-heading"><span className="at-eyebrow">04 / {text('Review the explanation', '核查分析解释')}</span><h2 id="at-analysis-title">{text('A hypothesis with inspectable evidence.', '可检查证据的故障假设。')}</h2></div>
          {!analysis ? <div className="at-live-empty"><p>{text('No analysis attached to this incident.', '此事件尚未附加分析。')}</p><small>{text('An observed failing journey provides the frozen input. Fresh model analysis requires an authorized budget.', '实际失败的操作提供冻结输入。新的模型分析需要授权额度。')}</small></div> : <>
            <span className="at-outline-badge">{analysisSourceLabel(incident?.analysis_source, text)}</span>
            <dl><dt>{text('Candidate service', '候选服务')}</dt><dd className="at-live-candidate">{analysis.candidate_service ?? text('No supported candidate', '无充分支持的候选')}</dd><dt>{text('Reason', '理由')}</dt><dd>{analysis.reason ?? text('No explanation supplied', '尚未提供解释')}</dd><dt>{text('Decision status', '判断状态')}</dt><dd>{analysis.status ?? '—'}</dd></dl>
            <p className="at-live-warning">{text('This is an investigation hypothesis. Inspectable records do not prove causality or that an action will work.', '这是调查假设。可检查的记录不能证明因果关系或操作有效。')}</p>
            {Boolean(analysis.missing_evidence?.length) && <><h3>{text('Still needed', '还缺哪些证据')}</h3><ul>{analysis.missing_evidence!.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
            {analysis.uncertainty && <p>{analysis.uncertainty}</p>}
            <h3>{text('Cited records from the incident snapshot', '原事件快照中的引用记录')}</h3>
            {analysis.evidence_ids?.length ? analysis.evidence_ids.map(citation) : <p className="at-fine-print">{text('No cited records. This explanation cannot support an action on its own.', '没有引用记录，此解释本身不能支持执行操作。')}</p>}
            {analysis.next_step && <section className="at-live-next-step"><span className="at-eyebrow">{text('Suggested next check', '建议的下一步检查')}</span><h3>{analysis.next_step.label ?? text('Inspect the available evidence', '核查已有证据')}</h3>{Boolean(analysis.next_step.instructions?.length) && <ol>{analysis.next_step.instructions!.map((item, index) => <li key={index}>{item}</li>)}</ol>}<p className="at-fine-print">{text('A policy suggestion derived from the validated candidate; not a model-generated command or proof of a correct repair.', '这是根据候选结果生成的策略建议，并非模型生成的命令，也不证明修复正确。')} {analysis.next_step.basis}</p></section>}
            <details><summary>{text('Preserved analysis response', '保留的分析结果')}</summary><pre>{JSON.stringify(analysis, null, 2)}</pre></details>
          </>}
        </section>

        <section className="at-live-panel" aria-labelledby="at-action-title">
          <div className="at-live-section-heading"><span className="at-eyebrow">05 / {text('Authorize one bounded action', '授权一次限定操作')}</span><h2 id="at-action-title">{text('Review before the local change.', '本地修改前先核查。')}</h2></div>
          <div className="at-live-action-scope"><strong>{hasActionContext ? proposal?.label ?? selectedAction?.label ?? text('Local configuration restoration', '本地配置恢复') : text('Available after compatible evidence and a reviewed proposal', '在证据匹配并核查提案后可用')}</strong><p>{hasActionContext ? proposal?.effect ?? selectedAction?.effect : text('No action is proposed. Observe a compatible failing journey, then review its evidence before preparing a bounded local change.', '当前没有操作提案。先观察匹配的失败操作，再核查证据并准备限定的本地修改。')}</p><small>{text('Controlled experimental restoration, not proof of learned repair capability.', '这是受控实验恢复，不能证明模型学会了修复故障。')}</small></div>
          {!proposal && !incident?.execution && hasIncident && <div className="at-live-action-form">
            <label htmlFor="at-action-target">{text('Allowlisted local action', '允许的本地操作')}</label><select id="at-action-target" value={actionId} disabled={busy || !canPropose} onChange={e => { setActionId(e.target.value); setEvidenceService(data?.action_catalog[e.target.value]?.target_service ?? 'all'); setSelectedIds([]); setReason(''); setApproved(false); }}>{availableActions.length ? availableActions.map(id => <option key={id} value={id}>{data?.action_catalog[id].label}</option>) : <option value={actionId}>{text('No compatible action available', '没有可用的匹配操作')}</option>}</select>
            <label htmlFor="at-action-reason">{text('Your reason for this action', '你支持此操作的理由')}</label><textarea id="at-action-reason" value={reason} maxLength={1000} disabled={busy || !canPropose} onChange={e => setReason(e.target.value)} placeholder={text('Explain what the evidence supports and what remains uncertain.', '说明证据支持什么，以及还有哪些不确定之处。')} />
            <div className="at-live-evidence-heading"><label htmlFor="at-evidence-service">{text('Choose supporting incident records', '选择支持操作的原事件记录')}</label><select id="at-evidence-service" value={evidenceService} disabled={busy || !canPropose} onChange={e => setEvidenceService(e.target.value)}><option value="all">{text('All services', '全部服务')}</option>{services.map(service => <option key={service} value={service}>{service}</option>)}</select></div>
            <p className="at-fine-print">{text('Frozen incident records, not the latest observation. Include a record for the stated target; selecting it does not establish action correctness.', '这里是冻结的原事件记录，不是最新观测。至少选择一条目标服务记录；选中记录不证明操作正确。')} {text('Target', '目标')}: {targetService}</p>
            <div className="at-live-evidence-picker">{visibleRecords.length ? visibleRecords.map(row => <label className={`at-live-evidence-option ${selectedIds.includes(row.id) ? 'selected' : ''}`} key={row.id}><input type="checkbox" checked={selectedIds.includes(row.id)} disabled={busy || !canPropose} onChange={() => toggleEvidence(row.id)} /><span><span className="at-mono">{row.id}</span><small>{row.service} · {row.kind} · {row.timestamp}</small><span>{row.summary}</span></span></label>) : <p className="at-fine-print">{text('No incident records for this service yet.', '尚无此服务的原事件记录。')}</p>}</div>
            <p className="at-fine-print">{selectedIds.length} {text('selected', '条已选择')} · {selectedHasTarget ? text('Target record included', '已包含目标服务记录') : text('Target record still required', '仍需要目标服务记录')}</p>
            <button className="at-button" disabled={busy || !canPropose || !reason.trim() || !selectedHasTarget} onClick={() => act('propose')}>{text('Prepare this local proposal', '准备此本地操作提案')}</button>
            {!canPropose && <p className="at-fine-print">{!data?.restoration_enabled ? text('A verified local executor must be connected before any action can be prepared.', '经过验证的本地执行器接入前，不能准备执行操作。') : text('Review an incident analysis before preparing the proposal.', '先核查事件分析，再准备操作提案。')}</p>}
          </div>}
          {proposal && <div className="at-live-proposal"><span className="at-eyebrow">{text('Exact proposal', '本次具体提案')}</span><p className="at-mono">{proposal.proposal_id}</p><dl><dt>{text('Target / snapshot', '目标 / 快照')}</dt><dd>{proposal.target_service} / <span className="at-mono">{proposal.snapshot_id.slice(0, 12)}</span></dd><dt>{text('Justification', '理由')}</dt><dd>{proposal.reason}</dd><dt>{text('Supporting records', '支持记录')}</dt><dd>{proposal.evidence_ids.join(', ')}</dd></dl>
            {!incident?.execution && <div className="at-live-approval"><label htmlFor="at-execution-mode">{text('Execution mode', '执行模式')}</label><select id="at-execution-mode" value={mode} disabled={busy || !canExecute} onChange={e => setMode(e.target.value as ExecutionMode)}><option value="human_approved">{text('Execute after my approval', '经我批准后执行')}</option><option value="incident_authorized_auto">{text('Authorize this one local automatic action', '授权此次单一本地自动操作')}</option></select><p className="at-fine-print">{mode === 'human_approved' ? text('The adapter executes after your click. This does not record a manually performed engineer action.', '点击后由执行器执行，不会将其记录为工程师手工完成的操作。') : text('One action for this incident only. No recurring actions, new commands, or unrestricted model execution.', '仅针对本事件的一次操作，不包含重复执行、新命令或无限制模型执行。')}</p>
              <label className="at-live-consent"><input type="checkbox" checked={automaticChecks} disabled={busy || !canExecute} onChange={e => { setAutomaticChecks(e.target.checked); setApproved(false); }} /><span>{text('After execution, automatically repeat this customer journey and its declared backend checks: at most 6 checks over 5 minutes. Order journeys create local test orders. No model calls.', '执行后自动重复当前客户操作及其规定的后台检查：5 分钟内最多 6 次；订单操作会产生本地测试订单，不调用模型。')}</span></label>
              <label className="at-live-consent"><input type="checkbox" checked={approved} disabled={busy || !canExecute} onChange={e => setApproved(e.target.checked)} /><span>{text('I reviewed this exact proposal and authorize its stated local change and selected verification mode for this incident.', '我已核查此具体提案，并授权对此事件执行所述本地修改及所选验证模式。')}</span></label>
              <button className="at-button at-button-primary" disabled={busy || !canExecute || !approved} onClick={() => act('execute')}>{text('Execute this approved proposal', '执行此已授权提案')}</button>
            </div>}
          </div>}
          {incident?.execution && <div className="at-live-execution"><strong>{text('Action outcome', '操作结果')}: {incident.execution.outcome}</strong><p>{incident.execution.completed_at}</p><p className="at-fine-print">{text('This receipt confirms the local change only. Customer recovery and new backend evidence still determine whether the incident closes.', '此记录仅确认本地修改；客户恢复和新后台证据仍需共同决定事件是否结束。')}</p></div>}
        </section>
      </div>

      <section className={`at-live-panel at-live-recovery-panel ${incident?.state === 'resolved' ? 'resolved' : ''}`} aria-labelledby="at-recovery-title">
        <div className="at-live-section-heading"><span className="at-eyebrow">06 / {text('Verify the result', '验证实际结果')}</span><h2 id="at-recovery-title">{incident?.state === 'resolved' ? text('This recorded incident was verified recovered.', '此记录中的事件已验证恢复。') : text('Keep the incident open until recovery is observed.', '观察到恢复后，再结束事件。')}</h2>{incident?.run_id && <p className="at-fine-print">{text('Incident', '事件')}: <span className="at-mono">{incident.run_id}</span></p>}{incident?.state === 'resolved' && latest?.customer.business_success === false && <p className="at-live-warning">{text('The latest customer check failed. The earlier incident’s closure does not establish recovery of this new observation.', '最新客户检查失败。此前事件的结束记录不证明此新观测已恢复。')}</p>}</div>
        <div className="at-live-recovery-grid"><div><p>{text('A new request must succeed within this journey’s declared criteria, its exact trace must appear on the affected backend path, declared backend checks must pass, and unrelated controls must remain unchanged.', '新的客户请求必须满足当前操作的成功标准，后台必须观察到对应路径的精确请求追踪，规定的后台检查必须通过，其他配置必须保持不变。')}</p><p className="at-fine-print">{text('Historical errors stay in the record. Only this declared local customer-path alert stops; the whole platform is not certified healthy.', '历史错误会保留，仅停止已声明的本地客户路径告警，不代表整个系统已通过健康认证。')}</p><button className="at-button at-button-primary" disabled={busy || !canVerify} onClick={() => act('verify')}>{text('Run a fresh recovery check', '进行一次新的恢复检查')}</button>{verificationRunning && <p className="at-live-warning" role="status">{text('Bounded recovery checks running', '限定次数的恢复检查正在运行')}: {data?.automatic_verification?.state} · {data?.automatic_verification?.checks} / {data?.automatic_verification?.max_checks}<br />{text('Status refresh reads receipts only. It does not submit additional orders or model calls.', '状态刷新只读取记录，不额外提交订单或调用模型。')}</p>}</div><div className="at-live-recovery-rule"><strong>{consecutiveChecks} / {incident?.policy?.min_successful_probes ?? 3} {text('consecutive passing checks', '次连续通过的检查')}</strong><p>{text('Sustained observation', '持续观察')}: {incident?.policy?.sustained_seconds ?? 60}s</p>{recoveryJourney === 'product_images' ? <><p>{text('Post-action observation window', '操作后的观察窗口')}: {incident?.policy?.metric_lookback_seconds ?? 120}s</p><ul className="at-live-family-gates"><li>{text('Selected storefront image rendered; its request completes within 1500 ms.', '选定的购物前端图片已显示，且其请求在 1500 毫秒内完成。')}</li><li>{text('Fresh matching proxy trace: OK and within 1500 ms. Matching image-route access record: HTTP 200 and within 1500 ms.', '新的匹配代理追踪：状态 OK、耗时不超过 1500 毫秒。匹配图片路径的访问记录：HTTP 200、耗时不超过 1500 毫秒。')}</li></ul></> : recoveryJourney === 'checkout' ? <><p>{text('Post-action metric window', '操作后的指标窗口')}: {incident?.policy?.metric_lookback_seconds ?? 120}s</p><ul className="at-live-family-gates"><li>{text('A new matching order and a successful trace on the affected checkout path.', '新的匹配订单，以及受影响结账路径中的成功调用追踪。')}</li><li>{text('Fresh scoped call rate, error fraction and p95 latency must pass the declared recovery policy.', '新的限定范围调用率、错误比例和 p95 延迟必须通过已声明的恢复策略。')}</li></ul></> : <p>{text('Recovery criteria appear for a recorded checkout or product-image incident.', '记录结账或商品图片事件后，会显示对应的恢复标准。')}</p>}<small>{text('Each passing check requires a full post-action observation window. A successful action does not dismiss the alert.', '每次通过的检查都需要完整的操作后观察窗口。操作成功不会直接消除告警。')}</small></div></div>
        {lastCheck && <div className="at-live-last-check"><strong>{lastCheck.passed ? text('Latest check passed; sustained recovery may still be pending.', '最新检查通过，但持续恢复可能仍待确认。') : text('Latest check did not establish recovery.', '最新检查尚未证明恢复。')}</strong><span>{lastCheck.checked_at}</span>{lastCheck.errors.length > 0 && <ul>{lastCheck.errors.map((item, index) => <li key={`${item}-${index}`} className="at-mono">{item}</li>)}</ul>}</div>}
        {checks.length > 0 && <details><summary>{text('All preserved recovery checks', '全部保留的恢复检查')}</summary><div className="at-live-check-history">{checks.map((check, index) => <div key={`${check.checked_at}-${index}`}><span>{String(index + 1).padStart(2, '0')}</span><time>{check.checked_at}</time><strong>{check.passed ? text('Passed this check', '此检查通过') : text('Not verified', '未验证')}</strong><small>{check.errors.join('; ') || text('No blockers in this check', '此检查没有阻断项')}</small></div>)}</div></details>}
      </section>
      </>}
      <LiveInvestigationHistory apiBase={apiBase} text={text} />
    </main>
  </div>;
}

export function InvestigationApp({ apiBase, host = 'standalone', historical }: { apiBase: string; host?: 'standalone' | 'grafana'; historical: React.ReactNode }) {
  const [live, setLive] = useState(new URLSearchParams(window.location.search).get('view') === 'live');
  return <><nav className="at-view-switch" aria-label="Investigation mode"><button aria-pressed={live} onClick={() => setLive(true)}>Live observation</button><button aria-pressed={!live} onClick={() => setLive(false)}>Historical evidence</button></nav>{live ? <LiveDesk apiBase={apiBase} host={host} /> : historical}</>;
}
