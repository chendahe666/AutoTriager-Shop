"""Bilingual, read-only incident investigation UI.

Run with ``streamlit run app.py``. The private ground-truth file is never read
by this application; it is reserved for offline evaluation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from autotriager_shop import analyze_incident, load_incident
from autotriager_shop.gemini import DEFAULT_MODEL, diagnose_with_gemini
from autotriager_shop.ui import (
    broken_evidence_references,
    build_review_record,
    gemini_result_to_analysis,
    list_case_dirs,
    local_source_line,
    provenance_label,
    save_review,
)


ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
REVIEWS_DIR = ROOT / "reviews"

COPY = {
    "en": {
        "language": "Language",
        "title": "AutoTriager",
        "subtitle": "Evidence-grounded incident triage for a simulated shopping service",
        "case": "Incident case",
        "no_cases": "No replayable incident bundles are available yet. Capture a Shop run or add a clearly labeled test fixture under `cases/`.",
        "public_files": "Each case needs public `incident.json` and `observations.json`. Evaluation answers remain private.",
        "case_details": "Incident scope",
        "symptom": "Reported symptom",
        "time_window": "Investigation window",
        "provenance": "Data provenance",
        "source_kind": "Source type",
        "repository": "Source repository",
        "version": "Source version",
        "collection": "Collection method",
        "captured_at": "Captured at",
        "run": "Run diagnosis",
        "run_local": "Run local baseline",
        "run_gemini": "Analyze with Gemini",
        "gemini_heading": "Optional Gemini grounded analysis",
        "gemini_consent": "I confirm this is an open demo case with no private enterprise data, and I allow its public incident and observations to be sent to Gemini.",
        "gemini_consent_required": "Confirm the data-sharing statement before calling Gemini.",
        "gemini_unavailable": "Gemini analysis is available only for captured open shopping demos. This case is not eligible.",
        "gemini_no_key": "GEMINI_API_KEY is not configured for this process. Add it to the local environment before calling Gemini.",
        "gemini_sending": "Sending this case's public incident and selected observations to Gemini…",
        "gemini_error": "Gemini request failed: {error}",
        "result_view": "Result to inspect",
        "local_result": "Local baseline",
        "gemini_result": "Gemini grounded analysis",
        "model": "Model",
        "latency": "API latency",
        "visible_count": "Observations sent to model",
        "invalid_citations": "Gemini supplied citations that did not match the sent evidence: {ids}. These were excluded.",
        "running": "Analyzing public observations…",
        "result": "Diagnosis",
        "status": "Evidence status",
        "supported": "Supported hypothesis",
        "insufficient_evidence": "Insufficient evidence",
        "method": "Analysis method",
        "candidates": "Candidate services",
        "first_check": "First service to inspect",
        "priority_not_cause": "An investigation priority, not a proven root cause.",
        "more_evidence": "{count} more IDs; inspect the evidence table below",
        "no_candidates": "No service can be supported from the available observations.",
        "ranking_score": "Ranking score (not a calibrated probability)",
        "rationale": "Reasoning",
        "cites": "Cited evidence",
        "evidence": "Inspectable evidence",
        "kind": "Type",
        "service": "Service",
        "timestamp": "Timestamp",
        "summary": "Observation",
        "source": "Source reference",
        "trace": "Trace ID",
        "span": "Span ID",
        "raw": "Raw observation",
        "original_line": "Original collector record",
        "baseline_sources": "Baseline source records",
        "alert_sources": "Alert-window source records",
        "more_source_refs": "{count} additional source references are listed in the raw observation.",
        "unknown_source": "No direct source link was supplied.",
        "uncertainty": "Uncertainty and missing information",
        "broken_refs": "Some candidate citations have no matching evidence record: {ids}. Verify the analysis before relying on it.",
        "human_review": "Human review",
        "human_review_help": "Check the linked observations before deciding. This judgment does not change the simulated service.",
        "review_candidate": "Candidate to review",
        "none": "No candidate / overall finding",
        "review_decision": "Your judgment",
        "accept": "Accept",
        "reject": "Reject",
        "uncertain": "Uncertain",
        "reason": "Reason for your judgment",
        "reason_placeholder": "Which observations support or contradict this finding? What should be checked next?",
        "save": "Save local review",
        "saved": "Review saved: {path}",
        "download": "Download review JSON",
        "reason_required": "Enter a brief reason before saving.",
        "decision_required": "Choose your judgment before saving.",
        "candidate_required": "Choose a candidate service before accepting or rejecting a supported hypothesis.",
        "load_error": "Could not load this case: {error}",
        "analysis_error": "Diagnosis failed: {error}",
        "review_error": "Could not save review: {error}",
        "fixture_warning": "This case is a synthetic test fixture. Results do not establish performance on a running Shop deployment.",
        "capture_note": "A captured Shop case records actual telemetry from a running instance; check its provenance before treating it as an experiment.",
        "local_sim_note": "This case records a run of this project's local shopping simulation. It is separate from the official Astronomy Shop deployment.",
    },
    "zh": {
        "language": "语言 / Language",
        "title": "AutoTriager",
        "subtitle": "购物服务仿真环境中的证据化故障排查",
        "case": "故障案例",
        "no_cases": "目前没有可重放的故障案例。请采集一次 Shop 运行数据，或在 `cases/` 中加入明确标注的测试样例。",
        "public_files": "每个案例需要公开的 `incident.json` 和 `observations.json`。评估答案不作为分析输入。",
        "case_details": "调查范围",
        "symptom": "报告的症状",
        "time_window": "调查时间范围",
        "provenance": "数据来源",
        "source_kind": "来源类型",
        "repository": "来源仓库",
        "version": "来源版本",
        "collection": "采集方法",
        "captured_at": "采集时间",
        "run": "运行诊断",
        "run_local": "运行本地基线",
        "run_gemini": "使用 Gemini 分析",
        "gemini_heading": "可选的 Gemini 证据化分析",
        "gemini_consent": "我确认这是不含企业私有数据的开放演示案例，并同意将公开的故障描述和观测记录发送给 Gemini。",
        "gemini_consent_required": "调用 Gemini 前请确认数据发送声明。",
        "gemini_unavailable": "Gemini 分析只用于已采集的开放购物演示案例；此案例不符合条件。",
        "gemini_no_key": "当前进程未配置 GEMINI_API_KEY。请先在本地环境配置，再调用 Gemini。",
        "gemini_sending": "正在向 Gemini 发送该案例的公开描述与选定观测记录…",
        "gemini_error": "Gemini 请求失败：{error}",
        "result_view": "查看哪项结果",
        "local_result": "本地基线",
        "gemini_result": "Gemini 证据化分析",
        "model": "模型",
        "latency": "API 耗时",
        "visible_count": "发送给模型的观测记录数",
        "invalid_citations": "Gemini 给出的这些引用无法与所发送的证据对应：{ids}。这些引用已被排除。",
        "running": "正在分析公开的观测记录…",
        "result": "诊断结果",
        "status": "证据状态",
        "supported": "有证据支持的假设",
        "insufficient_evidence": "证据不足",
        "method": "分析方法",
        "candidates": "候选服务",
        "first_check": "优先检查的服务",
        "priority_not_cause": "这是调查优先级，并非已证明的根因。",
        "more_evidence": "另有 {count} 条引用；请查看下方证据表",
        "no_candidates": "现有记录不足以支持任何特定服务。",
        "ranking_score": "排序分数（不是校准后的概率）",
        "rationale": "判断理由",
        "cites": "引用的证据",
        "evidence": "可核查的证据",
        "kind": "类型",
        "service": "服务",
        "timestamp": "时间戳",
        "summary": "观测内容",
        "source": "来源记录",
        "trace": "Trace ID",
        "span": "Span ID",
        "raw": "原始观测",
        "original_line": "采集文件中的原始记录",
        "baseline_sources": "正常阶段原始记录",
        "alert_sources": "告警阶段原始记录",
        "more_source_refs": "其余 {count} 条来源引用见下方原始观测数据。",
        "unknown_source": "未提供直接来源链接。",
        "uncertainty": "不确定性和缺失信息",
        "broken_refs": "候选结论引用了不存在的证据记录：{ids}。使用前请核对诊断。",
        "human_review": "人工核查",
        "human_review_help": "请先检查引用的观测记录，再作判断。这里的判断不会修改仿真服务。",
        "review_candidate": "核查对象",
        "none": "无候选 / 整体结论",
        "review_decision": "你的判断",
        "accept": "接受",
        "reject": "拒绝",
        "uncertain": "暂不确定",
        "reason": "判断理由",
        "reason_placeholder": "哪些记录支持或反驳该结论？下一步需要核查什么？",
        "save": "保存本地核查记录",
        "saved": "核查记录已保存：{path}",
        "download": "下载核查 JSON",
        "reason_required": "保存前请写一句判断理由。",
        "decision_required": "保存前请选择你的判断。",
        "candidate_required": "接受或否定有证据支持的假设前，请先选择一个候选服务。",
        "load_error": "无法加载案例：{error}",
        "analysis_error": "诊断失败：{error}",
        "review_error": "无法保存核查记录：{error}",
        "fixture_warning": "该案例是合成测试样例，结果不能证明系统在真实运行的 Shop 上有效。",
        "capture_note": "已采集案例记录的是运行实例的实际遥测；将其视作实验前请检查来源信息。",
        "local_sim_note": "该案例来自本项目本地购物仿真的实际运行，不等同于官方 Astronomy Shop 部署。",
    },
}


def _human_source_link(source_url: Any, tr: dict[str, str]) -> None:
    url = str(source_url or "").strip()
    if not url:
        st.caption(tr["unknown_source"])
    elif urlparse(url).scheme in {"http", "https"}:
        st.link_button(tr["source"], url)
    else:
        # Local file references and trace IDs are shown as identifiers. A
        # browser cannot reliably navigate directly into the collector files.
        st.code(url, language=None)


def _show_evidence(analysis: dict[str, Any], tr: dict[str, str], case_dir: Path) -> None:
    st.subheader(tr["evidence"])
    evidence = analysis.get("evidence", [])
    if not evidence:
        st.info(tr["no_candidates"])
        return
    overview = [
        {
            "ID": item.get("id", ""),
            tr["timestamp"]: item.get("timestamp", ""),
            tr["service"]: item.get("service", ""),
            tr["kind"]: item.get("kind", ""),
            tr["summary"]: item.get("summary", ""),
        }
        for item in evidence
    ]
    st.dataframe(overview, hide_index=True, width="stretch")
    for item in evidence:
        title = f"{item.get('id', '?')} · {item.get('service', '?')} · {item.get('timestamp', '?')}"
        with st.expander(title):
            st.write(item.get("summary", ""))
            st.caption(f"{tr['kind']}: {item.get('kind', '—')}")
            if item.get("trace_id"):
                st.code(f"{tr['trace']}: {item['trace_id']}", language=None)
            if item.get("span_id"):
                st.code(f"{tr['span']}: {item['span_id']}", language=None)
            _human_source_link(item.get("source_url"), tr)
            try:
                original = local_source_line(case_dir, str(item.get("source_url") or ""))
            except OSError:
                original = None
            if original:
                st.caption(tr["original_line"])
                st.code(original, language="json")
            if item.get("kind") == "metric" and isinstance(item.get("raw"), dict):
                raw = item["raw"]
                groups = (
                    (tr["baseline_sources"], raw.get("baseline_source_refs", [])),
                    (tr["alert_sources"], raw.get("alert_source_refs", raw.get("source_refs", []))),
                )
                for label, refs in groups:
                    if not isinstance(refs, list) or not refs:
                        continue
                    st.caption(label)
                    for ref in refs[:3]:
                        if not isinstance(ref, str):
                            continue
                        try:
                            source_line = local_source_line(case_dir, ref)
                        except OSError:
                            source_line = None
                        st.code(ref + ("\n" + source_line if source_line else ""), language="json")
                    if len(refs) > 3:
                        st.caption(tr["more_source_refs"].format(count=len(refs) - 3))
            if item.get("raw") is not None:
                st.write(tr["raw"])
                st.json(item["raw"])


def _show_candidates(analysis: dict[str, Any], tr: dict[str, str]) -> None:
    st.subheader(tr["candidates"])
    candidates = analysis.get("candidates", [])
    if not candidates:
        st.info(tr["no_candidates"])
        return
    if analysis.get("status") == "supported":
        st.info(f"{tr['first_check']}: **{candidates[0].get('service', '?')}**. {tr['priority_not_cause']}")
    for index, candidate in enumerate(candidates, start=1):
        service = candidate.get("service", "?")
        st.markdown(f"**{index}. {service}**")
        if candidate.get("score") is not None:
            st.caption(f"{tr['ranking_score']}: {candidate['score']}")
        st.write(f"{tr['rationale']}: {candidate.get('rationale', '—')}")
        cited = list(map(str, candidate.get("evidence_ids", [])))
        shown = ", ".join(cited[:4]) or "—"
        if len(cited) > 4:
            shown += f" · {tr['more_evidence'].format(count=len(cited) - 4)}"
        st.caption(f"{tr['cites']}: {shown}")


def _show_review(case: dict[str, Any], analysis: dict[str, Any], tr: dict[str, str], lang: str) -> None:
    st.subheader(tr["human_review"])
    st.caption(tr["human_review_help"])
    case_id = str(case["case_id"])
    review_key = f"{case_id}_{analysis.get('method', 'unknown')}"
    options = [None] + [str(item.get("service")) for item in analysis.get("candidates", [])]
    candidate_service = st.selectbox(
        tr["review_candidate"],
        options,
        format_func=lambda service: tr["none"] if service is None else service,
        key=f"review_service_{review_key}",
    )
    decision = st.radio(
        tr["review_decision"],
        ["accept", "reject", "uncertain"],
        index=None,
        format_func=lambda value: tr[value],
        horizontal=True,
        key=f"review_decision_{review_key}",
    )
    reason = st.text_area(
        tr["reason"],
        placeholder=tr["reason_placeholder"],
        key=f"review_reason_{review_key}",
    )
    if st.button(tr["save"], type="secondary", key=f"save_{review_key}"):
        if decision is None:
            st.warning(tr["decision_required"])
        elif analysis.get("status") == "supported" and candidate_service is None and decision != "uncertain":
            st.warning(tr["candidate_required"])
        elif not reason.strip():
            st.warning(tr["reason_required"])
        else:
            try:
                record = build_review_record(case, analysis, candidate_service, decision, reason)
                path = save_review(record, REVIEWS_DIR)
                st.session_state["latest_review"] = (review_key, record, str(path))
            except (OSError, ValueError, KeyError) as exc:
                st.error(tr["review_error"].format(error=exc))
    latest = st.session_state.get("latest_review")
    if latest and latest[0] == review_key:
        st.success(tr["saved"].format(path=latest[2]))
        st.download_button(
            tr["download"],
            data=json.dumps(latest[1], ensure_ascii=False, indent=2),
            file_name=Path(latest[2]).name,
            mime="application/json",
            key=f"download_{review_key}_{lang}",
        )


def main() -> None:
    st.set_page_config(page_title="AutoTriager", layout="wide")
    lang = st.sidebar.selectbox("Language / 语言", ["English", "中文"])
    language = "zh" if lang == "中文" else "en"
    tr = COPY[language]
    st.title(tr["title"])
    st.caption(tr["subtitle"])

    cases = list_case_dirs(CASES_DIR)
    if not cases:
        st.info(tr["no_cases"])
        st.caption(tr["public_files"])
        return

    selected_dir = st.sidebar.selectbox(tr["case"], cases, format_func=lambda path: path.name)
    if selected_dir is None:
        return
    try:
        incident = load_incident(selected_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(tr["load_error"].format(error=exc))
        return

    st.header(incident.get("title", selected_dir.name))
    st.subheader(tr["case_details"])
    st.write(f"**{tr['symptom']}:** {incident.get('symptom', '—')}")
    st.write(
        f"**{tr['time_window']}:** "
        f"{incident.get('start_time', '—')} → {incident.get('end_time', '—')}"
    )
    provenance = incident.get("provenance", {})
    st.subheader(tr["provenance"])
    st.write(provenance_label(provenance, language))
    if provenance.get("source_kind") == "synthetic_fixture":
        st.warning(tr["fixture_warning"])
    elif provenance.get("source_kind") == "captured_shop":
        st.caption(tr["capture_note"])
    elif provenance.get("source_kind") == "captured_local_sim":
        st.caption(tr["local_sim_note"])
    provenance_fields = [
        ("repository", "repository"),
        ("version", "version"),
        ("collection_method", "collection"),
        ("captured_at", "captured_at"),
    ]
    for field, label in provenance_fields:
        if provenance.get(field):
            st.caption(f"{tr[label]}: {provenance[field]}")

    selected_key = str(selected_dir.resolve())
    if st.session_state.get("analysis_case") != selected_key:
        st.session_state.pop("analysis_local", None)
        st.session_state.pop("analysis_gemini", None)
        st.session_state.pop("latest_review", None)
        st.session_state["analysis_case"] = selected_key
    if st.button(tr["run_local"], type="primary"):
        try:
            with st.spinner(tr["running"]):
                st.session_state["analysis_local"] = analyze_incident(selected_dir)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            st.session_state.pop("analysis_local", None)
            st.error(tr["analysis_error"].format(error=exc))

    st.subheader(tr["gemini_heading"])
    eligible = provenance.get("source_kind") in {"captured_local_sim", "captured_shop"}
    if not eligible:
        st.caption(tr["gemini_unavailable"])
    consent = st.checkbox(tr["gemini_consent"], key=f"gemini_consent_{selected_key}", disabled=not eligible)
    if st.button(tr["run_gemini"], disabled=not eligible, key=f"run_gemini_{selected_key}"):
        if not consent:
            st.warning(tr["gemini_consent_required"])
        elif not os.environ.get("GEMINI_API_KEY"):
            st.warning(tr["gemini_no_key"])
        else:
            try:
                with st.spinner(tr["gemini_sending"]):
                    raw_result = diagnose_with_gemini(selected_dir, mode="grounded", model=DEFAULT_MODEL)
                    st.session_state["analysis_gemini"] = gemini_result_to_analysis(incident, raw_result)
            except Exception as exc:
                # Network, API, and validation errors are shown without hiding
                # the separately available local baseline result.
                st.session_state.pop("analysis_gemini", None)
                message = str(exc)
                configured_key = os.environ.get("GEMINI_API_KEY")
                if configured_key:
                    message = message.replace(configured_key, "[redacted]")
                st.error(tr["gemini_error"].format(error=message))

    available_results = {
        "local": st.session_state.get("analysis_local"),
        "gemini": st.session_state.get("analysis_gemini"),
    }
    available_results = {key: value for key, value in available_results.items() if value}
    if not available_results:
        return
    selected_result = st.radio(
        tr["result_view"],
        list(available_results),
        format_func=lambda key: tr[f"{key}_result"],
        horizontal=True,
    )
    analysis = available_results[selected_result]
    st.header(tr["result"])
    status = str(analysis.get("status", "insufficient_evidence"))
    if status == "supported":
        st.success(f"{tr['status']}: {tr['supported']}")
    else:
        st.warning(f"{tr['status']}: {tr['insufficient_evidence']}")
    st.caption(f"{tr['method']}: {analysis.get('method', '—')}")
    if selected_result == "gemini":
        st.caption(
            f"{tr['model']}: {analysis.get('model') or '—'} · "
            f"{tr['latency']}: {analysis.get('latency_ms', '—')} ms · "
            f"{tr['visible_count']}: {analysis.get('visible_evidence_count', '—')}"
        )
        invalid = analysis.get("invalid_citations", [])
        if invalid:
            st.warning(tr["invalid_citations"].format(ids=", ".join(map(str, invalid))))
    missing = broken_evidence_references(analysis)
    if missing:
        st.error(tr["broken_refs"].format(ids=", ".join(missing)))
    _show_candidates(analysis, tr)
    _show_evidence(analysis, tr, selected_dir)
    st.subheader(tr["uncertainty"])
    st.write(analysis.get("uncertainty") or "—")
    _show_review(incident, analysis, tr, language)


if __name__ == "__main__":
    main()
