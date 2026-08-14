"""Dev/CI helper â€” validates every agents/<name>/manifest.yaml is
well-formed and every declared target_doctype has a payload_verifier.py
entry, WITHOUT starting the full FastAPI app. Run this in CI before
deploy so a malformed manifest fails fast rather than surfacing as a 500
on the first real copilot turn.

Usage: python scripts/register_agents.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator.agent_registry import get_agent_registry  # noqa: E402
from app.platform.governance.payload_verifier import ALLOWED_TARGETS  # noqa: E402


def main() -> int:
    registry = get_agent_registry()
    manifests = registry.all_manifests()

    if not manifests:
        print("ERROR: no agents were discovered under app/agents/")
        return 1

    errors = []
    for manifest in manifests:
        allowed = ALLOWED_TARGETS.get(manifest.agent_type)
        if allowed is None:
            errors.append(
                f"{manifest.agent_type}: no entry in governance/payload_verifier.ALLOWED_TARGETS"
            )
        elif manifest.target_doctype not in allowed:
            errors.append(
                f"{manifest.agent_type}: manifest target_doctype '{manifest.target_doctype}' "
                f"not in ALLOWED_TARGETS {allowed}"
            )

        print(f"OK  {manifest.agent_type:30s} -> {manifest.target_doctype}")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{len(manifests)} agent(s) registered cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
