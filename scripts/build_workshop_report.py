"""Render the current workshop Markdown as an inspectable English PDF.

Run with the bundled workspace Python (ReportLab and Pillow required). This
script reads the source afresh, never calls a model or mutates a runtime, and
does not run the artifact-operation marker. The authoring session runs that
marker once, before using this builder. Wide tables and real screenshots are
placed in full-width appendices rather than shrinking them into a column.
"""

from __future__ import annotations

import argparse
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, Image, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "OFFICIAL_SHOP_WORKSHOP_DRAFT.md"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "AutoTriager_Challenge2_OfficialShop_Dahe_Chen_Final.pdf"
PAGE_W, PAGE_H = letter
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM, GUTTER = 44.0, 42.0, 43.0, 18.0
FULL_W = PAGE_W - 2 * MARGIN_X
COL_W = (FULL_W - GUTTER) / 2
BODY_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM


def printable(value: str) -> str:
    """Normalize punctuation unsupported by the standard PDF Times fonts."""
    replacements = {
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2212": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
        "\u202f": " ", "\u2009": " ", "\u2192": " -> ", "\u2190": " <- ",
        "\u2194": " <-> ", "\u2264": "<=", "\u2265": ">=", "\u00d7": "x",
        "\u2500": "-", "\u2502": "|", "\u03b1": "alpha", "\u03b2": "beta",
        "\u03b3": "gamma", "\u03b4": "delta", "\u03bc": "mu",
        "\u03c3": "sigma", "\u03c4": "tau", "\u0394": "Delta",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


INLINE = re.compile(r"\[([^\]]+)\]\(([^\s]+)\)|\*\*(.+?)\*\*|`([^`]+)`|(?<!\*)\*([^*]+)\*(?!\*)")


def markup(text: str) -> str:
    """Translate a small Markdown inline subset into safe Paragraph markup."""
    text = printable(text)
    output, last = [], 0
    for match in INLINE.finditer(text):
        output.append(escape(text[last:match.start()]))
        label, target, bold, code, italic = match.groups()
        if target is not None:
            output.append(f'<link href={quoteattr(target)} color="black"><u>{escape(label)}</u></link>')
        elif bold is not None:
            output.append(f"<b>{escape(bold)}</b>")
        elif code is not None:
            output.append(f'<font name="Courier" size="8.0">{escape(code)}</font>')
        else:
            output.append(f"<i>{escape(italic)}</i>")
        last = match.end()
    output.append(escape(text[last:]))
    return "".join(output)


def make_styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Times-Roman", fontSize=9.3, leading=11.2,
                textColor=colors.black, splitLongWords=True, allowWidows=0,
                allowOrphans=0)
    styles = {
        "body": ParagraphStyle("WorkshopBody", alignment=TA_JUSTIFY,
                               spaceAfter=4.0, **base),
        "heading": ParagraphStyle("WorkshopHeading", fontName="Times-Bold",
                                  fontSize=10.8, leading=12.5, spaceBefore=8,
                                  spaceAfter=4, keepWithNext=True),
        "subheading": ParagraphStyle("WorkshopSubheading", fontName="Times-Bold",
                                     fontSize=9.7, leading=11.7, spaceBefore=6,
                                     spaceAfter=3, keepWithNext=True),
        "caption": ParagraphStyle("WorkshopCaption", fontName="Times-Italic",
                                  fontSize=8.0, leading=9.6, spaceAfter=7,
                                  splitLongWords=True),
        "table": ParagraphStyle("WorkshopTable", fontName="Times-Roman",
                                fontSize=7.2, leading=8.5, splitLongWords=True),
        "table_head": ParagraphStyle("WorkshopTableHead", fontName="Times-Bold",
                                     fontSize=7.2, leading=8.5, splitLongWords=True),
        "wide_table": ParagraphStyle("WorkshopWideTable", fontName="Times-Roman",
                                     fontSize=8.2, leading=10.0, splitLongWords=True),
        "wide_table_head": ParagraphStyle("WorkshopWideTableHead", fontName="Times-Bold",
                                          fontSize=8.2, leading=10.0, splitLongWords=True),
        "flow": ParagraphStyle("WorkshopFlow", fontName="Times-Roman",
                               fontSize=8.2, leading=9.7, alignment=TA_CENTER),
        "title": ParagraphStyle("WorkshopTitle", fontName="Times-Bold",
                                fontSize=17.0, leading=19.2, alignment=TA_CENTER),
        "author": ParagraphStyle("WorkshopAuthor", fontName="Times-Roman",
                                 fontSize=10.0, leading=12.0, alignment=TA_CENTER),
        "status": ParagraphStyle("WorkshopStatus", fontName="Times-Roman",
                                 fontSize=8.0, leading=9.5, alignment=TA_LEFT),
    }
    styles["bullet"] = ParagraphStyle("WorkshopBullet", parent=styles["body"],
                                      leftIndent=10, firstLineIndent=0,
                                      bulletIndent=0, alignment=TA_LEFT)
    return styles


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    rows: list[list[str]] = field(default_factory=list)
    language: str = ""
    target: str = ""
    caption: str = ""


