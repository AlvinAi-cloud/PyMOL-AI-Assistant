"""Exercise update checks in the real frozen UI with an anonymous local server."""
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pymol.Qt import QtCore, QtWidgets
from pmg_qt import pymol_qt_gui
from pymol_ai_assistant import __version__
from pymol_ai_assistant.config import write_json
from pymol_ai_assistant import updates, updates_ui

OUT = Path(os.environ["PYMOL_UPDATES_QA"]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
checks, errors, requests, opened = {}, [], [], []
case_index = 0
heartbeat = False
next_version = ".".join(__version__.split(".")[:2] + [str(int(__version__.split(".")[2]) + 1)])
cases = ["newer", "current", "older", "missing", "error", "newer"]


class Releases(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        case = cases[case_index]
        requests.append(case)
        assert not self.headers.get("Authorization")
        time.sleep(0.4)
        if case == "error":
            self.send_error(500)
            return
        version = __version__ if case == "current" else "0.1.0" if case == "older" else next_version
        name = updates.installer_name(version)
        body = {"tag_name": "v" + version, "draft": False, "prerelease": False, "assets": []}
        if case != "missing":
            body["assets"] = [{"name": name, "state": "uploaded", "browser_download_url":
                               updates.REPOSITORY_URL + "/releases/download/v" + version + "/" + name}]
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


server = ThreadingHTTPServer(("127.0.0.1", 0), Releases)
threading.Thread(target=server.serve_forever, daemon=True).start()
original_fetch = updates_ui.fetch_latest
updates_ui.fetch_latest = lambda: updates.fetch_latest("http://127.0.0.1:%d/releases/latest" % server.server_port)


def finish(error=None):
    if (OUT / "result.json").exists():
        return
    if error:
        errors.append(error)
    updates_ui.fetch_latest = original_fetch
    write_json(OUT / "result.json", {"ok": not errors, "errors": errors, **checks, "requests": requests})
    server.shutdown()
    pymol_qt_gui.window.close()


def pulse():
    global heartbeat
    heartbeat = True


def start_case():
    global heartbeat
    try:
        heartbeat = False
        w = pymol_qt_gui.window
        w.check_update_action.trigger()
        d = w.update_dialog
        assert d.isVisible() and d.checking and not d.retry.isEnabled() and not d.download.isVisible()
        # Repeated menu clicks reuse the dialog and do not create duplicate requests.
        w.check_update_action.trigger()
        d.open_url = opened.append
        QtCore.QTimer.singleShot(50, pulse)
        QtCore.QTimer.singleShot(100, poll)
    except Exception:
        finish(traceback.format_exc())


def poll():
    global case_index
    try:
        d = pymol_qt_gui.window.update_dialog
        if d.checking:
            QtCore.QTimer.singleShot(100, poll)
            return
        assert heartbeat, "Update check blocked the UI event loop"
        assert d.retry.isEnabled()
        text = d.status.text()
        case = cases[case_index]
        assert len(requests) == case_index + 1, "Duplicate update request"
        if case == "newer":
            assert d.download.isVisible() and next_version in text
            assert d.download.width() >= d.download.fontMetrics().horizontalAdvance(d.download.text()) + 30
            d.download.click()
            assert opened[-1].endswith(updates.installer_name(next_version))
            d.releases.click()
            assert opened[-1] == updates.REPOSITORY_URL + "/releases/tag/v" + next_version
            d.grab().save(str(OUT / "update-available.png"))
            checks.update(platformMatchedDownload=True, browserDownloadAndReleaseActions=True)
        elif case in {"current", "older"}:
            assert "up to date" in text and not d.download.isVisible()
            checks["noDowngradeOrSameVersionDownload"] = True
        elif case == "missing":
            assert "No matching installer" in text and not d.download.isVisible()
            checks["missingInstallerFallback"] = True
        else:
            assert "Try again later" in text and not d.download.isVisible() and d.release is None
            d.releases.click()
            assert opened[-1] == updates.RELEASES_URL
            checks["failureAndRetry"] = True
        d.close()
        checks.update(nonblockingCheck=True, repeatedMenuClickReusesDialog=True)
        case_index += 1
        if case_index == len(cases):
            finish()
        else:
            QtCore.QTimer.singleShot(100, start_case)
    except Exception:
        finish(traceback.format_exc())


def ready():
    try:
        w = pymol_qt_gui.window
        if not hasattr(w, "check_update_action"):
            QtCore.QTimer.singleShot(200, ready)
            return
        menus = {a.text().replace("&", ""): a.menu() for a in w.menuBar().actions() if a.menu()}
        assert w.check_update_action in menus["AI Assistant"].actions()
        assert w.check_update_action in menus["Help"].actions()
        about = next(a for a in menus["AI Assistant"].actions() if a.text().startswith("About this"))
        captured = []
        original_about = QtWidgets.QMessageBox.about
        QtWidgets.QMessageBox.about = lambda owner, title, text: captured.append(text)
        try:
            about.trigger()
        finally:
            QtWidgets.QMessageBox.about = original_about
        assert len(captured) == 1 and __version__ in captured[0]
        for removed in ["AI connection components adapted", "Application integration:", "Live provider/account access"]:
            assert removed not in captured[0]
        checks.update(helpAndAssistantMenu=True, simplifiedAbout=True)
        start_case()
    except Exception:
        finish(traceback.format_exc())


QtCore.QTimer.singleShot(800, ready)
QtCore.QTimer.singleShot(60000, lambda: finish("Update GUI QA timed out"))
