"""Test setup."""

import itertools
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Home Assistant loads the integration as `custom_components.evsemaster`, so the repo root
# has to be importable.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def auto_enable_sockets(socket_enabled):
    """These tests drive fake chargers over real UDP on loopback."""
    yield


_TEST_PORTS = itertools.count(22000)


@pytest.fixture(autouse=True)
def loopback_listener(monkeypatch):
    """Keep the shared listener on loopback and off the production port.

    Binding 0.0.0.0:28376 makes the suite pick up broadcasts from real chargers on the network,
    which then race the fakes and win. Each test gets a port of its own.
    """
    from evsemaster import listener as listener_module
    from evsemaster import testing as testing_module

    port = next(_TEST_PORTS)
    real_listener = listener_module.EvseListener

    def build(**kwargs):
        return real_listener(listen_port=port, bind_addr="127.0.0.1", **kwargs)

    monkeypatch.setattr("custom_components.evsemaster.hub.EvseListener", build)
    monkeypatch.setattr(testing_module, "LISTEN_PORT", port)
    yield
