"""Test setup: make the bundled library importable and expose the fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "custom_components" / "balboa_spacentral"))
sys.path.insert(0, str(REPO_ROOT))

#: Home Assistant's test harness imports `fcntl`, so it cannot run on Windows --
#: the same reason HA core is developed on Linux and macOS only. The protocol
#: library has no such dependency and is tested everywhere; the integration
#: tests are collected on Linux, which is what CI runs.
try:  # pragma: no cover - platform dependent
    import fcntl  # noqa: F401

    HA_TESTS_RUNNABLE = True
except ImportError:  # pragma: no cover - platform dependent
    HA_TESTS_RUNNABLE = False

collect_ignore_glob = (
    []
    if HA_TESTS_RUNNABLE
    else ["test_identity.py", "test_config_flow.py", "test_integration.py"]
)


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
