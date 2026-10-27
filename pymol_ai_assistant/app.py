"""Launch official PyMOL with an independent assistant, without core patches."""
import json
import os
import sys
import subprocess
import time
import traceback
from pathlib import Path

from . import APP_NAME, __version__
from .config import profile_dir, resources_dir, write_json


_DLL_DIRECTORY_HANDLES = []
_DIAGNOSTIC_STREAM = None


def startup_note(message):
    if _DIAGNOSTIC_STREAM:
        _DIAGNOSTIC_STREAM.write(message + "\n")
        _DIAGNOSTIC_STREAM.flush()


def prepare_environment():
    if getattr(sys, "frozen", False):
        resources = resources_dir()
        if sys.platform == "win32":
            # cx_Freeze's Qt hook collects shared native libraries here.
            # PyMOL imports its engine before importing Qt, so register these
            # directories first and retain the loader handles for the process.
            candidates = [resources, resources / "lib", resources / "lib/PyQt5/Qt5/bin",
                          resources / "lib/PyQt5/bin", resources / "lib/PyQt5"]
            directories = [path for path in candidates if path.is_dir()]
            for directory in directories:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
            os.environ["PATH"] = os.pathsep.join([str(path) for path in directories] + [os.environ.get("PATH", "")])
        data = resources / "pymol-data"
        os.environ["PYMOL_PATH"] = str(data)
        os.environ["PYMOL_DATA"] = str(data / "data")
        os.environ["PYMOL_SCRIPTS"] = str(data / "scripts")
        plugins = resources / "lib/PyQt5/Qt5/plugins"
        if plugins.is_dir():
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    # The frozen package carries its own trusted CA bundle.
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def run_gui_self_test(window, directory):
    """Application-owned integration test: no paid requests or external UI control."""
    from pymol.Qt import QtCore, QtWidgets
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def ready():
        if not window.cmd.ready() or not window.pymolwidget.isValid():
            if time.monotonic() - started < 30:
                QtCore.QTimer.singleShot(250, ready)
                return
            write_json(output / "result.json", {"ok": False, "error": "OpenGL initialization timed out."})
            QtWidgets.QApplication.instance().quit()
            return
        dock = window.ai_assistant
        try:
            dock.example()
            initial = window.cmd.count_atoms("example_1hpv")
            assert initial > 100
            actions = [
                {"operation": "color", "selection": "example_1hpv", "color": "cyan"},
                {"operation": "show", "selection": "example_1hpv and organic", "representation": "sticks"},
                {"operation": "zoom", "selection": "example_1hpv", "buffer": 2.0},
            ]
            dock.tools.apply(actions)
            assert dock.tools.undo()
            assert window.cmd.count_atoms("example_1hpv") == initial
            window.cmd.save(str(output / "session.pse"))
            window.cmd.png(str(output / "molecule.png"), width=1000, height=750, ray=1, quiet=1)
            assert (output / "molecule.png").stat().st_size > 5000
            dock.accounts_dialog = __import__("pymol_ai_assistant.ui", fromlist=["AccountsDialog"]).AccountsDialog(dock, refresh=False)
            dock.accounts_dialog.grab().save(str(output / "accounts.png"))
            from .associations import show_file_types
            def capture_setup():
                dialog = QtWidgets.QApplication.activeModalWidget()
                if dialog:
                    dialog.grab().save(str(output / "file-types.png"))
                    dialog.reject()
            QtCore.QTimer.singleShot(300, capture_setup)
            show_file_types(window, first_launch=False)
            def helper_result(value, error):
                try:
                    assert not error, error
                    assert "chatgpt" in value
                    QtWidgets.QApplication.processEvents()
                    window.grab().save(str(output / "layout-debug.png"))
                    assert dock.chat.geometry().bottom() < dock.input.geometry().top(), "Assistant chat/input layout overlaps: %s / %s" % (dock.chat.geometry(), dock.input.geometry())
                    assert not hasattr(dock, "include_sequence"), "Obsolete sequence checkbox is present"
                    render_widget = QtWidgets.QWidget()
                    render_form = window.render_dialog(render_widget)
                    assert render_widget.findChild(QtWidgets.QSpinBox, "input_width") is not None, "Draw/Ray form is missing"
                    render_widget.grab().save(str(output / "draw-ray.png"))
                    render_widget.close()
                    if getattr(sys, "frozen", False) and sys.platform == "darwin":
                        import plistlib
                        info = plistlib.loads((Path(sys.executable).parents[1] / "Info.plist").read_bytes())
                        assert (resources_dir() / info["CFBundleIconFile"]).is_file(), "App icon declaration points to a missing file"
                    window.grab().save(str(output / "window.png"))
                    write_json(output / "result.json", {
                        "ok": True, "package": APP_NAME, "version": __version__,
                        "pymol": list(window.cmd.get_version()), "atoms": initial,
                        "renderer": list(window.cmd.get_renderer()), "helperStatus": value,
                        "guiVisible": window.isVisible(), "assistantVisible": dock.isVisible(),
                        "executable": sys.executable, "frozen": bool(getattr(sys, "frozen", False)),
                        "python": sys.version,
                        "assistantWidth": dock.width(),
                        "automaticControl": not hasattr(dock, "apply_button"),
                        "appIconValid": not QtWidgets.QApplication.instance().windowIcon().isNull(),
                        "availableCommandCount": len(dock.tools.native.names),
                    })
                except Exception:
                    write_json(output / "result.json", {"ok": False, "error": traceback.format_exc()})
                QtWidgets.QApplication.instance().quit()
            dock.bridge.request("status", helper_result)
        except Exception:
            write_json(output / "result.json", {"ok": False, "error": traceback.format_exc()})
            QtWidgets.QApplication.instance().quit()
    QtCore.QTimer.singleShot(700, ready)


