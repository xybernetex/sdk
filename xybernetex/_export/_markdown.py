"""
Minimal Markdown → structured block parser used by all export renderers.

Produces a flat list of typed block dicts that each renderer converts into
its native format (python-docx paragraphs, reportlab flowables, etc.).

Block types
-----------
- ``{"type": "heading",       "level": int, "text": str}``
- ``{"type": "paragraph",     "text": str}``
- ``{"type": "code",          "lang": str,  "text": str}``
- ``{"type": "bullet_list",   "items": list[str]}``
- ``{"type": "ordered_list",  "items": list[str]}``
- ``{"type": "table",         "headers": list[str], "rows": list[list[str]]}``
- ``{"type": "hr"}``
"""
from __future__ import annotations

import re
from typing import Iterator


def parse(text: str) -> list[dict]:
    """Parse a Markdown string into a list of block dicts."""
    blocks: list[dict] = []
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ──────────────────────────────────────────────────
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({"type": "code", "lang": lang, "text": "\n".join(code_lines)})
            i += 1
            continue

        # ── Horizontal rule ────────────────────────────────────────────────────
        if re.match(r"^[-*_]{3,}\s*$", line):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # ── ATX headings (# to ######) ─────────────────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # ── Setext headings (underline style) ─────────────────────────────────
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if re.match(r"^=+\s*$", next_line) and line.strip():
                blocks.append({"type": "heading", "level": 1, "text": line.strip()})
                i += 2
                continue
            if re.match(r"^-+\s*$", next_line) and line.strip():
                blocks.append({"type": "heading", "level": 2, "text": line.strip()})
                i += 2
                continue

        # ── Table ──────────────────────────────────────────────────────────────
        if "|" in line and i + 1 < len(lines) and re.match(r"^[\s|:-]+$", lines[i + 1]):
            table_lines = [line]
            j = i + 2
            while j < len(lines) and "|" in lines[j]:
                table_lines.append(lines[j])
                j += 1
            headers = _split_table_row(table_lines[0])
            rows = [_split_table_row(r) for r in table_lines[2:]]
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            i = j
            continue

        # ── Unordered list ─────────────────────────────────────────────────────
        if re.match(r"^[\-\*\+]\s+", line):
            items: list[str] = []
            while i < len(lines) and re.match(r"^[\-\*\+]\s+", lines[i]):
                items.append(re.sub(r"^[\-\*\+]\s+", "", lines[i]))
                i += 1
            blocks.append({"type": "bullet_list", "items": items})
            continue

        # ── Ordered list ───────────────────────────────────────────────────────
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                i += 1
            blocks.append({"type": "ordered_list", "items": items})
            continue

        # ── Blank line — skip ──────────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Paragraph (collect consecutive non-empty, non-special lines) ──────
        para_lines: list[str] = []
        while i < len(lines):
            l = lines[i]
            if not l.strip():
                break
            if (
                re.match(r"^#{1,6}\s", l)
                or re.match(r"^[\-\*\+]\s+", l)
                or re.match(r"^\d+\.\s+", l)
                or l.startswith("```")
                or re.match(r"^[-*_]{3,}\s*$", l)
                or ("|" in l and i + 1 < len(lines) and re.match(r"^[\s|:-]+$", lines[i + 1]))
            ):
                break
            para_lines.append(l)
            i += 1
        if para_lines:
            blocks.append({"type": "paragraph", "text": " ".join(para_lines)})
        continue

    return blocks


def inline_text(text: str) -> str:
    """Strip Markdown inline formatting, returning plain text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # italic
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)            # inline code
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)  # links
    return text


def inline_runs(text: str) -> list[dict]:
    """
    Split a paragraph into styled runs for rich renderers.

    Each run: ``{"text": str, "bold": bool, "italic": bool, "code": bool}``
    """
    runs: list[dict] = []
    pattern = re.compile(r"(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)")
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            runs.append({"text": text[pos:m.start()], "bold": False, "italic": False, "code": False})
        raw = m.group(0)
        if raw.startswith("***"):
            runs.append({"text": m.group(2), "bold": True, "italic": True, "code": False})
        elif raw.startswith("**"):
            runs.append({"text": m.group(3), "bold": True, "italic": False, "code": False})
        elif raw.startswith("*"):
            runs.append({"text": m.group(4), "bold": False, "italic": True, "code": False})
        elif raw.startswith("`"):
            runs.append({"text": m.group(5), "bold": False, "italic": False, "code": True})
        pos = m.end()
    if pos < len(text):
        runs.append({"text": text[pos:], "bold": False, "italic": False, "code": False})
    return runs or [{"text": text, "bold": False, "italic": False, "code": False}]


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [inline_text(c.strip()) for c in cells]
