"""Unit tests for extraction, cleaning and chunking (no database)."""

from __future__ import annotations

import re

import numpy as np
import pytest
from fixtures import make_docx, make_markdown, make_pdf

from app.services.ingestion.chunking import ChunkingConfig, chunk_document
from app.services.ingestion.cleaning import clean_blocks, normalize_text, strip_page_furniture
from app.services.ingestion.extractors import ExtractionError, extract
from app.services.ingestion.types import Block, ExtractedDocument
from app.services.text import split_sentences


def _prepared(file_type: str, data: bytes) -> ExtractedDocument:
    doc = extract(file_type, data)
    doc.blocks = clean_blocks(doc.blocks)
    return doc.finalize()


def test_pdf_extraction_keeps_pages_and_headings():
    doc = _prepared("pdf", make_pdf())
    assert doc.page_count == 3
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert "4 Termination" in headings
    termination = next(b for b in doc.blocks if "ninety (90) days" in b.text)
    assert termination.page == 2
    assert termination.heading_path == ["4 Termination"]


def test_pdf_running_header_is_removed():
    doc = _prepared("pdf", make_pdf())
    assert "Confidential" not in doc.full_text


def test_docx_extraction_headings_and_tables():
    doc = _prepared("docx", make_docx())
    kinds = {b.kind for b in doc.blocks}
    assert {"heading", "paragraph", "table"} <= kinds
    table = next(b for b in doc.blocks if b.kind == "table")
    assert "| Premium | 96,000 USD |" in table.text
    fees = next(b for b in doc.blocks if "48,000 USD" in b.text and b.kind == "paragraph")
    assert fees.heading_path[-1] == "2 Fees and Payment"


def test_markdown_extraction_heading_hierarchy():
    doc = _prepared("md", make_markdown())
    block = next(b for b in doc.blocks if "AES-256" in b.text)
    assert block.heading_path == ["Master Services Agreement", "3 Data Protection"]


def test_html_extraction_drops_scripts_and_keeps_structure():
    html = b"""<html><head><title>Policy</title><script>alert('x')</script></head>
    <body><nav>Menu</nav><main><h1>Security Policy</h1><p>Passwords rotate every 90 days.</p>
    <ul><li>Use MFA</li><li>Lock screens</li></ul>
    <table><tr><th>Level</th><th>Owner</th></tr><tr><td>High</td><td>CISO</td></tr></table></main></body></html>"""
    doc = _prepared("html", html)
    assert "alert" not in doc.full_text and "Menu" not in doc.full_text
    assert doc.metadata["title"] == "Policy"
    assert any(b.kind == "table" and "CISO" in b.text for b in doc.blocks)
    assert any(b.kind == "list" and "Use MFA" in b.text for b in doc.blocks)


def test_csv_rows_are_self_describing():
    doc = _prepared("csv", b"region,revenue,year\nEMEA,1200,2023\nAPAC,900,2023\n")
    assert doc.metadata["columns"] == ["region", "revenue", "year"]
    assert "Row 1: region: EMEA; revenue: 1200; year: 2023" in doc.full_text


def test_corrupt_pdf_raises_extraction_error():
    with pytest.raises(ExtractionError):
        extract("pdf", b"%PDF-1.4 this is not really a pdf")


def test_normalize_text_fixes_artifacts():
    raw = "The pro-\ncessing of data uses ﬁles.\x00\n\n\n\nNext"
    assert normalize_text(raw) == "The processing of data uses files.\n\nNext"


def test_strip_page_furniture_removes_repeated_header_and_numbers():
    pages = [f"ACME Corp Annual Report\nBody text {i}.\n{i}" for i in range(1, 6)]
    cleaned = strip_page_furniture(pages)
    assert all("ACME Corp" not in p for p in cleaned)
    assert cleaned[2].strip() == "Body text 3."


def test_split_sentences_handles_abbreviations():
    text = "See e.g. Section 4. The fee is 4.5 million. Dr. Smith approved it."
    assert split_sentences(text) == [
        "See e.g. Section 4.",
        "The fee is 4.5 million.",
        "Dr. Smith approved it.",
    ]


