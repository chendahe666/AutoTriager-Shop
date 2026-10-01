"""Build the evidence-bounded, English Challenge 2 PDF report.

Run with the bundled workspace Python (reportlab and Pillow required). The
document reads the tracked exploratory CSV and genuine local screenshots.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageEnhance, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "AutoTriager_Challenge2_Dahe_Chen.pdf"
RESULTS = ROOT / "results" / "local_sim_valid.json"
ROWS = ROOT / "results" / "local_sim_valid.csv"
SCREENSHOTS = ROOT / "results" / "screenshots"
BLACK = colors.black
GRAY = colors.HexColor("#505050")
LIGHT = colors.HexColor("#EDEDED")
MID = colors.HexColor("#B7B7B7")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="DocTitle", fontName="Helvetica-Bold", fontSize=18,
                          leading=21, alignment=TA_LEFT, textColor=BLACK,
                          spaceAfter=9))
styles.add(ParagraphStyle(name="Deck", fontName="Helvetica", fontSize=10.1,
                          leading=13.6, textColor=GRAY, spaceAfter=8))
styles.add(ParagraphStyle(name="SectionCustom", fontName="Helvetica-Bold",
                          fontSize=11.2, leading=13.4, spaceBefore=9,
                          spaceAfter=5, textColor=BLACK))
styles.add(ParagraphStyle(name="BodyCustom", fontName="Helvetica", fontSize=9.1,
                          leading=12.7, spaceAfter=6, textColor=BLACK))
styles.add(ParagraphStyle(name="SmallCustom", fontName="Helvetica", fontSize=8,
                          leading=10.6, spaceAfter=4, textColor=BLACK))
styles.add(ParagraphStyle(name="CaptionCustom", fontName="Helvetica-Oblique",
                          fontSize=7.8, leading=10.1, spaceBefore=4,
                          spaceAfter=8, textColor=GRAY))
styles.add(ParagraphStyle(name="TableHeadCustom", fontName="Helvetica-Bold",
                          fontSize=7.4, leading=9.2, textColor=BLACK))
styles.add(ParagraphStyle(name="TableCellCustom", fontName="Helvetica",
                          fontSize=7.2, leading=9.1, textColor=BLACK))


def p(text: str, style: str = "BodyCustom") -> Paragraph:
    return Paragraph(text, styles[style])


def section(title: str) -> Paragraph:
    return p(escape(title), "SectionCustom")


def bullet(text: str) -> Paragraph:
    return p("&#8226; " + text, "BodyCustom")


def caption(text: str) -> Paragraph:
    return p(escape(text), "CaptionCustom")


def tiny_table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[p(escape(v), "TableHeadCustom") for v in headers]]
    data += [[p(escape(str(v)), "TableCellCustom") for v in row] for row in rows]
    table = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, MID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


class FlowDiagram(Flowable):
    def __init__(self, nodes: list[tuple[str, str]], width: float = 504):
        super().__init__()
        self.nodes = nodes
        self.width = width
        self.height = 66

    def draw(self) -> None:
        c = self.canv
        gap = 16
        box_w = (self.width - gap * (len(self.nodes) - 1)) / len(self.nodes)
        for idx, (top, bottom) in enumerate(self.nodes):
            x = idx * (box_w + gap)
            c.setFillColor(colors.white)
            c.setStrokeColor(BLACK)
            c.roundRect(x, 10, box_w, 48, 3, fill=1, stroke=1)
            c.setFillColor(BLACK)
            c.setFont("Helvetica-Bold", 7.7)
            c.drawCentredString(x + box_w / 2, 39, top)
            c.setFont("Helvetica", 7.0)
            c.drawCentredString(x + box_w / 2, 25, bottom)
            if idx < len(self.nodes) - 1:
                x1 = x + box_w + 2
                x2 = x + box_w + gap - 2
                c.line(x1, 34, x2, 34)
                c.line(x2 - 4, 37, x2, 34)
                c.line(x2 - 4, 31, x2, 34)


class ArchitectureDiagram(Flowable):
    def __init__(self):
        super().__init__()
        self.width = 504
        self.height = 150

    def draw(self) -> None:
        c = self.canv
        nodes = [
            (0, "4 HTTP services", "frontend / checkout", "catalog / payment"),
            (104, "Raw telemetry", "spans + logs", "trace / parent IDs"),
            (208, "Incident bundle", "time + provenance", "public observations"),
            (312, "Evidence + model", "rank / select top 48", "optional Gemini"),
            (416, "Review UI", "candidate + raw links", "human judgment"),
        ]
        for x, head, line1, line2 in nodes:
            c.setFillColor(colors.white)
            c.setStrokeColor(BLACK)
            c.roundRect(x, 62, 88, 62, 3, stroke=1, fill=1)
            c.setFillColor(BLACK)
            c.setFont("Helvetica-Bold", 7.2)
            c.drawCentredString(x + 44, 105, head)
            c.setFont("Helvetica", 6.6)
            c.drawCentredString(x + 44, 88, line1)
            c.drawCentredString(x + 44, 75, line2)
            if x < 416:
                c.line(x + 89, 93, x + 103, 93)
                c.line(x + 99, 96, x + 103, 93)
                c.line(x + 99, 90, x + 103, 93)
        c.setStrokeColor(GRAY)
        c.setDash(3, 3)
        c.roundRect(144, 7, 218, 29, 3, stroke=1, fill=0)
        c.setDash()
        c.setFont("Helvetica", 7.3)
        c.setFillColor(BLACK)
        c.drawCentredString(253, 18, "Private intervention labels -> offline evaluator only")
        c.line(253, 36, 253, 61)
        c.line(250, 40, 253, 36)
        c.line(256, 40, 253, 36)
        c.setFont("Helvetica-Oblique", 6.8)
        c.drawString(0, 137, "Future adapter: official Astronomy Shop / Prometheus / Jaeger (not yet live-verified)")


def screenshot(filename: str, crop: tuple[int, int, int, int], width: float) -> Image:
    source = SCREENSHOTS / filename
    with PILImage.open(source) as img:
        gray = ImageEnhance.Contrast(ImageOps.grayscale(img.crop(crop))).enhance(1.7)
        data = io.BytesIO()
        gray.save(data, format="PNG")
        data.seek(0)
        out = Image(data)
        out.drawWidth = width
        out.drawHeight = width * gray.height / gray.width
        out.hAlign = "CENTER"
        return out


def footer(canvas, doc) -> None:
    canvas.saveState()
    w, _ = letter
    canvas.setStrokeColor(MID)
    canvas.line(0.62 * inch, 0.52 * inch, w - 0.62 * inch, 0.52 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(0.62 * inch, 0.37 * inch, "AutoTriager Shop | CS 5588 Challenge 2 | Dahe Chen")
    canvas.drawRightString(w - 0.62 * inch, 0.37 * inch, str(doc.page))
    canvas.restoreState()


def read_results() -> tuple[dict, list[dict]]:
    summary = json.loads(RESULTS.read_text(encoding="utf-8"))
    with ROWS.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return summary, rows


def build() -> None:
    summary, rows = read_results()
    case_rows: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        case_rows[row["case_id"]][row["method"]] = row
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=letter, rightMargin=0.65 * inch,
                            leftMargin=0.65 * inch, topMargin=0.59 * inch,
                            bottomMargin=0.68 * inch,
                            title="AutoTriager Shop: Human-AI Co-Design",
                            author="Dahe Chen")
    story: list = []

    # Page 1: self-contained problem and the original human reasoning.
    story += [p("AutoTriager Shop", "DocTitle"),
              p("Human-AI co-design of an evidence-grounded incident workbench", "Deck"),
              p("<b>Dahe Chen</b>  |  CS 5588 Data Science Capstone, Challenge 2  |  October 1, 2026", "SmallCustom"),
              section("Abstract"),
              p("A checkout failure can surface in several services even when one dependency initiated it. "
                "This project asks whether a novice on-call developer can use a read-only workbench to choose a "
                "defensible first service to inspect, verify the original telemetry, and defer judgment when "
                "the data are insufficient. We replaced an earlier benchmark replay with a running four-process "
                "shopping simulation, collected normal/fault/recovery records, implemented a bilingual evidence "
                "view and optional Gemini analysis, and compared methods on five newly captured local cases. A "
                "strong direct prompt and evidence-prioritized prompting both localized 3 of 4 injected faults "
                "and abstained on the clean control. The evidence therefore supports a working, inspectable "
                "prototype, not a localization gain or production readiness."),
              section("1. Problem and focused P1 task"),
              p("<b>User:</b> a junior on-call developer handling a bounded checkout incident. The need is a "
                "design hypothesis; no user study has confirmed it. <b>Challenge 2 goal:</b> load one observed "
                "incident, apply a diagnostic method, show a candidate service with source-linked evidence or "
                "abstain, and allow a human to record a judgment. The semester product would support harder "
                "cross-service ambiguity and more realistic sources later. It never executes recovery actions."),
              caption("Figure 1. Reconstruction of the human-selected investigation workflow before implementation."),
              FlowDiagram([("Checkout alert", "customer symptom"),
                           ("Bound window", "same incident"),
                           ("Compare signals", "service + time"),
                           ("Open evidence", "raw record"),
                           ("Human decision", "accept / defer")]),
              section("2. Human Design and its limits"),
              p("The human design fixed the decision boundary first: an engineer should inspect candidate "
                "services and evidence before deciding what to do. P1 combined case loading and existing-style "
                "analysis; evidence display made that path usable. Historical reviews, richer visualization, "
                "and optimization were lower priority; multiple unrelated systems were optional. The initial "
                "plan assumed that OpenRCA Bank cases established a suitable application scenario. They did "
                "not show a live shopping workflow, so their earlier scores are excluded from this report."),
              p("The revised acceptance gate requires separate running services, controlled normal/fault/"
                "recovery phases, labels isolated from the model, source-resolvable claims, a human veto, "
                "and comparison with a capable direct prompt. This directly addresses the instructor's "
                "questions: who uses the tool, where the need occurs, and why a prompt alone may suffice."),
              p("Earlier project discussions involved AI assistance. The Human Design here records the "
                "student's selected boundaries; it is not presented as an independently time-stamped, "
                "AI-free document.", "SmallCustom"),
              PageBreak()]

    # Page 2: AI design versus corrected co-design.
    story += [section("3. AI Design: useful structure and a necessary correction"),
              p("Earlier AI design advice proposed replaying OpenRCA Bank incidents through EviRCA-style "
                "evidence extraction, model reasoning, and a result view. That architecture did not itself "
                "establish a runnable shopping workflow. After the revised requirement, the coding assistant "
                "proposed a public case schema, UTC windows, stable IDs, trace parent links, deterministic "
                "first pass, budgeted evidence selection, optional LLM reasoning, citation validation, and "
                "a local review interface. It also found that official Astronomy Shop source could be pinned "
                "but not run here without WSL and Docker."),
              p("The AI proposal needed critical review. It had previously treated Bank benchmark results as "
                "evidence for this product, suggested a weak direct prompt as the comparator, and risked "
                "conflating a small local simulator with the official Shop. I rejected those shortcuts. A strong "
                "same-budget prompt is the meaningful comparator; local and official telemetry have separate "
                "provenance; a screenshot is interface evidence, not proof of diagnostic accuracy."),
              caption("Figure 2. Reconstructed earlier AI proposal, not an executed shopping architecture: Bank replay supplied no live checkout or matched intervention."),
              FlowDiagram([("Bank case", "benchmark replay"),
                           ("Evidence pass", "EviRCA style"),
                           ("LLM / agent", "candidate"),
                           ("Citations", "record IDs"),
                           ("Result UI", "compare label")]),
              section("4. Explicit Human-AI co-design"),
              tiny_table(
                  ["Decision", "Human Design", "AI proposal", "Final co-design"],
                  [
                      ["Scenario", "Read-only aid for a new on-call engineer", "Replay benchmark incidents", "Run a controlled shopping incident; exclude Bank scores"],
                      ["Data", "Metrics, traces, logs where available", "Normalize as compact text", "Preserve numbers, UTC, service, trace/parent IDs, raw line refs"],
                      ["Retrieval", "Find relevant observations", "Evidence-first context", "Rule-based top-48 selection; no claim of trained RAG"],
                      ["Grounding", "Engineer checks before action", "Cite IDs", "Validate IDs, open raw lines, abstain when thin"],
                      ["Evaluation", "Check injected labels", "Weak prompt baseline", "Add strong prompt, clean controls, explicit failure"],
                  ], [65, 128, 102, 207]),
              Spacer(1, 9),
              p("The AI-only proposal specified a data path, but did not establish user value or fair evaluation. "
                "Human review required a live scenario, isolated labels, a strong direct-model comparator, "
                "and separate claims for the local simulator and official Shop."),
              p("These changes are design improvements because they make the experiment, user action, and "
                "evidence boundary inspectable. They are <b>not</b> measured improvements in engineer speed "
                "or model accuracy. The strong direct prompt tied the grounded prompt in valid-set fault "
                "localization, so a claim that the new architecture beats prompting would be unsupported."),
              section("5. Human and AI responsibilities"),
              bullet("The human selected the user decision, target setting, first P1 scope, comparison standard, and what counts as unacceptable evidence leakage."),
              bullet("AI assisted source inspection, schema/adapter code, test construction, UI implementation, and identification of failure modes."),
              bullet("The human reviewer must decide whether a cited observation really supports a conclusion and whether any operational action is appropriate."),
              PageBreak()]

    # Page 3: data and architecture.
    story += [section("6. Data and multimodal processing"),
              p("The evaluated source is this project's <b>native local shopping simulation</b>: four separate "
                "Python HTTP processes named frontend, checkout, catalog, and payment. A test order actually "
                "crosses process boundaries. Fault modes include payment rejection, payment capacity pressure, "
                "payment delay, catalog error, checkout error, and no fault. Each run records normal, injected, "
                "and recovery traffic. One capacity run had 24/24 normal HTTP 200 responses, 21/24 checkout "
                "errors during injection, and 24/24 recovery HTTP 200 responses."),
              p("The five newly captured bundles contain 260 span, 234 log, and 40 derived metric observations "
                "(534 total). Raw spans/logs are append-only NDJSON with service, UTC timestamp, trace ID, "
                "span ID, and parent-span ID. Error-rate and latency metrics are computed from normal versus alert spans; "
                "they are not independent Prometheus measurements. A public observation has a stable ID and "
                "a reference such as <font name='Courier'>raw/payment.spans.ndjson#L8</font>. Numeric values "
                "and topology are retained as structured fields rather than flattened into prose."),
              p("The intervention, expected service, traffic counts, and phase bounds reside in a separate "
                "<font name='Courier'>ground_truth.json</font> for offline scoring. Diagnostic code and UI "
                "load only <font name='Courier'>incident.json</font> and "
                "<font name='Courier'>observations.json</font>; the loader rejects answer fields in public "
                "input. Source-kind metadata distinguishes a captured local run from an official-Shop run or "
                "a synthetic unit-test fixture."),
              caption("Figure 3. Final implemented architecture and isolated evaluator. The official-Shop adapter is staged, not live-verified."),
              ArchitectureDiagram(),
              section("7. Methods and grounding"),
              p("Python computes windows, HTTP counts, features, trace relationships, and raw-link checks. A "
                "deterministic baseline scores explicit errors/anomalies, caps duplicate records per signal "
                "kind, and uses bounded trace direction as a priority hint. Scores are not probabilities. "
                "It abstains when evidence is absent, only one kind supports the leader, or leaders tie. "
                "Gemini 3.5 Flash-Lite is optional: it sees at most 48 compact, public observations, returns "
                "a candidate/reason/evidence IDs/missing evidence, and is called only after local-user opt-in."),
              p("The grounded path prioritizes anomalous and error observations before prompting. This is "
                "metadata/rule-based retrieval, <b>not</b> a vector database, a trained RAG index, fine-tuning, "
                "or a multi-agent diagnosis. The validator rejects unsupported claims with unknown cited IDs "
                "and requires two cited "
                "signal kinds for a supported grounded output. The interface resolves citations to the "
                "original record. Referential integrity does not prove a citation is causally relevant."),
              PageBreak()]

    # Page 4: working application visual evidence.
    story += [section("8. Working application feature"),
              p("The local Streamlit app selects a captured case, shows its provenance and symptom, runs the "
                "deterministic analysis, optionally calls Gemini, lists candidate services, exposes source "
                "records, and accepts a reasoned human review. English and Chinese UI text are available. "
                "The review form now requires an explicit judgment; it does not preselect 'accept.' The "
                "model path was exercised in the UI on a local capacity case: Gemini returned payment from "
                "48 visible records in 1,257 ms. This is one interaction, not a held-out accuracy estimate."),
              screenshot("autotriager-gemini-local.png", (370, 445, 1350, 1000), 470),
              caption("Figure 4. Genuine local application screenshot. The case came from this project's native simulator, not an official Astronomy Shop deployment. Model output is an investigation priority."),
              p("The separate storefront makes the scenario tangible. In the live smoke test, a normal test "
                "order returned HTTP 200; after the payment fault switch, the same endpoint returned HTTP 502; "
                "the fault was then reset. The frontend, checkout, catalog, and payment processes each wrote "
                "raw trace/log records. The screenshot below shows the fault response; the injected label "
                "was never passed to the analysis input."),
              screenshot("local-shop-payment-fault.png", (280, 65, 1010, 550), 230),
              caption("Figure 5. Actual local storefront fault smoke test. It demonstrates a running request path, not enterprise-scale realism."),
              PageBreak()]

    # Page 5: newly generated five-case comparison and failure analysis.
    strong = summary["summary"]["direct_strong"]
    grounded = summary["summary"]["grounded"]
    story += [section("9. Corrected five-case evaluation"),
              p("Earlier development cases had a confounded delay intervention: payment slowed while the "
                "checkout timeout also changed. We excluded their scores. Before the five cases below were "
                "captured, the analysis rule was frozen and checkout's payment timeout fixed at 250 ms in "
                "all phases; the delay mode changes only payment response time. These cases were then run "
                "once through each Gemini configuration without tuning after the results. This is still a "
                "small local simulator, not an independent production or official-Shop estimate."),
              p("The injected service is held in a private evaluator label. Both methods used Gemini 3.5 "
                "Flash-Lite and a maximum 48-record context budget, but the prompt, selected evidence, and "
                "grounded validator differ. Client latency is one model call, not human resolution time. "
                "An API error is not scored as an abstention."),
              tiny_table(["Gemini configuration", "Fault localized", "Clean abstain", "Clean false attribution", "Median API latency"],
                         [["Strong direct", f"{strong['fault_localized']}/4", f"{strong['clean_abstentions']}/1", f"{strong['false_attributions']}/1", f"{strong['median_latency_ms']:,} ms"],
                          ["Evidence-prioritized", f"{grounded['fault_localized']}/4", f"{grounded['clean_abstentions']}/1", f"{grounded['false_attributions']}/1", f"{grounded['median_latency_ms']:,} ms"]],
                         [150, 88, 77, 113, 74]),
              caption("Table 1. Measured five-case local-simulation comparison. The two methods tied on fault localization and clean abstention; no accuracy or speed gain is established."),
              section("Case-level audit"),
    ]
    def name(row: dict | None) -> str:
        if not row:
            return "n/a"
        return row["predicted"] if row["predicted"] != "none" else "abstain"
    order = ["valid-capacity-001", "valid-catalog-001", "valid-checkout-001",
             "valid-delay-001", "valid-clean-001"]
    short = {"valid-capacity-001": "Payment capacity", "valid-catalog-001": "Catalog error",
             "valid-checkout-001": "Checkout error", "valid-delay-001": "Payment delay",
             "valid-clean-001": "Clean control"}
    matrix = []
    for case in order:
        group = case_rows[case]
        expected = group["direct_strong"]["expected"]
        matrix.append([short[case], expected, name(group.get("direct_strong")),
                       name(group.get("grounded")),
                       "miss: abstained" if case == "valid-delay-001" else "correct"])
    story += [tiny_table(["Case", "Injected service", "Strong direct", "Grounded", "Grounded result"],
                         matrix, [107, 98, 95, 95, 107]),
              caption("Table 2. Case-level outputs from four faults and one clean control; each mode ran once per case."),
              p("<b>Failure:</b> the checkout caller timed out around 260 ms, while payment completed an "
                "approximately 550 ms span with OK status. Strong direct incorrectly named checkout. The "
                "grounded path abstained rather than making that false attribution, but also missed the "
                "known payment intervention. This exposes a temporal-evidence gap, not superior localization."),
              p("All ten saved model outputs had nonempty, known citation IDs with resolvable raw links, "
                "including the clean case. A valid pointer does not establish causal relevance. The observed "
                "latency difference is based on five calls per configuration and is not a speed claim. "
                "Differences in selection, prompt, and validation prevent causal attribution of any behavior "
                "to retrieval alone."),
              PageBreak()]

    # Page 6: reproducibility, limitations, future work, primary links.
    story += [section("10. Reproducibility and current boundary"),
              p("The repository includes the four-process simulator, Streamlit app, schema, deterministic "
                "analyzer, Gemini client, capture adapter, tests, result CSV/summary, genuine local screenshots, "
                "and a public replay case without private fault labels. On Windows with Python 3.13, run "
                "<font name='Courier'>py -3.13 -m pip install -r requirements.txt</font>, "
                "<font name='Courier'>py -3.13 -m scripts.seed_example_case</font>, and "
                "<font name='Courier'>py -3.13 -m streamlit run app.py --server.address 127.0.0.1</font>. "
                "To generate a new run, execute "
                "<font name='Courier'>py -3.13 -m native_shop.run_experiment --case-id new-01 --mode payment_error</font>. "
                "Gemini requires a separately configured API key and may have quotas. Never commit the key."),
              p("The official OpenTelemetry Astronomy Shop source is pinned separately to release 3.1.0 at "
                "commit dedc0178918e260823323b8d95005a8cb924b007. A Prometheus/Jaeger capture adapter "
                "and protocol exist, and mocked adapter tests pass; <b>no official-Shop run or capture has "
                "occurred on this host</b>. Windows WSL features were enabled, but a restart plus working "
                "Docker runtime remain necessary. No upstream screenshot is presented as local execution."),
              p("<b>Limits:</b> the native topology is small; injected error logs can be more explicit than "
                "real incidents; five cases on one simulator are not external validation; no independent on-call user "
                "study or time-to-resolution measure exists; source-link validity is weaker than causal "
                "validity; and Gemini output can change with model/API versions. A repository URL remains "
                "pending verified publication. The September 30 course deadline has passed; this report "
                "does not claim on-time submission or an instructor grade."),
              section("11. Next challenge and three uses of the same artifact"),
              p("<b>Challenge 3:</b> capture a controlled incident on a verified official Shop deployment and "
                "show a trace-linked comparison between an initiating service and downstream symptoms. "
                "<b>Challenge 4:</b> test ambiguity under missing/delayed signals; consider concurrent faults "
                "only after a valid labeling protocol. <b>Challenge 5:</b> integrate reproducible setup, "
                "feedback, and a live demonstration. The course gets one complete feature and a candid "
                "evaluation; research gets a falsifiable comparison and future holdout/ablation plan; a "
                "hackathon gets a real fault-to-evidence interaction. None of these implies a publishable "
                "accuracy improvement yet."),
              section("Primary resources"),
              p("[1] Course-provided CS 5588 Challenge 2 report requirements, September 2026.", "SmallCustom"),
              p("[2] OpenTelemetry Demo source and Apache-2.0 license: "
                "https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007", "SmallCustom"),
              p("[3] OpenTelemetry Docker deployment: https://opentelemetry.io/docs/demo/docker-deployment/", "SmallCustom"),
              p("[4] Prometheus range-query API: https://prometheus.io/docs/prometheus/latest/querying/api/", "SmallCustom"),
              p("[5] Gemini API model and pricing documentation: https://ai.google.dev/gemini-api/docs/pricing", "SmallCustom"),
              p("[6] Context only, not test data: OpenRCA https://microsoft.github.io/OpenRCA/; "
                "EviRCA https://arxiv.org/abs/2609.19825", "SmallCustom"),
    ]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
