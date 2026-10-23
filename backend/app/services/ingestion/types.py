"""Data structures shared by the ingestion stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list", "table", "code", "row"]


@dataclass
class Block:
    """A structural unit of a document (heading, paragraph, table, ...).

    ``heading_path`` is the chain of headings above this block, e.g.
    ``["4 Termination", "4.2 Termination for Convenience"]``.
    """

    text: str
    kind: BlockKind = "paragraph"
    page: int | None = None
    level: int = 0  # heading level (1 = top) for headings
    heading_path: list[str] = field(default_factory=list)
    # Character offsets into ExtractedDocument.full_text, assigned by ``finalize``.
    start: int = 0
    end: int = 0


@dataclass
class ExtractedDocument:
    blocks: list[Block]
    page_count: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    full_text: str = ""

    def finalize(self) -> ExtractedDocument:
        """Assign heading paths and character offsets; build ``full_text``."""
        path: list[tuple[int, str]] = []
        parts: list[str] = []
        cursor = 0
        for block in self.blocks:
            if block.kind == "heading":
                level = max(1, block.level)
                path = [(lvl, txt) for lvl, txt in path if lvl < level]
                path.append((level, block.text))
                block.heading_path = [txt for _, txt in path]
            else:
                block.heading_path = [txt for _, txt in path]
            block.start = cursor
            parts.append(block.text)
            cursor += len(block.text)
            block.end = cursor
            parts.append("\n\n")
            cursor += 2
        self.full_text = "".join(parts).rstrip()
        return self

    def to_json(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "metadata": self.metadata,
            "blocks": [asdict(b) for b in self.blocks],
        }


@dataclass
class Chunk:
    text: str
    index: int
    token_count: int
    page_start: int | None
    page_end: int | None
    heading_path: list[str]
    start: int
    end: int
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def section(self) -> str | None:
        return self.heading_path[-1] if self.heading_path else None
