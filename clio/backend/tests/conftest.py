import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("CLIO_CONTACT_EMAIL", "test@example.com")


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status():
    """sse_starlette's AppStatus.should_exit_event is a module-level singleton
    bound to whichever event loop first awaited it; each TestClient request in
    this suite may spin up a fresh loop, so reset it between tests to avoid
    'bound to a different event loop' errors on unrelated tests."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield
