"""
PDF renderer — converts an Artifact to a PDF document.
Requires: pip install xybernetex[pdf]   (reportlab, markdown)
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xybernetex._models import Artifact

_MISSING = (
    "reportlab and markdown are required for PDF export.\n"
    "Install them with:  pip install xybernetex[pdf]"
)


def render_pdf(artifact: "Artifact", path: str) -> str:
    """
    Write *artifact* to a PDF at *path*.

    If *path* is a directory the file is named after the artifact title.
    Returns the path of the written file.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Preformatted,
            Table, TableStyle, HRFlowable,
        )
        from reportlab.platypus import ListFlowable, ListItem
    except ImportError:
        raise ImportError(_MISSING) from None

    from xybernetex._export._markdown import parse, inline_text
    from xybernetex._models import _safe_filename

    dest = _resolve_path(path, artifact.title, ".pdf")
    dest.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=artifact.title,
        author="Xybernetex",
    )

    styles = getSampleStyleSheet()

    # ── Custom styles ──────────────────────────────────────────────────────────
    style_title = ParagraphStyle(
        "XTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=4,
        textColor=colors.HexColor("#1A1A2E"),
    )
    style_subtitle = ParagraphStyle(
        "XSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#888888"),
        spaceAfter=16,
    )
    style_h1 = ParagraphStyle("XH1", parent=styles["Heading1"], fontSize=16, spaceBefore=14, spaceAfter=4)
    style_h2 = ParagraphStyle("XH2", parent=styles["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=3)
    style_h3 = ParagraphStyle("XH3", parent=styles["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=2)
    style_body = ParagraphStyle("XBody", parent=styles["Normal"], fontSize=10, leading=15, spaceAfter=6)
    style_code = ParagraphStyle(
        "XCode",
        parent=styles["Code"],
        fontSize=8,
        leading=11,
        backColor=colors.HexColor("#F2F2F2"),
        leftIndent=10,
        rightIndent=10,
        spaceAfter=8,
        fontName="Courier",
    )
    style_bullet = ParagraphStyle(
        "XBullet", parent=style_body, leftIndent=18, bulletIndent=6, spaceAfter=2
    )

    _heading_styles = {1: style_h1, 2: style_h2, 3: style_h3}

    story = []

    # ── Title block ────────────────────────────────────────────────────────────
    story.append(Paragraph(_rl_escape(artifact.title), style_title))
    story.append(Paragraph(artifact.artifact_type.replace("_", " ").title(), style_subtitle))

    # ── Body ───────────────────────────────────────────────────────────────────
    for block in parse(artifact.content):
        btype = block["type"]

        if btype == "heading":
            level = min(block["level"], 3)
            s = _heading_styles.get(level, style_h3)
            story.append(Paragraph(_rl_escape(block["text"]), s))

        elif btype == "paragraph":
            story.append(Paragraph(_rl_inline(block["text"]), style_body))

        elif btype == "code":
            story.append(Preformatted(block["text"], style_code))

        elif btype == "bullet_list":
            items = [
                ListItem(Paragraph(_rl_inline(it), style_bullet), bulletColor=colors.HexColor("#555"))
                for it in block["items"]
            ]
            story.append(ListFlowable(items, bulletType="bullet", start="•"))

        elif btype == "ordered_list":
            items = [
                ListItem(Paragraph(_rl_inline(it), style_bullet))
                for it in block["items"]
            ]
            story.append(ListFlowable(items, bulletType="1"))

        elif btype == "table":
            headers = block["headers"]
            rows = block["rows"]
            if not headers:
                continue
            col_count = max(len(headers), max((len(r) for r in rows), default=0))
            data = [headers[:col_count]] + [r[:col_count] for r in rows]
            # Pad short rows
            data = [row + [""] * (col_count - len(row)) for row in data]

            tbl = Table(data, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1A2E")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
                ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 8))

        elif btype == "hr":
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC"), spaceAfter=6))

    doc.build(story)
    return str(dest)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_path(path: str, title: str, ext: str) -> Path:
    from xybernetex._models import _safe_filename
    p = Path(path)
    if p.is_dir():
        p = p / f"{_safe_filename(title)}{ext}"
    return p


def _rl_escape(text: str) -> str:
    """Escape characters that reportlab treats as XML markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rl_inline(text: str) -> str:
    """Convert Markdown inline formatting to reportlab XML tags."""
    import re
    text = _rl_escape(text)
    # Bold+italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*",   r"<i>\1</i>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r'<font name="Courier" size="9">\1</font>', text)
    # Links — keep the label
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text
