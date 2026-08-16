"""POST /ingest request/response -- UC-8.4 steps 5-9.

buildpolaris_bff/ai_copilot/services/ingestion_trigger_service.py's own
docstring documents a deliberate design choice: rather than standing up a
signed-URL callback subsystem, the BFF reads the File's content itself
and sends it inline as base64 in the same authenticated service-to-
service request ("one fewer moving part for a single internal
consumer"). `content_b64`/`file_name` below are exactly that payload;
`signed_download_url` is kept optional for a future ingestion path that
wants a real fetch-by-reference instead, but nothing sends it today.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IngestRequest(BaseModel):
    company: str
    project: str
    source_doctype: Literal["Commitment", "Submittal Package", "RFI"]
    source_name: str
    file_id: str
    file_name: str | None = None
    content_hash: str
    # Exactly one of these two must be present.
    signed_download_url: str | None = None
    content_b64: str | None = None
    model_version_hint: str | None = None

    @model_validator(mode="after")
    def _require_one_content_source(self) -> "IngestRequest":
        if not self.signed_download_url and not self.content_b64:
            raise ValueError("one of signed_download_url or content_b64 is required")
        return self


class IngestResult(BaseModel):
    # Title-cased to match buildpolaris_bff/ai_copilot/services/
    # ingestion_trigger_service.py's check (`result.get("status") ==
    # "Indexed"`) and the AI Document Index DocType's own Select field
    # options (Queued/Processing/Indexed/Failed).
    status: Literal["Indexed", "Failed"]
    chunk_count: int = 0
    model_version: str | None = None
    failure_reason: str | None = None  # e.g. 'no_text_layer', 'scope_mismatch'
    status_detail: str | None = None
