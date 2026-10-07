import importlib.metadata

from core import utils


def _install(monkeypatch, version, checkout=False):
    def metadata_version(name):
        if version is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return version

    monkeypatch.setattr(utils.importlib.metadata, "version", metadata_version)
    monkeypatch.setattr(utils, "_is_source_checkout", lambda: checkout)


def test_installed_package_reports_its_release_version(monkeypatch):
    _install(monkeypatch, "0.3.1.0")
    assert utils.installed_version() == "0.3.1.0"
    assert utils.get_current_version() == "0.3.1.0"


def test_checkout_and_uninstalled_stay_dev(monkeypatch):
    _install(monkeypatch, "0.2.0.0", checkout=True)  # the version of pyproject.toml is only a placeholder
    assert utils.get_current_version() == "Dev"

    _install(monkeypatch, None)
    assert utils.get_current_version() == "Dev"


def test_this_checkout_is_detected():
    assert utils._is_source_checkout()