def main():
    global _DIAGNOSTIC_STREAM
    if os.environ.get("PYMOL_AI_DIAGNOSTICS"):
        import faulthandler
        _DIAGNOSTIC_STREAM = (profile_dir() / "startup-trace.log").open("a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=_DIAGNOSTIC_STREAM, all_threads=True)
        faulthandler.dump_traceback_later(20, repeat=True, file=_DIAGNOSTIC_STREAM)
    startup_note("Entered application main")
    prepare_environment()
    startup_note("Prepared bundled runtime paths")
    arguments = list(sys.argv[1:])
    test_directory = None
    for argument in list(arguments):
        if argument.startswith("--self-test="):
            test_directory = argument.partition("=")[2]
            arguments.remove(argument)
    # Finder may pass a legacy process-serial-number argument.
    arguments = [a for a in arguments if not a.startswith("-psn_")]
    profile = profile_dir()
    log = profile / "launch.log"
    if log.is_file() and log.stat().st_size > 2_000_000:
        os.replace(log, profile / "launch-previous.log")
    if getattr(sys, "frozen", False):
        sys.stdout = sys.stderr = open(log, "a", buffering=1, encoding="utf-8")
    startup_note("Importing PyMOL engine")
    import pymol
    startup_note("Importing Qt")
    from pymol.Qt import QtCore
    startup_note("Importing PyMOL GUI")
    from pmg_qt import pymol_qt_gui
    from .ui import install

    upstream_window = pymol_qt_gui.PyMOLQtGUI

    class AssistantWindow(upstream_window):
        def render_dialog(self, widget=None):
            form = super().render_dialog(widget)
            if widget is not None:
                # WidgetMenu installs the return value as a QWidget. Compiled
                # Designer forms are controllers; retain it on its widget.
                widget._pymol_render_form = form
                return widget
            return form

        def new_window(self, extra_argv=()):
            # Upstream's Python-module launcher is not valid for a frozen executable.
            arguments = [sys.executable]
            if not getattr(sys, "frozen", False):
                arguments.append(str(Path(__file__).resolve().parents[1] / "launch.py"))
            return subprocess.Popen(arguments + list(extra_argv))

        def __init__(self):
            startup_note("Constructing PyMOL window")
            super().__init__()
            startup_note("Constructed PyMOL window")
            def complete():
                startup_note("Installing assistant panel")
                install(self)
                startup_note("Installed assistant panel")
                if test_directory:
                    run_gui_self_test(self, test_directory)
                elif getattr(sys, "frozen", False) and not os.environ.get("PYMOL_AI_SKIP_SETUP"):
                    from .associations import needs_setup, show_file_types
                    if needs_setup():
                        QtCore.QTimer.singleShot(600, lambda: show_file_types(self, first_launch=True))
            QtCore.QTimer.singleShot(0, complete)

    pymol_qt_gui.PyMOLQtGUI = AssistantWindow
    # -k keeps this independent app from executing another installation's startup scripts/plugins.
    startup_note("Launching PyMOL GUI loop")
    pymol.launch([APP_NAME, "-k"] + arguments)
