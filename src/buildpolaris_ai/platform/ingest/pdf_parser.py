"""PDF parsing for construction documents (drawings, contracts, specs)."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class PDFParser:
    """Extracts text from PDF files with page-level metadata."""

    def parse_file(self, file_path: str) -> list[dict[str, Any]]:
        """Parse PDF and return list of page dicts."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            pages = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")

                # Also try to extract tables/structured content
                blocks = page.get_text("blocks")

                pages.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "blocks": blocks,
                    "has_images": len(page.get_images()) > 0,
                })

            doc.close()
            return pages

        except ImportError:
            logger.warning("PyMuPDF not available, trying pdfplumber")
            return self._parse_with_pdfplumber(file_path)
        except Exception as e:
            logger.error("PDF parsing failed", file=file_path, error=str(e))
            return []

    def _parse_with_pdfplumber(self, file_path: str) -> list[dict[str, Any]]:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    pages.append({
                        "page_number": i + 1,
                        "text": text,
                        "blocks": [],
                        "has_images": False,
                    })
            return pages
        except Exception as e:
            logger.error("pdfplumber parsing failed", error=str(e))
            return []

    def parse_bytes(self, content: bytes, filename: str = "") -> list[dict[str, Any]]:
        """Parse PDF from bytes."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            return self.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)
