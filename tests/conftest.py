"""Test setup.

The integration lives in the repository root (HACS `content_in_root`), but Home Assistant can
only load it as `custom_components.evsemaster`, so build that layout in a temp dir and put it on
the path. This is what lets `pytest` run straight from the repo root.
"""

import itertools
import pathlib
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _install_custom_components_path() -> None:
    root = pathlib.Path(tempfile.gettempdir()) / "evsemaster-custom-components"
    package = root / "custom_components"
    package.mkdir(parents=True, exist_ok=True)
    link = package / "evsemaster"
    if link.is_symlink() and link.readlink() != REPO:
        link.unlink()
    if not link.is_symlink():
        link.symlink_to(REPO, target_is_directory=True)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _dedupe_library() -> None:
    """Make the loader's copy of `evsemaster` the same module objects as the tests'.

    The documented dev workflow symlinks the library to ./evsemaster inside this repo, and
    `evse_loader` then imports it a second time as `custom_components.evsemaster.evsemaster`.
    Two copies means two sets of classes, so the coordinator's `isinstance(payload, EvseStatus)`
    checks fail against the tests' top-level copy and nothing is ever pushed - entities just
    stay `unknown`, for a reason that looks nothing like the cause.
    """
    import evsemaster
    import evsemaster.data_types  # noqa: F401
    import evsemaster.device  # noqa: F401
    import evsemaster.listener  # noqa: F401
    import evsemaster.testing  # noqa: F401

    sys.modules["custom_components.evsemaster.evsemaster"] = evsemaster


_install_custom_components_path()
_dedupe_library()

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
