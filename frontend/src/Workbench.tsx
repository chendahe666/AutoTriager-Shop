import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, request, safeSource } from './api';
import { textFor, TextKey } from './i18n';
import { CaseResponse, CaseSummary, Catalog, Comparison, Decision, FollowUp, Kind, Language, Observation, ObservedLink, Query } from './types';
import { GraphRAGPanel } from './GraphRAGPanel';

type IconName = 'mark' | 'search' | 'arrow' | 'close' | 'check' | 'clock' | 'layers' | 'link' | 'chevron' | 'shield';
function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    mark: <><path d="M3 17 9 5h6l6 12M6.5 12h11"/><circle cx="12" cy="20" r="1"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
    layers: <><path d="m3 8 9-5 9 5-9 5-9-5Z"/><path d="m3 13 9 5 9-5M3 18l9 5 9-5"/></>,
    link: <><path d="m10 13 4-4M7 15l-1 1a4 4 0 0 1-5-5l5-5a4 4 0 0 1 5 0M17 9l1-1a4 4 0 0 1 5 5l-5 5a4 4 0 0 1-5 0"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>,
    shield: <><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function timestamp(value: string, lang: Language, short = false): string {
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return value;
  return new Intl.DateTimeFormat(lang === 'zh' ? 'zh-CN' : 'en-GB', {
    timeZone: 'UTC', ...(short ? {} : { year: 'numeric', month: 'short', day: '2-digit' }),
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(date);
}
function shortId(id: string): string { return id.length > 28 ? `${id.slice(0, 16)}…${id.slice(-8)}` : id; }
function KindMark({ kind }: { kind: Kind }) { return <span className={`at-kind-mark at-kind-${kind}`} aria-hidden="true">{kind === 'metric' ? '≋' : kind === 'span' ? '↳' : '≡'}</span>; }
function valueFor(row: Observation): string {
  const raw = row.raw;
  if (row.kind === 'span' && typeof raw.duration_ms === 'number') return `${raw.duration_ms.toLocaleString(undefined, { maximumFractionDigits: 3 })} ms`;
  if (row.kind === 'metric' && (typeof raw.value === 'number' || typeof raw.value === 'string')) return `${raw.value}${typeof raw.unit === 'string' ? ` ${raw.unit}` : ''}`;
  return String(raw.severity ?? raw.status ?? raw.status_code ?? '—');
}
function isError(row: Observation): boolean {
  const state = String(row.raw.status ?? row.raw.status_code ?? row.raw.severity ?? row.raw.severity_text ?? '').toUpperCase();
  return ['ERROR', 'STATUS_CODE_ERROR', 'FATAL', 'CRITICAL', 'SEVERE'].includes(state);
}

export function Workbench({ apiBase = '/api', host = 'standalone' }: { apiBase?: string; host?: 'standalone' | 'grafana' }) {
  const [lang, setLang] = useState<Language>('en');
  const t = textFor(lang);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [casesLoading, setCasesLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [caseId, setCaseId] = useState('');
  const [data, setData] = useState<CaseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [retry, setRetry] = useState(0);
  const [services, setServices] = useState<string[]>([]);
  const [kind, setKind] = useState<Kind | 'all'>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [originalLine, setOriginalLine] = useState<string | null>(null);
  const [originalLineError, setOriginalLineError] = useState('');
  const [contextStale, setContextStale] = useState(false);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [followup, setFollowup] = useState<FollowUp | null>(null);
  const [queryTarget, setQueryTarget] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [decision, setDecision] = useState<Decision>('uncertain');
  const [candidate, setCandidate] = useState('');
  const [reviewReason, setReviewReason] = useState('');
  const [reviewStatus, setReviewStatus] = useState('');
  const [reviewFile, setReviewFile] = useState('');
  const [savingReview, setSavingReview] = useState(false);
  const epoch = useRef(0);
  const actionSequence = useRef(0);
  const selectedServices = useRef<string[]>([]);
  const actionAbort = useRef<AbortController | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCasesLoading(true); setListError('');
    request<{ cases: CaseSummary[]; catalog?: Catalog }>(apiBase, '/cases', controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setCases(value.cases); setCatalog(value.catalog ?? null); setCaseId((previous) => value.cases.some((entry) => entry.case_id === previous) ? previous : (value.cases[0]?.case_id ?? '')); } })
      .catch((error: Error) => { if (error.name !== 'AbortError') setListError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setCasesLoading(false); });
    return () => controller.abort();
  }, [apiBase, retry]);

  useEffect(() => {
    const controller = new AbortController();
    epoch.current += 1; actionSequence.current += 1;
    actionAbort.current?.abort();
    selectedServices.current = [];
    setData(null); setLoadError(''); setServices([]); setKind('all'); setSearch(''); setPage(0);
    setSelectedId(null); setOriginalLine(null); setOriginalLineError(''); setContextStale(false); setComparison(null); setFollowup(null); setQueryTarget('');
    setActionError(''); setActionBusy(false); setDecision('uncertain'); setCandidate('');
    setReviewReason(''); setReviewStatus(''); setReviewFile(''); setSavingReview(false);
    if (!caseId) { setLoading(false); return () => controller.abort(); }
    setLoading(true);
    request<CaseResponse>(apiBase, `/cases/${encodeURIComponent(caseId)}`, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setData(value); setCandidate(value.analysis.candidates[0]?.service ?? ''); } })
      .catch((error: Error) => { if (error.name !== 'AbortError') setLoadError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [apiBase, caseId, retry]);

  useEffect(() => { setPage(0); }, [services, kind, search]);
  useEffect(() => {
    setOriginalLine(null); setOriginalLineError('');
    if (!selectedId || !data) return;
    const controller = new AbortController();
    request<{ original_line: string | null; snapshot_id: string }>(apiBase, `/cases/${encodeURIComponent(data.case.case_id)}/evidence/${encodeURIComponent(selectedId)}`, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (value.snapshot_id === data.snapshot_id) setOriginalLine(value.original_line);
        else { setOriginalLineError(t('sourceChanged')); setContextStale(true); }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setOriginalLineError(error instanceof Error ? error.message : t('apiError'));
        if (error instanceof ApiError && error.status === 409) setContextStale(true);
      });
    return () => controller.abort();
  }, [selectedId, data, apiBase]);

  const observations = data?.case.observations ?? [];
  const availableServices = useMemo(() => [...new Set(observations.map((row) => row.service))].sort(), [observations]);
  const counts = useMemo(() => Object.fromEntries(['metric', 'span', 'log'].map((item) => [item, observations.filter((row) => row.kind === item).length])) as Record<Kind, number>, [observations]);
  const citedIds = useMemo(() => new Set(data?.analysis.evidence.map((row) => row.id) ?? []), [data]);
  const modelIds = useMemo(() => data?.analysis.recorded ? new Set(data.analysis.recorded.selected_ids) : null, [data]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return observations.filter((row) => (!services.length || services.includes(row.service)) && (kind === 'all' || kind === row.kind)
      && (!query || `${row.id} ${row.service} ${row.summary} ${JSON.stringify(row.raw)}`.toLowerCase().includes(query)))
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp) || a.id.localeCompare(b.id));
  }, [observations, services, kind, search]);
  const pageSize = 12;
  const selectedRow = observations.find((row) => row.id === selectedId);
  const windowRows = filtered.slice(page * pageSize, (page + 1) * pageSize);

  function toggleService(service: string) {
    const next = services.includes(service) ? services.filter((item) => item !== service) : services.length < 3 ? [...services, service] : services;
    if (next === services) return;
    selectedServices.current = next; actionAbort.current?.abort(); actionSequence.current += 1;
    setServices(next); setComparison(null); setFollowup(null); setQueryTarget(''); setActionError(''); setActionBusy(false);
  }
  function clearScope() {
    selectedServices.current = []; actionAbort.current?.abort(); actionSequence.current += 1;
    setServices([]); setKind('all'); setSearch(''); setComparison(null); setFollowup(null); setQueryTarget(''); setActionError(''); setActionBusy(false);
  }
  function inspect(id: string) { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setSelectedId(id); }
  function closeRecord() { setSelectedId(null); returnFocus.current?.focus(); }

  async function runEvidenceAction(query?: Query) {
    if (!data || contextStale || services.length < 2 || services.length > 3) return;
    const actionEpoch = epoch.current;
    const sequence = ++actionSequence.current;
    actionAbort.current?.abort(); const controller = new AbortController(); actionAbort.current = controller;
    const components = [...services]; const currentCase = data.case.case_id;
    const payload = { components, snapshot_id: data.snapshot_id, analysis_id: data.analysis_id, ...(query ? { query, component: components.includes(queryTarget) ? queryTarget : components[0] } : {}) };
    setActionBusy(true); setActionError('');
    if (query) setFollowup(null);
    try {
      const value = query ? await request<FollowUp>(apiBase, `/cases/${encodeURIComponent(currentCase)}/follow-up`, controller.signal, payload)
        : await request<Comparison>(apiBase, `/cases/${encodeURIComponent(currentCase)}/compare`, controller.signal, payload);
      if (epoch.current !== actionEpoch || actionSequence.current !== sequence || controller.signal.aborted) return;
      if (query) setFollowup(value as FollowUp); else { const compared = value as Comparison; setComparison(compared); setQueryTarget(compared.components[0] ?? ''); setFollowup(null); }
    } catch (error) {
      if (epoch.current === actionEpoch && actionSequence.current === sequence && !controller.signal.aborted) { setActionError(error instanceof Error ? error.message : t('apiError')); if (error instanceof ApiError && error.status === 409) setContextStale(true); }
    } finally { if (epoch.current === actionEpoch && actionSequence.current === sequence) setActionBusy(false); }
  }

  async function saveReview(event: React.FormEvent) {
    event.preventDefault(); if (!data || savingReview || contextStale) return;
    if (!reviewReason.trim()) { setReviewStatus(t('needReason')); return; }
    if (decision !== 'uncertain' && !candidate) { setReviewStatus(t('needCandidate')); return; }
    const actionEpoch = epoch.current;
    setSavingReview(true); setReviewStatus(''); setReviewFile('');
    try {
      const value = await request<{ record: unknown; filename: string }>(apiBase, `/cases/${encodeURIComponent(data.case.case_id)}/reviews`, undefined, {
        snapshot_id: data.snapshot_id, analysis_id: data.analysis_id, decision, candidate_service: candidate || null, reason: reviewReason.trim(),
        selected_evidence_ids: selectedId ? [selectedId] : [], compared_components: comparison?.components ?? [],
      });
      if (epoch.current === actionEpoch) { setReviewStatus(t('reviewSaved')); setReviewFile(value.filename); }
    } catch (error) { if (epoch.current === actionEpoch) { setReviewStatus(error instanceof Error ? error.message : t('apiError')); if (error instanceof ApiError && error.status === 409) setContextStale(true); } }
    finally { if (epoch.current === actionEpoch) setSavingReview(false); }
  }

  const provenanceKey: TextKey = data?.case.provenance.source_kind === 'captured_shop' ? 'capturedShop' : data?.case.provenance.source_kind === 'captured_local_sim' ? 'localSim' : data?.case.provenance.source_kind === 'synthetic_fixture' ? 'fixture' : 'unknownSource';
  const supported = data?.analysis.status === 'supported';
  const displayedCandidate = data?.analysis.candidates.find((item) => item.service === candidate);
  const displayedEvidence = displayedCandidate ? (data?.analysis.evidence ?? []).filter((row) => displayedCandidate.evidence_ids.includes(row.id)) : [];
  const coverageText = catalog?.coverage_code === 'official_shop_pilot' ? t('pilotCoverage') : t('genericCoverage');
  const scopeNarrowed = services.length > 0 || kind !== 'all' || search.trim().length > 0;
  const unavailableFinding = loading || casesLoading ? t('loading') : loadError || listError ? t('error') : !cases.length ? t('noCases') : t('noFinding');
  const queries: { key: Query; label: TextKey }[] = [
    { key: 'component_records', label: 'showRecords' }, { key: 'observed_links', label: 'showLinks' }, { key: 'outside_recorded_input', label: 'showOutside' },
  ];

  return <div className={`at-workbench at-host-${host}`} lang={lang === 'zh' ? 'zh-CN' : 'en'}>
    <header className="at-topbar">
      <a className="at-brand" href={host === 'grafana' ? '/a/dahe-autotriager-app' : './'} aria-label="AutoTriager"><span className="at-logo"><Icon name="mark" size={25}/></span><span>AutoTriager<span className="at-brand-sub">{t('desk')}</span></span></a>
      <div className="at-header-center"><span className="at-dot"/>{t('recordedTelemetry')}<span className="at-header-separator"/>{t('readonly')}</div>
      <div className="at-language" role="group" aria-label="Language / 语言"><button onClick={() => setLang('en')} className={lang === 'en' ? 'active' : ''} aria-pressed={lang === 'en'}>EN</button><button onClick={() => setLang('zh')} className={lang === 'zh' ? 'active' : ''} aria-pressed={lang === 'zh'}>中文</button></div>
    </header>
    <div className="at-body-grid">
      <aside className="at-navigation" aria-label={t('caseLibrary')}>
        <div className="at-nav-title"><span className="at-eyebrow">01 / {t('caseLibrary')}</span><span className="at-count">{cases.length}</span></div>
        {casesLoading && <p className="at-muted">{t('loadingCases')}</p>}
        {listError && <div className="at-error" role="alert"><p>{listError}</p><button onClick={() => setRetry((value) => value + 1)}>{t('retry')}</button></div>}
        {!casesLoading && !listError && !cases.length && <p className="at-muted">{t('noCases')}</p>}
        <div className="at-case-list">{cases.map((entry, index) => <button key={entry.case_id} className={`at-case ${entry.case_id === caseId ? 'active' : ''}`} onClick={() => setCaseId(entry.case_id)} aria-pressed={entry.case_id === caseId}>
          <span className="at-case-number">{String(index + 1).padStart(2, '0')}</span><span className="at-case-content"><span className="at-case-name at-mono" title={entry.title}>{entry.case_id}</span><span className="at-case-meta">{timestamp(entry.start_time, lang)} UTC</span><span className="at-case-meta">{entry.observation_count} {t('records')}</span></span><Icon name="chevron" size={13}/>
        </button>)}</div>
        <div className="at-services-head"><span className="at-eyebrow">02 / {t('services')}</span>{services.length > 0 && <button className="at-text-button" onClick={clearScope}>{t('clear')}</button>}</div>
        <p className="at-nav-hint">{t('filterHint')}</p>
        <div className="at-service-list">{availableServices.map((service) => {
          const selected = services.includes(service); const count = observations.filter((row) => row.service === service).length;
          return <button key={service} className={`at-service ${selected ? 'active' : ''}`} onClick={() => toggleService(service)} disabled={!selected && services.length >= 3} aria-pressed={selected}><span className="at-checkbox">{selected && <Icon name="check" size={11}/>}</span><span>{service}</span><span className="at-service-count">{count}</span></button>;
        })}</div>
        <button className="at-button at-button-primary at-compare-button" disabled={services.length < 2 || actionBusy || !data || contextStale} onClick={() => runEvidenceAction()}><Icon name="layers"/>{actionBusy ? t('loadingAction') : t('compare')}<span>{services.length}/3</span></button>
        <div className="at-nav-footer"><Icon name="shield"/><span>{t('privacy')}</span></div>
      </aside>

      <main className="at-main">
        {loading && <div className="at-loading" role="status"><span className="at-loader"/><p>{t('loading')}</p></div>}
        {loadError && <div className="at-error at-main-error" role="alert"><h2>{t('error')}</h2><p>{loadError}</p><button className="at-button" onClick={() => setRetry((value) => value + 1)}>{t('retry')}</button></div>}
        {data && <>
          <section className="at-context" aria-label={t('dataScope')}>
            <div className="at-product-heading"><h1>{t('platformHeading')}</h1><p>{t('platformDescription')}</p></div>
            <div className="at-catalog-context"><div><span className="at-eyebrow">{t('currentMode')}</span><strong>{catalog?.mode === 'recorded_evidence' ? t('historicalMode') : t('unknownSource')}</strong></div><p><span>{t('currentCoverage')}</span>{coverageText}</p></div>
            <div className="at-context-overline"><span className="at-eyebrow">{t('dataScope')}</span><span className="at-mono at-case-id">{data.case.case_id}</span></div>
            {contextStale && <div className="at-stale-context" role="alert"><p>{t('staleContext')}</p><button className="at-button at-button-small" onClick={() => setRetry((value) => value + 1)}>{t('reloadIncident')}</button></div>}
            <div className="at-original-incident" aria-label={t('originalIncidentFields')}><span className="at-eyebrow">{t('selectedIncident')} · {t('originalTitle')}</span><h2>{data.case.title}</h2><span className="at-incident-field-label">{t('symptom')}</span><p className="at-symptom">{data.case.symptom}</p></div>
            <div className="at-context-meta"><span><Icon name="clock"/>{timestamp(data.case.start_time, lang)} — {timestamp(data.case.end_time, lang, true)} UTC</span><span><Icon name="layers"/>{t(provenanceKey)}</span></div>
            <details className="at-capture-details"><summary>{t('captureDetails')}</summary><dl><dt>{t('source')}</dt><dd>{data.case.provenance.source_kind ?? t('unknownSource')}</dd><dt>{t('repository')}</dt><dd>{safeSource(String(data.case.provenance.repository ?? '')) ? <a href={safeSource(String(data.case.provenance.repository))!} target="_blank" rel="noopener noreferrer">{String(data.case.provenance.repository)}</a> : String(data.case.provenance.repository ?? '—')}</dd><dt>{t('version')}</dt><dd>{String(data.case.provenance.version ?? '—')}</dd><dt>{t('collection')}</dt><dd>{String(data.case.provenance.collection_method ?? '—')}</dd><dt>{t('capturedAt')}</dt><dd>{data.case.provenance.captured_at ? `${timestamp(data.case.provenance.captured_at, lang)} UTC` : '—'}</dd><dt>{t('snapshot')}</dt><dd className="at-mono">{data.snapshot_id}</dd><dt>{t('analysisIdentity')}</dt><dd className="at-mono">{data.analysis_id}</dd></dl><details><summary>{t('captureMetadata')}</summary><pre>{JSON.stringify(data.case.provenance, null, 2)}</pre></details></details>
            <div className="at-scope-summary"><div><strong>{observations.length}</strong><span>{t('records')}</span></div><div><strong>{availableServices.length}</strong><span>{t('components')}</span></div><div><strong>{citedIds.size}</strong><span>{t('citations')}</span></div><p>{t('noLive')}</p></div>
          </section>
          <GraphRAGPanel key={`${data.case.case_id}:${data.snapshot_id}:${data.analysis_id}`} data={data} components={services} apiBase={apiBase} lang={lang} stale={contextStale} onStale={() => setContextStale(true)} onInspect={inspect}/>
          <section className="at-evidence-section" aria-label={t('workspace')}>
            <div className="at-section-heading"><div><span className="at-eyebrow">03 / {t('workspace')}</span><h2>{t('observations')}</h2></div><span className="at-caption">{scopeNarrowed ? t('filteredView') : t('allServices')}</span></div>
            <div className="at-evidence-toolbar"><div className="at-tabs" role="group" aria-label={t('capturedSignals')}>{(['all', 'metric', 'span', 'log'] as const).map((item) => <button key={item} className={kind === item ? 'active' : ''} aria-pressed={kind === item} onClick={() => setKind(item)}>{t(item)}<span>{item === 'all' ? observations.length : counts[item]}</span></button>)}</div><label className="at-search"><Icon name="search"/><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('search')} aria-label={t('search')}/></label></div>
            {scopeNarrowed && <div className="at-active-filters"><span>{services.length ? services.join(' + ') : t('allServices')}</span><span className="at-muted">{t('scopeChanges')}</span><button className="at-text-button" onClick={clearScope}>{t('resetView')}</button></div>}
            {kind === 'log' && counts.log === 0 ? <div className="at-empty"><KindMark kind="log"/><p>{t('noLogs')}</p></div> : filtered.length === 0 ? <div className="at-empty"><Icon name="search" size={23}/><p>{t('noRecords')}</p></div> : <>
              <div className="at-table-scroll"><table className="at-evidence-table"><thead><tr><th>{t('time')}</th><th>{t('service')}</th><th>{t('observation')}</th><th>{t('capturedValue')}</th><th aria-label={t('details')}></th></tr></thead><tbody>{windowRows.map((row) => <tr key={row.id} className={`${selectedId === row.id ? 'selected' : ''} ${isError(row) ? 'at-error-row' : ''}`}>
                <td className="at-time at-mono">{timestamp(row.timestamp, lang, true)}</td><td><span className="at-service-cell">{row.service}</span></td><td><button className="at-record-button" onClick={() => inspect(row.id)}><span className="at-record-title"><KindMark kind={row.kind}/><span>{row.summary}</span></span><span className="at-record-id at-mono">{shortId(row.id)}{citedIds.has(row.id) && <span className="at-cited-dot" title={t('cited')}>●</span>}</span></button></td><td className="at-value at-mono">{valueFor(row)}</td><td><button className="at-icon-button" onClick={() => inspect(row.id)} aria-label={`${t('openEvidence')} ${row.id}`}><Icon name="chevron"/></button></td>
              </tr>)}</tbody></table></div>
              <div className="at-table-footer"><span>{t('range')} {page * pageSize + 1}–{Math.min((page + 1) * pageSize, filtered.length)} / {filtered.length}</span><div><button disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} aria-label={t('previous')}>←</button><span>{page + 1} / {Math.ceil(filtered.length / pageSize)}</span><button disabled={(page + 1) * pageSize >= filtered.length} onClick={() => setPage((value) => value + 1)} aria-label={t('next')}>→</button></div></div>
            </>}
            {selectedRow && <RecordDetails row={selectedRow} originalLine={originalLine} originalLineError={originalLineError} cited={citedIds.has(selectedRow.id)} membership={modelIds ? modelIds.has(selectedRow.id) ? 'in_model_input' : 'outside_model_input' : data.analysis_source === 'local_baseline' ? 'not_applicable' : 'unknown'} lang={lang} onClose={closeRecord}/>}
          </section>
          <section className="at-comparison-section" aria-label={t('comparison')}>
            <div className="at-section-heading"><div><span className="at-eyebrow">04 / {t('comparison')}</span><h2>{comparison ? comparison.components.join(' / ') : t('comparison')}</h2></div><Icon name="layers" size={23}/></div>
            {actionError && <div className="at-error" role="alert">{actionError}</div>}
            {!comparison ? <p className="at-muted at-compare-empty">{t('compareHint')}</p> : <>
              <div className="at-comparison-cards">{comparison.summaries.map((summary) => <div className="at-component-card" key={summary.service}><h3>{summary.service}</h3><strong>{summary.record_count}<span>{t('records')}</span></strong><div className="at-kind-counts">{(['metric', 'span', 'log'] as Kind[]).map((item) => <span key={item}><KindMark kind={item}/>{summary.counts_by_kind[item]} {t(item)}</span>)}</div><p>{summary.error_span_count} {t('errorSpans')} · {summary.cited_record_count} {t('citations')}</p></div>)}</div>
              <div className="at-link-stats"><span><strong>{comparison.links.length}</strong> {t('observedEdges')}</span><span><strong>{comparison.unresolved_parents.length}</strong> {t('unresolved')}</span></div>
              <p className="at-fine-print">{t('linksNotCausal')}</p>
              <div className="at-query-heading"><strong>{t('followups')}</strong><label htmlFor="at-query-target">{t('queryTarget')}<select id="at-query-target" value={queryTarget} disabled={actionBusy || contextStale} onChange={(event) => { setQueryTarget(event.target.value); setFollowup(null); }}>{comparison.components.map((component) => <option key={component} value={component}>{component}</option>)}</select></label></div>
              <div className="at-followup-buttons" role="group" aria-label={t('followups')}>{queries.map((query) => <button className={`at-button at-button-small ${followup?.query === query.key ? 'active' : ''}`} key={query.key} disabled={actionBusy || contextStale} onClick={() => runEvidenceAction(query.key)}>{t(query.label)}{query.key === 'component_records' ? ` · ${queryTarget}` : ''}</button>)}</div>
              {followup && <FollowUpResult result={followup} lang={lang} onInspect={inspect}/>}
            </>}
          </section>
          <footer className="at-main-footer"><span>{t('originalData')}</span><span className="at-mono" title={data.snapshot_id}>{t('snapshot')}: {data.snapshot_id.slice(0, 12)}</span></footer>
        </>}
      </main>

      <aside className="at-findings" aria-label={t('findings')}>
        <div className="at-findings-heading"><span className="at-eyebrow">05 / {t('findings')}</span><span className="at-outline-badge">{t('readonly')}</span></div>
        {!data ? <div className="at-findings-placeholder" role="status"><Icon name="shield" size={27}/><p>{unavailableFinding}</p>{(loadError || listError) && <p className="at-fine-print">{loadError || listError}</p>}</div> : <>
          <div className="at-finding-source"><span className="at-source-icon">{data.analysis_source === 'recorded' ? 'G' : 'B'}</span><div><strong>{data.analysis_source === 'recorded' ? t('recordedGemini') : t('baseline')}</strong><span>{data.analysis.model ?? data.analysis.method}</span></div></div>
          <p className="at-snapshot-notice">{t(data.analysis_source === 'recorded' ? 'fullSnapshot' : 'baselineSnapshot')}</p>
          <section className="at-finding-card"><div className={`at-status ${supported ? 'at-status-supported' : ''}`}><span/>{supported ? t('supported') : t('insufficient')}</div><h2>{displayedCandidate?.service ?? t('overallAnalysis')}</h2><span className="at-finding-label">{displayedCandidate ? t('inspectionPriority') : t('noCandidateSelected')}</span><p>{displayedCandidate?.rationale ?? data.analysis.uncertainty}</p><div className="at-finding-warning"><Icon name="shield"/>{t('notRootCause')}</div></section>
          <div className="at-citations"><div className="at-subheading">{t('viewEvidence')} <span>{displayedEvidence.length}</span></div>{!displayedEvidence.length && <p className="at-muted">{t('noCitations')}</p>}{displayedEvidence.map((row, index) => <button key={row.id} className="at-citation" onClick={() => inspect(row.id)} title={row.id}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{row.service}</strong><small>{row.summary}</small></div><Icon name="chevron" size={13}/></button>)}</div>
          <div className="at-uncertainties"><div className="at-subheading">{t('uncertainties')}</div><p>{data.analysis.uncertainty || t('noUncertainty')}</p></div>
          <details className="at-method-details"><summary>{t('recordingDetails')}</summary><dl><dt>{t('method')}</dt><dd className="at-mono">{data.analysis.method}</dd>{data.analysis.model && <><dt>{t('model')}</dt><dd>{data.analysis.model}</dd></>}{data.analysis.recorded && <><dt>{t('recordedAt')}</dt><dd>{timestamp(data.analysis.recorded.recorded_at, lang)} UTC</dd><dt>{t('snapshot')}</dt><dd className="at-mono">{data.analysis.recorded.public_case_sha256}</dd></>}</dl>{data.analysis.recorded ? <><details><summary>{t('selectedIds')}</summary><pre>{JSON.stringify(data.analysis.recorded.selected_ids, null, 2)}</pre></details><details><summary>{t('rawResponse')}</summary><pre>{JSON.stringify(data.analysis.recorded.raw_response, null, 2)}</pre></details><details><summary>{t('applicationResponse')}</summary><pre>{JSON.stringify(data.analysis.recorded.application_response, null, 2)}</pre></details></> : <p>{t('baselineNote')}</p>}</details>
          <form className="at-review-form" onSubmit={saveReview}><div className="at-review-heading"><Icon name="shield"/><h3>{t('review')}</h3></div><p className="at-fine-print">{t('reviewHint')}</p><label htmlFor="at-candidate">{t('viewCandidate')} · {t('reviewService')}</label><select id="at-candidate" value={candidate} disabled={savingReview} onChange={(event) => { setCandidate(event.target.value); setReviewStatus(''); setReviewFile(''); }}><option value="">{t('noService')}</option>{data.analysis.candidates.map((item) => <option key={item.service} value={item.service}>{item.service}</option>)}</select><div className="at-decision-buttons" role="group" aria-label={t('review')}>{(['accept', 'reject', 'uncertain'] as Decision[]).map((item) => <button type="button" className={decision === item ? 'active' : ''} key={item} disabled={savingReview || (!candidate && item !== 'uncertain')} aria-pressed={decision === item} onClick={() => { setDecision(item); setReviewStatus(''); setReviewFile(''); }}>{t(item)}</button>)}</div><label htmlFor="at-review-reason">{t('reviewReason')}</label><textarea id="at-review-reason" value={reviewReason} disabled={savingReview} onChange={(event) => { setReviewReason(event.target.value); setReviewStatus(''); setReviewFile(''); }} placeholder={t('reviewPlaceholder')} rows={4} maxLength={4000}/><button className="at-button at-button-primary" type="submit" disabled={savingReview || contextStale || !reviewReason.trim()}><Icon name="check"/>{savingReview ? t('reviewing') : t('saveReview')}</button>{reviewStatus && <p className="at-review-status" role="status">{reviewStatus}</p>}{reviewFile && <p className="at-fine-print at-mono">{t('reviewedFile')}: {reviewFile}</p>}</form>
        </>}
      </aside>
    </div>
  </div>;
}

