"""Freeze native PyMOL and its private AI helper on the target operating system."""
import os
import platform
import sys
from pathlib import Path

from cx_Freeze import Executable, setup

ROOT = Path(__file__).resolve().parent
import pymol

PYMOL_DATA = Path(pymol.__file__).parent / "pymol_path"
HELPER = ROOT / ("ai/pymol-ai-assistant.exe" if os.name == "nt" else "ai/pymol-ai-assistant")
if not HELPER.is_file():
    raise SystemExit("Build the AI helper first, then place it in ai/pymol-ai-assistant.")

from PyQt5 import uic
import pmg_qt
forms = Path(pmg_qt.__file__).parent / "forms"
for form in forms.glob("*.ui"):
    with form.with_suffix(".py").open("w") as output:
        uic.compileUi(str(form), output)

build_base = os.environ.get("PYMOL_AI_BUILD_DIR", str(ROOT / "build"))
includes = ["pymol", "pymol2", "pmg_qt", "chempy", "pymol_ai_assistant", "numpy", "certifi", "xml", "gzip", "sqlite3", "PyQt5.uic"]
options = {
    "build": {"build_base": build_base},
    "build_exe": {
        "packages": includes,
        "includes": ["PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.QtOpenGL", "PyQt5.QtSvg", "PyQt5.sip"],
        "excludes": ["tkinter", "PyQt6", "PySide2", "PySide6", "PyQt5.QtSql", "PyQt5.QtMultimedia", "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtTextToSpeech", "PyQt5.QtSensors", "PyQt5.QtSerialPort", "matplotlib", "scipy", "pandas", "pytest", "pip", "setuptools", "test", "unittest"],
        "include_files": [] if sys.platform == "darwin" else [(str(PYMOL_DATA), "pymol-data"), (str(ROOT / "ai"), "ai"), (str(ROOT / "licenses"), "licenses"), (str(ROOT / "LICENSE"), "LICENSE"), (str(ROOT / "README.md"), "README.md")] + [(str(ROOT / "icons" / (name + ext)), "icons/" + name + ext) for name in ["PyMOL", "PDB", "CIF", "PSE", "MOL", "MOL2"] for ext in [".png", ".ico"]],
        "include_msvcr": os.name == "nt",
        "bin_excludes": ["pyqt5qmlplugin.dll"] if os.name == "nt" else [],
        "zip_include_packages": [],
        "zip_exclude_packages": ["*"],
        "optimize": 1,
    },
    "bdist_mac": {
        "bundle_name": "PyMOL AI-Assistant",
        "iconfile": str(ROOT / "icons/PyMOL.icns"),
        "custom_info_plist": str(ROOT / "Info.plist"),
        "include_resources": [(str(PYMOL_DATA), "pymol-data"), (str(ROOT / "ai"), "ai"), (str(ROOT / "licenses"), "licenses"), (str(ROOT / "LICENSE"), "LICENSE"), (str(ROOT / "README.md"), "README.md")] + [(str(ROOT / ("icons/" + name + ".icns")), name + ".icns") for name in ["PDB", "CIF", "PSE", "MOL", "MOL2"]],
        "codesign_identity": "-",
        "codesign_deep": True,
    },
}
if sys.platform != "darwin":
    options.pop("bdist_mac")

setup(name="pymol-ai-assistant", version="0.4.0", description="Unofficial standalone Open-Source PyMOL with an integrated AI assistant", options=options,
      executables=[Executable(str(ROOT / "launch.py"), base="gui", target_name="PyMOL AI-Assistant.exe" if os.name == "nt" else "PyMOL AI-Assistant", icon=str(ROOT / "icons/PyMOL.ico") if os.name == "nt" else None, shortcut_name="PyMOL AI-Assistant", shortcut_dir="ProgramMenuFolder")])