def table_cells(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in
            re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parse_markdown(text: str) -> list[Block]:
    lines, blocks, index = text.lstrip("\ufeff").splitlines(), [], 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            language, raw = line[3:].strip(), []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                raw.append(lines[index])
                index += 1
            blocks.append(Block("code", "\n".join(raw), language=language))
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            blocks.append(Block("heading", heading.group(2), level=len(heading.group(1))))
            index += 1
            continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if image:
            blocks.append(Block("image", image.group(1), target=image.group(2)))
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = table_cells(lines[index])
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row):
                    rows.append(row)
                index += 1
            blocks.append(Block("table", rows=rows))
            continue
        bullet = re.match(r"^([-*]|\d+[.)])\s+(.+)$", line)
        if bullet:
            blocks.append(Block("bullet", bullet.group(2), target=bullet.group(1)))
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            following = lines[index].strip()
            if (following.startswith(("#", "```", "|", "!["))
                    or re.match(r"^([-*]|\d+[.)])\s+", following)):
                break
            paragraph.append(following)
            index += 1
        blocks.append(Block("paragraph", " ".join(paragraph)))
    # Attach authored captions to their actual preceding figure/table.
    combined = []
    for block in blocks:
        if (block.kind == "paragraph" and combined
                and combined[-1].kind in {"table", "image", "code"}
                and re.match(r"^\*\*(Table|Figure)\s+\d", block.text)):
            combined[-1].caption = block.text
        else:
            combined.append(block)
    return combined