function RecordDetails({ row, lang, onClose, originalLine, originalLineError, cited, membership }: { row: Observation; lang: Language; onClose: () => void; originalLine: string | null; originalLineError: string; cited: boolean; membership: string }) {
  const t = textFor(lang); const source = safeSource(row.source_url);
  const membershipText = membership === 'in_model_input' ? t('inInput') : membership === 'outside_model_input' ? t('outside') : membership === 'not_applicable' ? t('notApplicable') : t('membershipUnknown');
  const details = useRef<HTMLDivElement>(null);
  useEffect(() => { details.current?.focus({ preventScroll: true }); details.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' }); }, [row.id]);
  return <div className="at-record-details" ref={details} tabIndex={-1} role="region" aria-label={`${t('selectedRecord')} ${row.id}`}>
    <div className="at-details-header"><div><span className="at-eyebrow">{t('selectedRecord')}</span><h3><KindMark kind={row.kind}/>{row.service}</h3></div><button className="at-icon-button" aria-label={t('close')} onClick={onClose}><Icon name="close"/></button></div>
    <p>{row.summary}</p><div className="at-details-tags"><span>{t(row.kind)}</span>{cited && <span className="at-tag-cited">{t('cited')}</span>}<span>{membershipText}</span></div>
    <dl><dt>ID</dt><dd className="at-mono">{row.id}</dd><dt>{t('time')}</dt><dd>{timestamp(row.timestamp, lang)} UTC</dd>{row.trace_id && <><dt>{t('traceId')}</dt><dd className="at-mono">{row.trace_id}</dd></>}{row.span_id && <><dt>{t('spanId')}</dt><dd className="at-mono">{row.span_id}</dd></>}</dl>
    {source ? <a className="at-source-link" href={source} target="_blank" rel="noopener noreferrer"><Icon name="arrow"/>{t('openSource')}</a> : <p className="at-fine-print">{t('sourceUnavailable')}</p>}<p className="at-fine-print">{t('sourceMayExpire')}</p>
    <details open><summary>{t('raw')}</summary><pre>{JSON.stringify(row.raw, null, 2)}</pre></details>{originalLineError && <p className="at-error" role="alert">{t('originalLookupError')}: {originalLineError}</p>}{originalLine !== null && <details><summary>{t('originalLine')}</summary><pre>{originalLine}</pre></details>}
  </div>;
}

function FollowUpResult({ result, lang, onInspect }: { result: FollowUp; lang: Language; onInspect: (id: string) => void }) {
  const t = textFor(lang);
  const title: TextKey = result.query === 'component_records' ? 'componentRecords' : result.query === 'observed_links' ? 'observedLinks' : 'outsideInput';
  function linkRows(rows: ObservedLink[], unresolved = false) {
    return <div className="at-links-list">{rows.map((link, index) => <div className="at-observed-link" key={`${link.child_evidence_id}-${index}`}><div><span>{link.parent_service ?? '?'}</span><span className="at-link-arrow">→</span><strong>{link.child_service}</strong></div><button className="at-text-button at-mono" onClick={() => onInspect(link.child_evidence_id)}>{shortId(link.child_evidence_id)}</button>{link.parent_evidence_id && <button className="at-text-button at-mono" onClick={() => onInspect(link.parent_evidence_id!)}>{shortId(link.parent_evidence_id)}</button>}{unresolved && <small>{link.reason}</small>}</div>)}</div>;
  }
  return <div className="at-followup-result"><h3>{t(title)}</h3><p className="at-fine-print">{t('followupNote')}</p>{result.status === 'unknown' ? <p>{t('inputUnknown')}</p> : result.status === 'not_applicable' ? <p>{t('notApplicable')}</p> : result.query === 'observed_links' ? <>
    {(result.links ?? []).length === 0 && <p className="at-muted">{t('noLinks')}</p>}{linkRows(result.links ?? [])}{(result.external_links ?? []).length > 0 && <details><summary>{t('allServices')} · {(result.external_links ?? []).length}</summary>{linkRows(result.external_links ?? [])}</details>}{(result.unresolved_parents ?? []).length > 0 && <details><summary>{t('unresolved')} · {(result.unresolved_parents ?? []).length}</summary>{linkRows(result.unresolved_parents ?? [], true)}</details>}
  </> : <>{(result.records ?? []).length === 0 && <p className="at-muted">{result.query === 'outside_recorded_input' ? t('noOutside') : t('noRecords')}</p>}<div className="at-query-records">{(result.records ?? []).map((row) => <button key={row.id} onClick={() => onInspect(row.id)}><KindMark kind={row.kind}/><span><strong>{row.service}</strong> · {row.summary}<small className="at-mono">{row.id}</small></span><Icon name="chevron" size={13}/></button>)}</div></> }</div>;
}
