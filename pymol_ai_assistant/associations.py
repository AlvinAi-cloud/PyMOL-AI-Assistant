"""Opt-in document associations for macOS, Windows and Linux desktops."""
import os
import subprocess
import ctypes
import json
import sys
from pathlib import Path

from . import APP_NAME
from .config import profile_dir, write_json

BUNDLE_ID = "org.pymol-ai-assistant.desktop"
FILE_TYPES = [
    {"label": "PDB structures", "extensions": ["pdb"], "uti": "org.wwpdb.pdb", "icon": "PDB"},
    {"label": "mmCIF structures", "extensions": ["cif", "mmcif"], "uti": "org.pymol-ai-assistant.mmcif", "icon": "CIF"},
    {"label": "PyMOL sessions", "extensions": ["pse"], "uti": "org.pymol-ai-assistant.session", "icon": "PSE"},
    {"label": "Mol / SDF structures", "extensions": ["mol", "sdf"], "uti": "org.pymol-ai-assistant.mol-sdf", "icon": "MOL"},
    {"label": "Mol2 structures", "extensions": ["mol2"], "uti": "org.pymol-ai-assistant.mol2", "icon": "MOL2"},
]


class LaunchServices:
    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("File type setup in this build supports macOS.")
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.cs = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
        self.cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        self.cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
        self.cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
        self.cs.UTTypeCreatePreferredIdentifierForTag.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.cs.UTTypeCreatePreferredIdentifierForTag.restype = ctypes.c_void_p
        self.cs.LSCopyDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.cs.LSCopyDefaultRoleHandlerForContentType.restype = ctypes.c_void_p
        self.cs.LSSetDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self.cs.LSSetDefaultRoleHandlerForContentType.restype = ctypes.c_int32
        self.cs.LSRegisterURL.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.cs.LSRegisterURL.restype = ctypes.c_int32

    def string(self, text):
        value = self.cf.CFStringCreateWithCString(None, text.encode("utf-8"), 0x08000100)
        if not value:
            raise RuntimeError("Could not create a macOS file type identifier.")
        return value

    def text(self, value):
        buffer = ctypes.create_string_buffer(4096)
        if value and self.cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100):
            return buffer.value.decode("utf-8")
        return ""

    def preferred_uti(self, extension):
        tag, suffix = self.string("public.filename-extension"), self.string(extension)
        value = None
        try:
            value = self.cs.UTTypeCreatePreferredIdentifierForTag(tag, suffix, None)
            return self.text(value)
        finally:
            for item in [tag, suffix, value]:
                if item:
                    self.cf.CFRelease(item)

    def default_handler(self, uti):
        identifier = self.string(uti)
        value = None
        try:
            value = self.cs.LSCopyDefaultRoleHandlerForContentType(identifier, 0xffffffff)
            return self.text(value)
        finally:
            for item in [identifier, value]:
                if item:
                    self.cf.CFRelease(item)

    def register(self, path):
        encoded = str(path).encode("utf-8")
        url = self.cf.CFURLCreateFromFileSystemRepresentation(None, encoded, len(encoded), True)
        if not url:
            raise RuntimeError("Could not register the application bundle.")
        try:
            code = self.cs.LSRegisterURL(url, True)
            if code:
                raise RuntimeError("macOS could not register this app (code %d)." % code)
        finally:
            self.cf.CFRelease(url)

    def set_handler(self, uti):
        identifier, bundle = self.string(uti), self.string(BUNDLE_ID)
        try:
            code = self.cs.LSSetDefaultRoleHandlerForContentType(identifier, 0xffffffff, bundle)
            if code:
                raise RuntimeError("macOS did not accept the preferred app for %s (code %d)." % (uti, code))
            if self.default_handler(uti) != BUNDLE_ID:
                raise RuntimeError("macOS has not confirmed this default. Use Finder → Get Info → Open with → Change All.")
        finally:
            self.cf.CFRelease(identifier)
            self.cf.CFRelease(bundle)


def set_preferred_types(indices, native=None, bundle=None):
    if native is None and sys.platform != "darwin":
        return set_desktop_types(indices)
    native = native or LaunchServices()
    if bundle is None:
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Install and open the packaged app before setting file types.")
        bundle = Path(sys.executable).resolve().parents[2]
    if str(bundle).startswith("/Volumes/"):
        raise RuntimeError("Drag the app into Applications and open that copy before setting preferred file types.")
    native.register(bundle)
    changed, errors = [], []
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(FILE_TYPES):
            raise ValueError("Unknown molecular file type.")
    for index in sorted(set(indices)):
        group = FILE_TYPES[index]
        identifiers = {group["uti"]}
        identifiers.update(filter(None, (native.preferred_uti(ext) for ext in group["extensions"])))
        try:
            for uti in sorted(identifiers):
                native.set_handler(uti)
            changed.extend(group["extensions"])
        except RuntimeError as error:
            errors.append(str(error))
    return changed, errors


