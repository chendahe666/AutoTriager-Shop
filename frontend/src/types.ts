export type Language = 'en' | 'zh';
export type Kind = 'metric' | 'span' | 'log';
export type Query = 'component_records' | 'observed_links' | 'outside_recorded_input';
export type Decision = 'accept' | 'reject' | 'uncertain';
export interface Observation {
  id: string; kind: Kind; service: string; summary: string; timestamp: string;
  source_url: string; raw: Record<string, unknown>; trace_id?: string; span_id?: string;
  model_input_membership?: string; cited_by_current_result?: boolean;
  in_investigation_window?: boolean;
}
export interface Provenance {
  source_kind?: string; repository?: string; version?: string; collection_method?: string;
  captured_at?: string; [key: string]: unknown;
}
export interface CaseSummary {
  case_id: string; title: string; symptom: string; start_time: string; end_time: string;
  provenance: Provenance; observation_count: number; services: string[]; kinds: Record<Kind, number>;
  has_recorded_analysis: boolean;
}
export interface Catalog {
  mode: string; case_count: number; coverage_code: string;
  model_calls_enabled: boolean; live_refresh_enabled: boolean;
}
export interface Incident extends Omit<CaseSummary, 'observation_count' | 'services' | 'kinds' | 'has_recorded_analysis'> {
  observations: Observation[]; schema_version: string;
}
export interface Candidate {
  service: string; score: number | null; evidence_ids: string[]; rationale: string;
}
export interface Analysis {
  case_id: string; status: string; candidates: Candidate[]; evidence: Observation[];
  uncertainty: string; method: string; model?: string; latency_ms?: number;
  visible_evidence_count?: number; invalid_citations?: string[];
  recorded?: {
    selected_ids: string[]; recorded_at: string; input_sha256: string;
    sanitized_raw_response_sha256: string; public_case_sha256: string;
    raw_response: unknown; application_response: unknown; [key: string]: unknown;
  };
}
export interface CaseResponse {
  case: Incident; analysis: Analysis; analysis_source: 'recorded' | 'local_baseline'; snapshot_id: string; analysis_id: string;
}
export interface ObservedLink {
  parent_service?: string; child_service: string; parent_evidence_id?: string;
  child_evidence_id: string; trace_id?: string; reason?: string; timestamp: string;
}
export interface ServiceSummary {
  service: string; record_count: number; counts_by_kind: Record<Kind, number>;
  error_span_count: number; cited_record_count: number; outside_window_count: number;
}
export interface Comparison {
  case_id: string; components: string[]; model_input_visibility: string;
  summaries: ServiceSummary[]; records: Observation[]; links: ObservedLink[];
  external_links: ObservedLink[]; unresolved_parents: ObservedLink[];
}
export interface FollowUp {
  query: Query; status: string; records?: Observation[]; links?: ObservedLink[];
  external_links?: ObservedLink[]; unresolved_parents?: ObservedLink[];
}
