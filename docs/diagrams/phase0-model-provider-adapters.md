# Phase 0 — Model Provider Adapters (Decision Log #6)

```mermaid
flowchart LR
    CONFIG["platform/config.py<br/>ModelProviderSettings<br/>provider_id + api_key + base_url"] --> FACTORY["get_model_provider()"]
    FACTORY --> ADAPTER["InstructorProvider<br/>(single adapter, all providers)"]
    ADAPTER --> INSTRUCTOR["instructor.from_provider(provider_id)"]

    INSTRUCTOR --> OLLAMA["Ollama (local)<br/>Mode.JSON<br/>ollama/qwen2.5:3b-instruct"]
    INSTRUCTOR --> GEMINI["Gemini (API)<br/>Mode.TOOLS<br/>google/gemini-2.5-flash"]
    INSTRUCTOR --> OTHER["Other providers<br/>(extendable via config)"]

    PROTOCOL["ModelProviderProtocol<br/>(hexagonal port)"] -.->|"contract"| ADAPTER
    CALLER["Agents / Gateway / Workers"] -->|"get_model_provider()"| FACTORY

    style CONFIG fill:#e8f5e9,stroke:#1b5e20
    style PROTOCOL fill:#fff3e0,stroke:#e65100
    style ADAPTER fill:#e1f5fe,stroke:#01579b
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Single adapter, not per-provider classes | `instructor.from_provider()` handles routing; less code, same contract |
| Ollama uses `Mode.JSON` | Prevents crashes when model outputs plain text (preserves original fix) |
| Other providers use `Mode.TOOLS` | More reliable structured extraction for API models |
| Provider selected via config string | Swapping providers is a `.env` change, not a code change (NFR-AI-5 prep) |
| Factory function as single seam | Callers never instantiate adapters directly — one place to change |