def show_file_types(parent, first_launch=False):
    from pymol.Qt import QtWidgets
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Choose preferred file types — " + APP_NAME)
    dialog.resize(560, 390)
    layout = QtWidgets.QVBoxLayout(dialog)
    text = QtWidgets.QLabel("Choose the file types you want to open in PyMOL AI-Assistant when double-clicked. Only checked types will change; unchecked types keep their current application.")
    text.setWordWrap(True)
    layout.addWidget(text)
    checks = []
    for group in FILE_TYPES:
        check = QtWidgets.QCheckBox(group["label"] + "  (" + ", ".join("." + ext for ext in group["extensions"]) + ")")
        layout.addWidget(check)
        checks.append(check)
    note = QtWidgets.QLabel("Windows confirms default applications in Settings after registration. Choose PyMOL AI-Assistant for the checked extensions there." if sys.platform == "win32" else "These files use PyMOL document icons when this package is their preferred app. Revisit this under AI Assistant → File Types…")
    note.setWordWrap(True)
    layout.addWidget(note)
    status = QtWidgets.QLabel()
    status.setWordWrap(True)
    layout.addWidget(status)
    buttons = QtWidgets.QHBoxLayout()
    all_button = QtWidgets.QPushButton("Select all")
    all_button.setAutoDefault(False)
    all_button.clicked.connect(lambda: [check.setChecked(True) for check in checks])
    buttons.addWidget(all_button)
    apply_button = QtWidgets.QPushButton("Register types and open Settings" if sys.platform == "win32" else "Set checked types as preferred")
    apply_button.setDefault(True)
    def apply():
        indices = [i for i, check in enumerate(checks) if check.isChecked()]
        if not indices:
            status.setText("Check at least one type, or choose Skip.")
            return
        try:
            changed, errors = set_preferred_types(indices)
            if errors:
                status.setText("\n".join(errors))
                return
            write_json(profile_dir() / "installation.json", {"fileTypesSetupSeen": True, "registeredExtensions" if sys.platform == "win32" else "preferredExtensions": changed, "defaultsRequireConfirmation": sys.platform == "win32"})
            dialog.accept()
        except (OSError, RuntimeError) as error:
            status.setText(str(error))
    apply_button.clicked.connect(apply)
    buttons.addWidget(apply_button)
    skip = QtWidgets.QPushButton("Skip" if first_launch else "Close")
    skip.setAutoDefault(False)
    skip.clicked.connect(dialog.reject)
    buttons.addWidget(skip)
    layout.addLayout(buttons)
    result = dialog.exec()
    if first_launch and not result:
        write_json(profile_dir() / "installation.json", {"fileTypesSetupSeen": True, "preferredExtensions": []})
    return result


def needs_setup():
    path = profile_dir() / "installation.json"
    try:
        return not json.loads(path.read_text(encoding="utf-8")).get("fileTypesSetupSeen")
    except (OSError, ValueError, AttributeError):
        return True


def set_desktop_types(indices):
    from .desktop import DESKTOP_ID, FORMATS
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(FILE_TYPES):
            raise ValueError("Unknown molecular file type.")
    extensions = [ext for index in sorted(set(indices)) for ext in FILE_TYPES[index]["extensions"]]
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Install and open the packaged app before setting file types.")
    if sys.platform == "win32":
        import winreg
        from .config import resources_dir
        def write(key, name, value):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)
        capabilities = r"Software\PyMOL AI-Assistant\Capabilities"
        write(capabilities, "ApplicationName", APP_NAME)
        write(capabilities, "ApplicationDescription", "Open-Source PyMOL with AI assistant")
        write(r"Software\RegisteredApplications", APP_NAME, capabilities)
        for extension in extensions:
            icon = next(icon for ext, _, icon in FORMATS if ext == extension)
            progid = "PyMOLAI." + extension
            root = "Software\\Classes\\" + progid
            write(root, "", "PyMOL " + extension.upper() + " document")
            write(root + r"\DefaultIcon", "", '"' + str(resources_dir() / ("icons/" + icon + ".ico")) + '",0')
            write(root + r"\shell\open\command", "", '\"' + sys.executable + '\" \"%1\"')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\." + extension + r"\OpenWithProgids") as handle:
                winreg.SetValueEx(handle, progid, 0, winreg.REG_NONE, b"")
            write(capabilities + r"\FileAssociations", "." + extension, progid)
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        os.startfile("ms-settings:defaultapps")
        return extensions, []
    errors = []
    changed = []
    for extension in extensions:
        mime = next(mime for ext, mime, _ in FORMATS if ext == extension)
        try:
            subprocess.run(["xdg-mime", "default", DESKTOP_ID, mime], check=True, timeout=10, capture_output=True)
            actual = subprocess.run(["xdg-mime", "query", "default", mime], check=True, timeout=10, capture_output=True, text=True).stdout.strip()
            if actual != DESKTOP_ID:
                raise RuntimeError("The desktop has not confirmed the preferred app for ." + extension)
            changed.append(extension)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            errors.append("Could not set ." + extension + "; use your desktop's Open With menu.")
    return changed, errors
