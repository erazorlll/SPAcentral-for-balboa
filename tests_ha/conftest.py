"""Integration tests: need Home Assistant, so Linux or macOS only.

Kept apart from `tests/` on purpose. `pytest-homeassistant-custom-component`
installs autouse fixtures that assume a running Home Assistant event loop; let
loose on the protocol tests they fail every one of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _allow_custom_integrations(enable_custom_integrations: None) -> None:
    """A custom integration is only loadable in tests with this enabled."""