def _long_doc() -> ExtractedDocument:
    blocks = []
    for s in range(3):
        blocks.append(Block(text=f"Section {s}", kind="heading", level=1))
        for p in range(4):
            sentence = f"Paragraph {p} of section {s} discusses topic {s} in detail with several words. "
            blocks.append(Block(text=sentence * 4, kind="paragraph", page=s + 1))
    return ExtractedDocument(blocks=blocks).finalize()


@pytest.mark.parametrize("strategy", ["recursive", "token", "structure"])
def test_chunks_respect_budgets_and_offsets(strategy):
    doc = _long_doc()
    cfg = ChunkingConfig(
        strategy=strategy, chunk_size=400, chunk_overlap=60, max_tokens=120, token_overlap=16
    )
    chunks = chunk_document(doc, cfg)
    assert chunks
    for chunk in chunks:
        assert chunk.token_count <= 120
        assert chunk.page_start is not None
        # Offsets point into the full text at the chunk's first span.
        first_words = chunk.text[:20]
        assert first_words in doc.full_text[chunk.start : chunk.end + 1]
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_structure_chunks_never_cross_sections():
    chunks = chunk_document(
        _long_doc(), ChunkingConfig(strategy="structure", chunk_size=400, chunk_overlap=0)
    )
    assert len(chunks) > 3
    for chunk in chunks:
        section_number = chunk.heading_path[-1].split()[-1]
        mentioned = set(re.findall(r"of section (\d)", chunk.text))
        assert mentioned == {section_number}


def test_recursive_chunks_overlap():
    cfg = ChunkingConfig(strategy="recursive", chunk_size=300, chunk_overlap=120)
    chunks = chunk_document(_long_doc(), cfg)
    overlaps = sum(1 for a, b in zip(chunks, chunks[1:], strict=False) if b.start < a.end)
    assert overlaps > 0


def test_semantic_chunking_splits_on_topic_shift():
    blocks = [
        Block(text="Cats purr. Cats chase mice. Cats nap in the sun. Cats groom fur.", kind="paragraph"),
        Block(
            text="Bonds pay coupons. Bonds have maturity dates. Bonds carry credit risk. Bonds trade OTC.",
            kind="paragraph",
        ),
    ]
    doc = ExtractedDocument(blocks=blocks).finalize()

    def embed(texts: list[str]) -> np.ndarray:
        return np.array([[t.count("Cats"), t.count("Bonds"), 0.1] for t in texts], dtype=float)

    cfg = ChunkingConfig(strategy="semantic", chunk_size=2000, chunk_overlap=0, min_chunk_chars=10)
    chunks = chunk_document(doc, cfg, embed=embed)
    assert len(chunks) >= 2
    assert all(not ("Cats" in c.text and "Bonds" in c.text and c.text.count("Bonds") > 1) for c in chunks)


def test_invalid_chunking_config_rejected():
    with pytest.raises(ValueError):
        chunk_document(_long_doc(), ChunkingConfig(chunk_size=500, chunk_overlap=400))


def test_tiny_sibling_sections_merge_with_honest_location():
    blocks = [
        Block(text="Handbook", kind="heading", level=1),
        Block(text="Remote Work", kind="heading", level=2),
        Block(
            text="Employees may work remotely up to three days per week with manager approval. " * 2,
            kind="paragraph",
        ),
        Block(text="Equipment", kind="heading", level=2),
        Block(text="Laptops are refreshed every three years.", kind="paragraph"),
    ]
    doc = ExtractedDocument(blocks=blocks).finalize()
    [chunk] = chunk_document(doc, ChunkingConfig(strategy="structure", chunk_size=900, chunk_overlap=0))
    assert chunk.heading_path == ["Handbook"]
    assert chunk.section == "Remote Work / Equipment"
    assert "Equipment\nLaptops are refreshed" in chunk.text
