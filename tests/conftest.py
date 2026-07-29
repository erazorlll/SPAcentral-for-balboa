"""Protocol library tests: no Home Assistant, runs on every platform.

The integration tests live in `tests_ha/`, because Home Assistant's test
harness imports `fcntl` and its autouse fixtures would otherwise be applied to
these tests too.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "custom_components" / "balboa_spacentral"))


def _load(name: str) -> bytes:
    path = FIXTURES / f"{name}.bin"
    if not path.exists():
        pytest.skip(f"capture {path.name} not available")
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _fast_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the deliberate pacing delays so the suite stays quick.

    The real values exist to be gentle on a shared RS-485 bus; nothing in the
    logic depends on their magnitude.
    """
    from balboa import client as client_module

    monkeypatch.setattr(client_module, "REQUEST_INTERVAL", 0.001)
    monkeypatch.setattr(client_module, "TOGGLE_INTERVAL", 0.001)


@pytest.fixture(scope="session")
def capture_idle() -> bytes:
    """Two minutes of an undisturbed bus."""
    return _load("ew11_idle")


@pytest.fixture(scope="session")
def capture_probe() -> bytes:
    """One minute including the four configuration requests and their answers."""
    return _load("ew11_probe")


@pytest.fixture(scope="session")
def capture_panel() -> bytes:
    """Three minutes with the control panel being operated."""
    return _load("ew11_panel")


@pytest.fixture(scope="session")
def capture_spa2() -> bytes:
    """A second, physically separate controller of the same model.

    Guards against overfitting the parser to one device.
    """
    return _load("spa2_probe")
