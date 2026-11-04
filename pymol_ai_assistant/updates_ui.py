"""Nonblocking, on-demand update checks for the desktop app."""
import threading

from pymol.Qt import QtCore, QtGui, QtWidgets

from . import APP_NAME, __version__
from .updates import RELEASES_URL, fetch_latest


class UpdateDialog(QtWidgets.QDialog):
    completed = QtCore.Signal(object, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Check for Update — " + APP_NAME)
        self.setObjectName("check_for_update_dialog")
        self.setMinimumWidth(440)
        self.release = None
        self.checking = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(APP_NAME + "\nInstalled version: " + __version__))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(65)
        layout.addWidget(self.status)
        note = QtWidgets.QLabel("Checks public GitHub releases only when requested. Downloads open in your browser; run the installer to update the app.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QtWidgets.QHBoxLayout()
        self.download = QtWidgets.QPushButton("Download update")
        self.download.setVisible(False)
        self.download.clicked.connect(self.open_download)
        row.addWidget(self.download)
        self.releases = QtWidgets.QPushButton("View releases")
        self.releases.clicked.connect(self.open_releases)
        row.addWidget(self.releases)
        self.retry = QtWidgets.QPushButton("Check again")
        self.retry.clicked.connect(self.check)
        row.addWidget(self.retry)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self.completed.connect(self.finished_check)

    def check(self):
        if self.checking:
            return
        self.checking = True
        self.release = None
        self.download.setVisible(False)
        self.retry.setEnabled(False)
        self.status.setText("Checking GitHub for the latest stable release…")

        def run():
            try:
                result, error = fetch_latest(), ""
            except Exception as exception:
                from .updates import UpdateError
                result = None
                error = str(exception) if isinstance(exception, UpdateError) else "Could not check for updates. Try again later or view the releases page."
            try:
                self.completed.emit(result, error)
            except RuntimeError:
                # The main window may have been closed during the bounded request.
                pass

        threading.Thread(target=run, daemon=True, name="pymol-update-check").start()

    def finished_check(self, release, error):
        self.checking = False
        self.retry.setEnabled(True)
        self.release = release
        if error:
            self.status.setText(error)
        elif release.newer:
            text = "Version " + release.version + " is available."
            if release.download_url:
                text += "\nInstaller: " + release.installer
                self.download.setText("Download " + release.version)
                self.download.setMinimumWidth(self.download.fontMetrics().horizontalAdvance(self.download.text()) + 40)
                self.download.setVisible(True)
            else:
                text += "\nNo matching installer is available yet. View the release page for downloads and details."
            self.status.setText(text)
        else:
            self.status.setText("You’re up to date.\nInstalled: " + __version__ + " · Latest stable release: " + release.version)

    def open_url(self, url):
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)):
            self.status.setText("Could not open your browser. Visit " + url)

    def open_download(self):
        if self.release and self.release.newer and self.release.download_url:
            self.open_url(self.release.download_url)

    def open_releases(self):
        self.open_url(self.release.release_url if self.release else RELEASES_URL)


def show_updates(window):
    dialog = getattr(window, "update_dialog", None)
    if dialog is None:
        dialog = window.update_dialog = UpdateDialog(window)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.check()


def install_update_action(window, assistant_menu):
    action = QtWidgets.QAction("Check for Update…", window)
    action.setObjectName("check_for_update_action")
    action.setToolTip("Check GitHub for a newer version and download the installer for this computer.")
    action.triggered.connect(lambda: show_updates(window))
    assistant_menu.addAction(action)
    # Keep the same action available from PyMOL's conventional Help menu.
    for item in window.menuBar().actions():
        if item.text().replace("&", "").strip() == "Help" and item.menu():
            item.menu().addSeparator()
            item.menu().addAction(action)
            break
    window.check_update_action = action
