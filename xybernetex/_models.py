from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass


@dataclass
class Event:
    """A single event emitted during an agent run."""

    type: str
    run_id: str
    data: dict = field(default_factory=dict)

    # ── Convenience accessors ──────────────────────────────────────────────────

    @property
    def step_number(self) -> Optional[int]:
        return self.data.get("step_number")

    @property
    def action_type(self) -> Optional[str]:
        return self.data.get("action_type")

    @property
    def focus(self) -> Optional[str]:
        return self.data.get("focus")

    @property
    def reward(self) -> Optional[float]:
        return self.data.get("reward")

    @property
    def artifact_id(self) -> Optional[int]:
        return self.data.get("artifact_id")

    @property
    def artifact_type(self) -> Optional[str]:
        return self.data.get("artifact_type")

    @property
    def title(self) -> Optional[str]:
        return self.data.get("title")

    @property
    def preview(self) -> Optional[str]:
        return self.data.get("preview")

    @property
    def conclusion(self) -> Optional[str]:
        return self.data.get("conclusion")

    @property
    def error(self) -> Optional[str]:
        return self.data.get("error")

    @property
    def artifact_count(self) -> Optional[int]:
        return self.data.get("artifact_count")

    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, run_id={self.run_id!r})"


class Artifact:
    """A structured output produced by an agent run."""

    def __init__(self, *, id: int, artifact_type: str, title: str, content: str):
        self.id = id
        self.artifact_type = artifact_type
        self.title = title
        self.content = content

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self, path: str, *, encoding: str = "utf-8") -> str:
        """
        Save the artifact as a Markdown file.

        If *path* is a directory, the file is named after the artifact title.
        Returns the path of the written file.
        """
        dest = Path(path)
        if dest.is_dir():
            safe = _safe_filename(self.title)
            dest = dest / f"{safe}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.content, encoding=encoding)
        return str(dest)

    # ── Export ─────────────────────────────────────────────────────────────────

    def to_docx(self, path: str) -> str:
        """
        Export to a Word document (.docx).
        Requires: ``pip install xybernetex[docx]``
        """
        from xybernetex._export._docx import render_docx
        return render_docx(self, path)

    def to_pdf(self, path: str) -> str:
        """
        Export to a PDF document.
        Requires: ``pip install xybernetex[pdf]``
        """
        from xybernetex._export._pdf import render_pdf
        return render_pdf(self, path)

    def to_xlsx(self, path: str) -> str:
        """
        Export to an Excel workbook (.xlsx).
        Best used with artifacts whose content contains Markdown tables.
        Requires: ``pip install xybernetex[xlsx]``
        """
        from xybernetex._export._xlsx import render_xlsx
        return render_xlsx(self, path)

    def to_pptx(self, path: str) -> str:
        """
        Export to a PowerPoint presentation (.pptx).
        Requires: ``pip install xybernetex[pptx]``
        """
        from xybernetex._export._pptx import render_pptx
        return render_pptx(self, path)

    def __repr__(self) -> str:
        return (
            f"Artifact(id={self.id}, type={self.artifact_type!r}, "
            f"title={self.title!r})"
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_filename(text: str, max_len: int = 80) -> str:
    """Convert a title to a filesystem-safe filename (no extension)."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in text)
    return safe.strip()[:max_len] or "artifact"


def _artifact_from_dict(data: dict) -> Artifact:
    return Artifact(
        id=data.get("id", 0),
        artifact_type=data.get("artifact_type", ""),
        title=data.get("title", ""),
        content=data.get("content", ""),
    )
