"""Cross-platform desktop behavior without changing actual system defaults."""
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from pymol_ai_assistant import config, associations


class DesktopTests(unittest.TestCase):
    def test_frozen_resources_are_beside_windows_linux_exe_and_inside_mac_bundle(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(sys, "executable", "/tmp/Test.app/Contents/MacOS/Test"):
                self.assertEqual(config.resources_dir(), Path("/tmp/Test.app/Contents/Resources").resolve())
            for platform in ["linux", "win32"]:
                with mock.patch.object(sys, "platform", platform), mock.patch.object(sys, "executable", "/tmp/Standalone App/App"):
                    self.assertEqual(config.resources_dir(), Path("/tmp/Standalone App").resolve())

    def test_windows_registers_bundled_engine_dependencies_before_import(self):
        from pymol_ai_assistant import app
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            qt_bin = root / "lib/PyQt5/Qt5/bin"
            qt_bin.mkdir(parents=True)
            handle = object()
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "win32"), mock.patch.object(sys, "executable", str(root / "Application.exe")), mock.patch.object(app.os, "add_dll_directory", return_value=handle, create=True) as register, mock.patch.object(app, "_DLL_DIRECTORY_HANDLES", []), mock.patch.dict(app.os.environ, {}, clear=False):
                app.prepare_environment()
                registered = [call.args[0] for call in register.call_args_list]
                self.assertIn(str(qt_bin), registered)
                self.assertIn(str(root), registered)
                self.assertIn(handle, app._DLL_DIRECTORY_HANDLES)
                self.assertIn(str(qt_bin), app.os.environ["PATH"])

    def test_linux_only_sets_checked_types_and_confirms_defaults(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return types.SimpleNamespace(stdout="org.pymol-ai-assistant.desktop\n")
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "linux"), mock.patch.object(associations.subprocess, "run", side_effect=run):
            changed, errors = associations.set_preferred_types([2])
        self.assertEqual(changed, ["pse"])
        self.assertEqual(errors, [])
        self.assertEqual(calls, [["xdg-mime", "default", "org.pymol-ai-assistant.desktop", "application/x-pymol-session"], ["xdg-mime", "query", "default", "application/x-pymol-session"]])

    def test_failed_linux_change_is_reported_without_claiming_success(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "linux"), mock.patch.object(associations.subprocess, "run", side_effect=OSError("unavailable")):
            changed, errors = associations.set_preferred_types([0])
        self.assertEqual(changed, [])
        self.assertIn(".pdb", errors[0])

    def test_windows_registers_open_command_icons_and_requests_user_confirmation(self):
        writes = []
        class Key:
            def __init__(self, path): self.path = path
            def __enter__(self): return self
            def __exit__(self, *_): pass
        registry = types.SimpleNamespace(HKEY_CURRENT_USER=1, REG_SZ=1, REG_NONE=0,
            CreateKey=lambda _root, key: Key(key),
            SetValueEx=lambda key, name, _reserved, kind, value: writes.append((key.path, name, kind, value)))
        shell = mock.Mock()
        with mock.patch.dict(sys.modules, winreg=registry), mock.patch.object(sys, "platform", "win32"), mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", "/tmp/Standalone App/PyMOL AI-Assistant.exe"), mock.patch.object(associations.ctypes, "windll", types.SimpleNamespace(shell32=shell), create=True), mock.patch.object(associations.os, "startfile", create=True) as settings:
            changed, errors = associations.set_preferred_types([2])
        self.assertEqual(changed, ["pse"])
        self.assertEqual(errors, [])
        settings.assert_called_once_with("ms-settings:defaultapps")
        command = next(value for key, name, kind, value in writes if key.endswith("open\\command"))
        self.assertEqual(command, '\"/tmp/Standalone App/PyMOL AI-Assistant.exe\" \"%1\"')
        self.assertTrue(any(key.endswith("DefaultIcon") and "PSE.ico" in value for key, _, _, value in writes))
        self.assertFalse(any("UserChoice" in key for key, _, _, _ in writes))
        self.assertFalse(any(".pdb" in key for key, _, _, _ in writes))