class VectorWorkflow(Flowable):
    """Render only labels present in the authored text/Mermaid as vector boxes."""

    def __init__(self, source: str, language: str, styles: dict):
        super().__init__()
        self.styles = styles
        self.branch = []
        self.nodes = []
        self.connect_sequence = language.lower() != "mermaid"
        if language.lower() == "mermaid":
            # Preserve authored relations instead of inventing a sequential
            # graph from a branched Mermaid declaration. Render clean text
            # relationships with resolved labels inside vector boxes.
            declaration = re.compile(r"\b([A-Za-z_]\w*)\s*\[\s*([^]]+)\]")
            labels = {match.group(1): re.sub(r"<br\s*/?>", "; ", match.group(2)).strip('"\' ')
                      for match in declaration.finditer(source)}
            for line in source.splitlines():
                if not line.strip() or re.match(r"\s*(graph|flowchart|classDef|class|style)\b", line):
                    continue
                relation = declaration.sub(lambda match: match.group(1), line.strip())
                relation = re.sub(r"\b[A-Za-z_]\w*\b", lambda match: labels.get(match.group(0), match.group(0)), relation)
                self.nodes.append(printable(relation))
        if not self.nodes:
            for line in source.splitlines():
                if not line.strip():
                    continue
                if "private" in line.lower() or "evaluator" in line.lower():
                    self.branch.append(printable(line.strip()))
                else:
                    self.nodes.extend(part.strip(" -") for part in
                                      re.split(r"→|\s+->\s+", line.strip()) if part.strip(" -"))
        if not self.nodes:
            self.nodes = [printable(line) for line in source.splitlines() if line.strip()]

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self.width = min(avail_width, COL_W)
        self.boxes = []
        for node in self.nodes:
            paragraph = Paragraph(escape(printable(node)), self.styles["flow"])
            _, text_h = paragraph.wrap(self.width - 20, 1000)
            self.boxes.append((paragraph, max(text_h + 8, 22)))
        self.branch_paragraph = None
        branch_h = 0
        if self.branch:
            self.branch_paragraph = Paragraph(
                "<b>Separate evaluation path</b><br/>" +
                "<br/>".join(escape(row) for row in self.branch), self.styles["flow"])
            _, text_h = self.branch_paragraph.wrap(self.width - 16, 1000)
            branch_h = text_h + 10
        self.height = sum(height for _, height in self.boxes) + 10 * max(len(self.boxes) - 1, 0)
        self.height += branch_h + (10 if branch_h else 0) + 4
        return self.width, self.height

    def draw(self) -> None:
        canvas, y = self.canv, self.height - 2
        canvas.setStrokeColor(colors.black)
        canvas.setFillColor(colors.white)
        canvas.setLineWidth(0.55)
        for index, (paragraph, height) in enumerate(self.boxes):
            y -= height
            canvas.roundRect(0, y, self.width, height, 2, fill=0, stroke=1)
            paragraph.drawOn(canvas, 10, y + (height - paragraph.height) / 2)
            if index < len(self.boxes) - 1 and self.connect_sequence:
                center = self.width / 2
                canvas.line(center, y - 1, center, y - 9)
                canvas.line(center - 2.5, y - 6, center, y - 9)
                canvas.line(center + 2.5, y - 6, center, y - 9)
                y -= 10
        if self.branch_paragraph:
            y -= self.branch_paragraph.height + 20
            canvas.setDash(2, 2)
            canvas.roundRect(0, y, self.width, self.branch_paragraph.height + 10,
                             2, fill=0, stroke=1)
            canvas.setDash()
            self.branch_paragraph.drawOn(canvas, 8, y + 5)


