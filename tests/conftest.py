import os
import tempfile

# Tests never see the owner's data folder: point AirFare at an empty one before anything imports it.
os.environ["AIRFARE_DATA"] = tempfile.mkdtemp(prefix="airfare-test-data-")

import pytest  # noqa: E402

from airfare import links, money, notify, secrets  # noqa: E402


@pytest.fixture(autouse=True)
def no_windows_registration(monkeypatch):
    """Tests never register AirFare with the system (Windows' notification sender, airfare: links)."""
    monkeypatch.setattr(links, "_registered", False)
    monkeypatch.setattr(notify, "_app_id", notify.FALLBACK_APP_ID)


@pytest.fixture(autouse=True)
def keychain(monkeypatch):
    """Tests never touch the system keychain (macOS, Linux): API keys go to this dict instead."""
    store = {}
    monkeypatch.setattr(secrets, "_keychain_get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "_keychain_set", lambda name, value: store.__setitem__(name, value) or True)
    monkeypatch.setattr(secrets, "_cache", {})
    monkeypatch.setattr(secrets, "_last", {})
    return store


@pytest.fixture(autouse=True)
def no_exchange_rate_downloads(monkeypatch):
    """Exchange rates come from the test, never from the internet."""
    def offline(url):
        raise OSError("tests don't download exchange rates")
    monkeypatch.setattr(money, "_get", offline)
