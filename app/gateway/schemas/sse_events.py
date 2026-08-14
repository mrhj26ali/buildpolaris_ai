"""Server-Sent Event payload shapes for the streaming copilot response
path (ARCH Â§4.5 â€” 'a full-response wait reads as "hung" compared to
token-by-token streaming'). buildpolaris_bff proxies this stream through
to the PWA rather than buffering it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SSEToken(BaseModel):
    event: Literal["token"] = "token"
    text: str


class SSECitation(BaseModel):
    event: Literal["citation"] = "citation"
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int


class SSEDisclosure(BaseModel):
    """FR-8.9 â€” sent once at the start of every stream so the client can
    render the AI-generated badge before the first token even arrives."""

    event: Literal["disclosure"] = "disclosure"
    ai_generated: bool = True


class SSEDone(BaseModel):
    event: Literal["done"] = "done"
    kind: str
    model_version: str
    trace_id: str


class SSEError(BaseModel):
    event: Literal["error"] = "error"
    message: str
