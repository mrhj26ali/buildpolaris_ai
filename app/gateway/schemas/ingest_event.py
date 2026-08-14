"""POST /ingest request/response â€” UC-8.4 steps 5-9.

The sidecar never fetches a file on its own initiative; every field here
is what a BFF background job passes after its own eligibility + hash
check (ERD Â§4.1).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    company: str
    project: str
    source_doctype: Literal["Commitment", "Submittal Package", "RFI"]
    source_name: str
    file_id: str
    content_hash: str
    # Permission-checked, time-limited signed download reference
    # (NFR-SEC.7) â€” never a raw internal file path.
    signed_download_url: str
    model_version_hint: str | None = None


class IngestResult(BaseModel):
    status: Literal["indexed", "failed"]
    chunk_count: int = 0
    model_version: str | None = None
    failure_reason: str | None = None  # e.g. 'no_text_layer', 'scope_mismatch'
