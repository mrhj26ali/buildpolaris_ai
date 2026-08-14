"""Document chunking with construction-domain awareness."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class Chunk:
    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)
    source_docname: str = ""
    source_doctype: str = ""


class ConstructionChunker:
    """Chunker optimized for construction documents.
    
    Strategy:
    1. Split on natural boundaries (paragraphs, sections)
    2. Respect construction-specific patterns (clause numbers, spec sections)
    3. Maintain overlap for context continuity
    4. Preserve metadata (section headers, clause IDs)
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Construction-specific section patterns
        self._section_pattern = re.compile(
            r"^(?:SECTION|SECTION\s+\d+|ARTICLE\s+\d+|CLAUSE\s+\d+|"
            r"\d+\.\d+(?:\.\d+)?\s|[A-Z]\.\d+\.\d+\s)",
            re.MULTILINE | re.IGNORECASE,
        )
        self._paragraph_split = re.compile(r"\n\s*\n")

    def chunk_text(
        self,
        text: str,
        docname: str = "",
        doctype: str = "",
        metadata: dict | None = None,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        base_meta = metadata or {}
        chunks: list[Chunk] = []

        # First split by construction sections
        sections = self._split_by_sections(text)

        chunk_index = 0
        for section_text, section_header in sections:
            if len(section_text) <= self.chunk_size:
                chunks.append(Chunk(
                    text=section_text.strip(),
                    chunk_index=chunk_index,
                    metadata={**base_meta, "section_header": section_header},
                    source_docname=docname,
                    source_doctype=doctype,
                ))
                chunk_index += 1
            else:
                # Sub-chunk long sections with overlap
                sub_chunks = self._sliding_window_chunk(section_text, section_header)
                for sc in sub_chunks:
                    chunks.append(Chunk(
                        text=sc.strip(),
                        chunk_index=chunk_index,
                        metadata={**base_meta, "section_header": section_header},
                        source_docname=docname,
                        source_doctype=doctype,
                    ))
                    chunk_index += 1

        return chunks

    def _split_by_sections(self, text: str) -> list[tuple[str, str]]:
        """Split text by construction section headers."""
        parts = self._section_pattern.split(text)
        headers = self._section_pattern.findall(text)

        sections = []
        for i, part in enumerate(parts):
            if part.strip():
                header = headers[i - 1] if i > 0 and i - 1 < len(headers) else ""
                sections.append((part, header.strip()))

        if not sections:
            sections = [(text, "")]

        return sections

    def _sliding_window_chunk(self, text: str, section_header: str) -> list[str]:
        """Split long text with overlap using paragraph boundaries."""
        paragraphs = self._paragraph_split.split(text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 1 <= self.chunk_size:
                current_chunk = f"{current_chunk}\n{para}" if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If paragraph itself is too long, force-split by sentences
                if len(para) > self.chunk_size:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    current_chunk = ""
                    for sent in sentences:
                        if len(current_chunk) + len(sent) + 1 <= self.chunk_size:
                            current_chunk = f"{current_chunk} {sent}" if current_chunk else sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sent
                else:
                    # Overlap: keep last N chars
                    overlap_text = current_chunk[-self.chunk_overlap:] if current_chunk else ""
                    current_chunk = f"{overlap_text}\n{para}"

        if current_chunk.strip():
            chunks.append(current_chunk)

        return chunks

    def chunk_pdf_text(
        self,
        pages: list[dict],
        docname: str = "",
        doctype: str = "",
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Chunk text extracted from PDF pages, preserving page references."""
        all_chunks = []
        base_meta = metadata or {}

        for page_data in pages:
            page_num = page_data.get("page_number", 0)
            page_text = page_data.get("text", "")
            if not page_text.strip():
                continue

            page_meta = {**base_meta, "page_number": page_num}
            page_chunks = self.chunk_text(
                page_text, docname=docname, doctype=doctype, metadata=page_meta
            )
            all_chunks.extend(page_chunks)

        return all_chunks
