"""Export research reports and conversations to Markdown, DOCX and PDF with citations intact.

Inline citation labels (``[S1]``) are preserved in the text, and every export ends with a
numbered Sources section mapping each label to its document, location and quoted passage.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_BOLD = re.compile(r"\*\*(.+?)\*\*")


@dataclass
class ExportSource:
    label: str
    document_title: str
    location: str
    passage: str


@dataclass
class ExportSection:
    heading: str | None
    body_markdown: str
    sources: list[ExportSource]


@dataclass
class ExportDocument:
    title: str
    subtitle: str
    sections: list[ExportSection]


def to_markdown(doc: ExportDocument) -> str:
    out = [f"# {doc.title}", "", f"_{doc.subtitle}_", ""]
    for section in doc.sections:
        if section.heading:
            out += [f"## {section.heading}", ""]
        out += [section.body_markdown.strip(), ""]
        if section.sources:
            out += ["**Sources**", ""]
            for s in section.sources:
                where = f" — {s.location}" if s.location else ""
                excerpt = " ".join(s.passage.split())[:400]
                out.append(f"- **[{s.label}]** {s.document_title}{where}: “{excerpt}”")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _markdown_lines(markdown: str) -> list[tuple[str, str]]:
    """Very small Markdown reader: (kind, text) with kind in h1..h3, bullet, para."""
    lines: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            lines.append(("para", " ".join(paragraph)))
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if heading:
            flush()
            lines.append((f"h{min(3, len(heading.group(1)))}", heading.group(2)))
        elif bullet:
            flush()
            lines.append(("bullet", bullet.group(1)))
        else:
            paragraph.append(line.strip())
    flush()
    return lines


def to_docx(doc: ExportDocument) -> bytes:
    import docx
    from docx.shared import Pt, RGBColor

    document = docx.Document()
    document.add_heading(doc.title, level=0)
    sub = document.add_paragraph(doc.subtitle)
    sub.runs[0].italic = True

    def add_rich(paragraph, text: str) -> None:  # type: ignore[no-untyped-def]
        position = 0
        for match in _BOLD.finditer(text):
            paragraph.add_run(text[position : match.start()])
            paragraph.add_run(match.group(1)).bold = True
            position = match.end()
        paragraph.add_run(text[position:])

    for section in doc.sections:
        if section.heading:
            document.add_heading(section.heading, level=1)
        for kind, text in _markdown_lines(section.body_markdown):
            if kind.startswith("h"):
                document.add_heading(text, level=min(3, int(kind[1]) + 1))
            elif kind == "bullet":
                add_rich(document.add_paragraph(style="List Bullet"), text)
            else:
                add_rich(document.add_paragraph(), text)
        if section.sources:
            document.add_heading("Sources", level=2)
            for s in section.sources:
                p = document.add_paragraph()
                label = p.add_run(f"[{s.label}] ")
                label.bold = True
                p.add_run(s.document_title + (f" — {s.location}" if s.location else ""))
                quote = document.add_paragraph(" ".join(s.passage.split())[:600])
                quote.paragraph_format.left_indent = Pt(18)
                for run in quote.runs:
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0x66, 0x70, 0x85)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _unicode_font() -> tuple[str, str] | None:
    for regular in _FONT_CANDIDATES:
        path = Path(regular)
        if path.exists():
            bold = path.with_name(
                path.name.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                .replace("arial.ttf", "arialbd.ttf")
                .replace("Arial.ttf", "Arial Bold.ttf")
            )
            return str(path), str(bold if bold.exists() else path)
    return None


def to_pdf(doc: ExportDocument) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 18, 18)
    font = _unicode_font()
    if font:
        pdf.add_font("Body", "", font[0])
        pdf.add_font("Body", "B", font[1])
        family = "Body"

        def clean(text: str) -> str:
            return text
    else:  # core fonts are Latin-1 only
        family = "Helvetica"

        def clean(text: str) -> str:
            text = (
                text.replace("\u2014", "-")
                .replace("\u2013", "-")
                .replace("\u201c", '"')
                .replace("\u201d", '"')
            )
            return text.replace("\u2019", "'").encode("latin-1", "replace").decode("latin-1")

    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def write(text: str, size: float, style: str = "", gap: float = 1.5, indent: float = 0.0) -> None:
        pdf.set_font(family, style, size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(width - indent, size * 0.5, clean(text), markdown=True)
        pdf.ln(gap)

    write(doc.title, 18, "B", gap=2)
    pdf.set_text_color(102, 112, 133)
    write(doc.subtitle, 9, gap=4)
    pdf.set_text_color(16, 24, 40)
    for section in doc.sections:
        if section.heading:
            write(section.heading, 13, "B", gap=2)
        for kind, text in _markdown_lines(section.body_markdown):
            if kind == "h1":
                write(text, 13, "B")
            elif kind in ("h2", "h3"):
                write(text, 11.5, "B")
            elif kind == "bullet":
                write(f"\u2022 {text}" if font else f"- {text}", 10, indent=4)
            else:
                write(text, 10, gap=2)
        if section.sources:
            write("Sources", 11, "B")
            for s in section.sources:
                write(
                    f"**[{s.label}]** {s.document_title}" + (f" - {s.location}" if s.location else ""),
                    9,
                    gap=0.5,
                )
                pdf.set_text_color(102, 112, 133)
                write(" ".join(s.passage.split())[:600], 8.5, indent=4, gap=2)
                pdf.set_text_color(16, 24, 40)
    return bytes(pdf.output())


def render(doc: ExportDocument, fmt: str) -> tuple[bytes, str, str]:
    """Return ``(content, media_type, extension)``."""
    if fmt == "md":
        return to_markdown(doc).encode("utf-8"), "text/markdown; charset=utf-8", "md"
    if fmt == "docx":
        return to_docx(doc), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
    if fmt == "pdf":
        return to_pdf(doc), "application/pdf", "pdf"
    raise ValueError(f"Unsupported export format: {fmt}")


def safe_filename(title: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().replace(" ", "-")[:80] or "retrieva-export"
    return f"{stem}-{datetime.now(UTC):%Y%m%d}"


def sources_from_evidence(evidence: list[dict], cited: set[str] | None = None) -> list[ExportSource]:
    out = []
    for e in evidence:
        if cited is not None and e.get("label") not in cited:
            continue
        out.append(
            ExportSource(
                label=e.get("label", ""),
                document_title=e.get("document_title", ""),
                location=e.get("location") or "",
                passage=e.get("content") or e.get("passage") or "",
            )
        )
    return out
