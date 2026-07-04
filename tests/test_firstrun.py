"""Offscreen smoke test for the first-run wizard (SPEC §11.4, §18.7).

Requires QT_QPA_PLATFORM=offscreen (set in CI / pytest invocation) since it
instantiates real PySide6 widgets. Only construction and the setup_done
marker side-effect on close are checked here — no visual assertions.
"""

import sys

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWizard

import koekichi.paths as paths_module
from koekichi.config import DEFAULT_CONFIG
from koekichi.ui.firstrun import DonePage, FirstRunWizard, ModelDownloadPage


class _FakeEngineHost(QObject):
    """Stand-in for AppController, exposing only what the wizard needs."""

    sig_engine_ready = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def ensure_engine_loading(self) -> None:
        self.calls += 1


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _expected_page_count() -> int:
    # Welcome + ModelDownload + Done, plus Permissions on macOS only.
    return 4 if sys.platform == "darwin" else 3


def test_wizard_constructs_offscreen(qapp: QApplication) -> None:
    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)
    assert len(wizard.pageIds()) == _expected_page_count()


def test_wizard_is_non_modal(qapp: QApplication) -> None:
    from PySide6.QtCore import Qt

    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)
    assert wizard.windowModality() == Qt.NonModal


def test_done_page_shows_current_hotkey(qapp: QApplication) -> None:
    host = _FakeEngineHost()
    cfg = {"hotkey": {"type": "combo", "combo": "<ctrl>+<shift>+<space>"}}
    wizard = FirstRunWizard(cfg, host.ensure_engine_loading, host.sig_engine_ready)
    done_page = wizard.page(wizard.pageIds()[-1])
    assert isinstance(done_page, DonePage)


def test_model_download_page_start_calls_ensure_engine_loading(
    qapp: QApplication,
) -> None:
    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)
    download_page = wizard.page(wizard.pageIds()[1])
    assert isinstance(download_page, ModelDownloadPage)
    assert download_page.isComplete() is False

    download_page._start()
    assert host.calls == 1

    host.sig_engine_ready.emit(True, "")
    assert download_page.isComplete() is True


def test_model_download_page_skip_marks_complete(qapp: QApplication) -> None:
    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)
    download_page = wizard.page(wizard.pageIds()[1])

    download_page._skip()
    assert download_page.isComplete() is True


def test_model_download_page_failure_allows_retry(qapp: QApplication) -> None:
    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)
    download_page = wizard.page(wizard.pageIds()[1])

    download_page._start()
    host.sig_engine_ready.emit(False, "boom")
    assert download_page.isComplete() is False
    assert download_page.start_button.isEnabled() is True


def test_closing_wizard_writes_setup_marker(
    qapp: QApplication, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(paths_module, "get_config_dir", lambda: tmp_path)
    host = _FakeEngineHost()
    wizard = FirstRunWizard(DEFAULT_CONFIG, host.ensure_engine_loading, host.sig_engine_ready)

    assert paths_module.is_setup_done() is False
    wizard.done(QWizard.DialogCode.Rejected)
    assert paths_module.is_setup_done() is True
