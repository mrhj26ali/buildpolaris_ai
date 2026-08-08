"""
Shared pytest configuration and fixtures for buildpolaris_ai.

Responsibilities:
- Make src/ importable regardless of where pytest is invoked from.
- Auto-apply `unit` / `integration` / `security` markers based on the test's
  directory, so `pytest -m unit` etc. work without decorating every test
  (Implementation Plan §3.4).
- Provide an isolated containerized Postgres+AGE+pgvector instance for
  integration tests via testcontainers.
"""
import sys
from pathlib import Path

import pytest

# --- Make src/ importable -------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# --- Auto-mark tests by directory ----------------------------------------
def pytest_collection_modifyitems(config, items):
    """Apply unit/integration/security markers based on test file location.

    This lets `pytest -m unit` (and friends) select tests by directory without
    requiring a decorator on every test function.
    """
    for item in items:
        # Normalize separators so this works on Windows and Unix alike
        path = str(item.fspath).replace("\\", "/").lower()
        if "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/security/" in path:
            item.add_marker(pytest.mark.security)


# --- Containerized DB fixture (testcontainers) ---------------------------
@pytest.fixture(scope="session")
def db_container():
    """Spin up an isolated Postgres+AGE+pgvector container for integration tests.

    Uses the project's custom image (buildpolaris-ai-polaris-db), which has
    Apache AGE + pgvector compiled in and init-db.sh baked into the image
    (see Dockerfile.db). Build it first with:

        docker compose build polaris-db

    Yields a dict of asyncpg connection kwargs.

    NOTE: The existing integration tests read their connection settings from
    platform/config.py defaults (localhost:5432) and run against the long-lived
    docker-compose database. This fixture is the isolated alternative for new
    tests that should not depend on shared local state.
    """
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        pytest.skip("testcontainers not installed; skipping containerized DB fixture")

    image = "buildpolaris-ai-polaris-db:latest"
    container = DockerContainer(image)
    container.with_env("POSTGRES_USER", "polaris_ai")
    container.with_env("POSTGRES_PASSWORD", "polaris_ai_dev_password")
    container.with_env("POSTGRES_DB", "polaris_knowledge")
    container.with_exposed_ports(5432)

    try:
        container.start()
        # Postgres logs this after init scripts (AGE extension + graph) complete
        wait_for_logs(container, "ready to accept connections", timeout=120)
    except Exception as exc:
        pytest.skip(
            f"Could not start DB container ({exc}). "
            f"Ensure the image is built (`docker compose build polaris-db`) "
            f"and Docker is running."
        )

    conn_kwargs = {
        "host": container.get_container_host_ip(),
        "port": int(container.get_exposed_port(5432)),
        "user": "polaris_ai",
        "password": "polaris_ai_dev_password",
        "database": "polaris_knowledge",
    }

    yield conn_kwargs

    container.stop()