def render_table(block: Block, width: float, styles: dict, wide: bool) -> Table:
    count = len(block.rows[0])
    if any(len(row) != count for row in block.rows):
        raise ValueError("Markdown table has inconsistent cell counts")
    if count == 3:
        weights = (0.24, 0.43, 0.33) if not wide else (0.26, 0.35, 0.39)
    elif count == 4:
        weights = (0.18, 0.25, 0.25, 0.32)
    elif count == 5:
        weights = (0.22, 0.17, 0.18, 0.215, 0.215)
    else:
        weights = [1 / count] * count
    # Inline code is reduced only to 8 pt; all ordinary table text >= 7.2 pt.
    cell_style = styles["wide_table" if wide else "table"]
    head_style = styles["wide_table_head" if wide else "table_head"]
    data = [[Paragraph(markup(cell), head_style if index == 0 else cell_style)
             for cell in row] for index, row in enumerate(block.rows)]
    table = Table(data, colWidths=[width * ratio for ratio in weights],
                  hAlign="LEFT", repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("LINEABOVE", (0, 0), (-1, 0), 0.65, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.2, colors.HexColor("#bbbbbb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def render_image(path: Path, width: float) -> Image:
    with PILImage.open(path) as original:
        gray = ImageOps.grayscale(original)
        buffer = io.BytesIO()
        gray.save(buffer, format="PNG")
        buffer.seek(0)
        image = Image(buffer)
        scale = min(width / gray.width, 315.0 / gray.height)
        image.drawWidth, image.drawHeight = gray.width * scale, gray.height * scale
        image.hAlign = "CENTER"
        return image


class WorkshopDocument(BaseDocTemplate):
    def __init__(self, destination: Path, title: str, preface: list[Block], styles: dict):
        self.title_text, self.preface, self.styles = title, preface, styles
        self.title_items = [Paragraph(markup(title), styles["title"])]
        self.title_items += [Paragraph(markup(block.text), styles["author"] if index == 0
                                      else styles["status"])
                             for index, block in enumerate(preface)]
        self.title_h = sum(item.wrap(FULL_W, 1000)[1] + 5 for item in self.title_items) + 10
        super().__init__(str(destination), pagesize=letter, leftMargin=MARGIN_X,
                         rightMargin=MARGIN_X, topMargin=MARGIN_TOP,
                         bottomMargin=MARGIN_BOTTOM, title=printable(title),
                         author="Dahe Chen", subject="CS 5588 Challenge 2 workshop-style course report",
                         pageCompression=1, allowSplitting=1)
        def column_frames(height: float):
            return [Frame(MARGIN_X + index * (COL_W + GUTTER), MARGIN_BOTTOM,
                          COL_W, height, leftPadding=0, rightPadding=0,
                          topPadding=0, bottomPadding=0, id=f"col-{index}")
                    for index in range(2)]
        self.addPageTemplates([
            PageTemplate("First", frames=column_frames(BODY_H - self.title_h),
                         onPage=self.draw_first, autoNextPageTemplate="Main"),
            PageTemplate("Main", frames=column_frames(BODY_H), onPage=self.draw_page),
            PageTemplate("Appendix", frames=[Frame(MARGIN_X, MARGIN_BOTTOM,
                         FULL_W, BODY_H, leftPadding=0, rightPadding=0,
                         topPadding=0, bottomPadding=0, id="wide")], onPage=self.draw_page),
        ])

    def draw_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 7)
        canvas.setFillColor(colors.black)
        canvas.drawString(MARGIN_X, PAGE_H - 24, "AutoTriager Shop | CS 5588 - Challenge 2")
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 24, "Dahe Chen")
        canvas.setLineWidth(0.3)
        canvas.line(MARGIN_X, 30, PAGE_W - MARGIN_X, 30)
        canvas.drawString(MARGIN_X, 19, "Workshop-style course report")
        canvas.drawRightString(PAGE_W - MARGIN_X, 19, str(doc.page))
        canvas.restoreState()

    def draw_first(self, canvas, doc):
        self.draw_page(canvas, doc)
        y = PAGE_H - MARGIN_TOP
        for paragraph in self.title_items:
            _, height = paragraph.wrap(FULL_W, 1000)
            y -= height
            paragraph.drawOn(canvas, MARGIN_X, y)
            y -= 5


def build(source: Path, destination: Path, add_context_images: bool = True) -> dict:
    source, destination = source.resolve(), destination.resolve()
    blocks = parse_markdown(source.read_text(encoding="utf-8"))
    if not blocks or blocks[0].kind != "heading":
        raise ValueError("Workshop source must begin with a Markdown title")
    title = blocks.pop(0).text
    preface = []
    while blocks and blocks[0].kind == "paragraph":
        block = blocks.pop(0)
        author_and_status = re.match(r"^(\*\*Dahe Chen.+?\*\*)\s+(.+)$", block.text)
        if author_and_status:
            preface.extend([Block("paragraph", author_and_status.group(1)),
                            Block("paragraph", author_and_status.group(2))])
        else:
            preface.append(block)
    styles, story, wide_tables, images, warnings = make_styles(), [], [], [], []
    appendix_mode = False
    for block in blocks:
        if block.kind == "heading":
            if block.text.lower().startswith("appendix") and not appendix_mode:
                story.extend([NextPageTemplate("Appendix"), PageBreak()])
                appendix_mode = True
            story.append(Paragraph(markup(block.text),
                                   styles["heading" if block.level <= 2 else "subheading"]))
        elif block.kind == "paragraph":
            style = styles["caption"] if re.match(r"^\*\*(Table|Figure)\s", block.text) else styles["body"]
            story.append(Paragraph(markup(block.text), style))
        elif block.kind == "bullet":
            marker = "-" if block.target in {"*", "-"} else block.target
            story.append(Paragraph(markup(block.text), styles["bullet"], bulletText=marker))
        elif block.kind == "table":
            if len(block.rows[0]) >= 4 and not appendix_mode:
                wide_tables.append(block)
                label = re.search(r"Table\s+\d+", block.caption)
                reference = label.group(0) if label else "The comparison table"
                story.append(Paragraph(f"<i>{reference} is reproduced at full width in Appendix B.</i>",
                                       styles["caption"]))
            else:
                table = render_table(block, FULL_W if appendix_mode else COL_W, styles, appendix_mode)
                caption = Paragraph(markup(block.caption), styles["caption"]) if block.caption else Spacer(1, 5)
                width = FULL_W if appendix_mode else COL_W
                height = table.wrap(width, 1000)[1] + caption.wrap(width, 1000)[1]
                story.append(KeepTogether([table, caption]) if height < BODY_H - 20 else table)
                if height >= BODY_H - 20 and block.caption:
                    story.append(caption)
        elif block.kind == "code":
            diagram = VectorWorkflow(block.text, block.language, styles)
            caption = Paragraph(markup(block.caption), styles["caption"]) if block.caption else Spacer(1, 5)
            story.append(KeepTogether([diagram, caption]))
        elif block.kind == "image":
            image_path = (source.parent / block.target).resolve()
            if image_path.is_file():
                images.append((image_path, block.caption or block.text))
                label = re.search(r"Figure\s+\d+", block.caption)
                reference = label.group(0) if label else "The recorded image"
                story.append(Paragraph(f"<i>{reference} appears at full width in Appendix C.</i>",
                                       styles["caption"]))
            else:
                message = f"Referenced image is unavailable: {block.target}"
                warnings.append(message)
                story.append(Paragraph(escape(message), styles["caption"]))
    if wide_tables:
        if not appendix_mode:
            story.extend([NextPageTemplate("Appendix"), PageBreak()])
        else:
            story.append(Spacer(1, 9))
        story.append(Paragraph("Appendix B. Full-width comparison tables", styles["heading"]))
        for block in wide_tables:
            table = render_table(block, FULL_W, styles, True)
            caption = Paragraph(markup(block.caption), styles["caption"])
            story.append(KeepTogether([table, caption]))
    if add_context_images:
        known_images = {path for path, _ in images}
        for filename, caption in [
            ("official_shop_home_20261001.jpg",
             "Recorded official Shop storefront on October 1, 2026. This is runtime visual evidence, not a diagnostic score."),
            ("official_case_app_20261001.jpg",
             "Recorded application view using an official captured case. Diagnostic correctness is assessed separately."),
        ]:
            path = ROOT / "results" / "screenshots" / filename
            if path.is_file() and path.resolve() not in known_images:
                images.append((path.resolve(), caption))
    if images:
        if not appendix_mode and not wide_tables:
            story.append(NextPageTemplate("Appendix"))
        story.extend([PageBreak(), Paragraph("Appendix C. Recorded application and runtime views", styles["heading"])])
        for path, caption in images:
            story.append(KeepTogether([render_image(path, FULL_W),
                                      Paragraph(markup(caption), styles["caption"])]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = WorkshopDocument(destination, title, preface, styles)
    document.build(story)
    return {"source": str(source), "output": str(destination), "pages": document.page,
            "wide_tables": len(wide_tables), "screenshots": len(images), "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-context-images", action="store_true",
                        help="Only include images explicitly referenced by the source")
    arguments = parser.parse_args()
    import json
    print(json.dumps(build(arguments.source, arguments.output,
                           not arguments.no_context_images), indent=2))


if __name__ == "__main__":
    main()
