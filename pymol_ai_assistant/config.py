"""Application-owned paths. Never import another application's credentials."""
import json
import os
import sys
import tempfile
from pathlib import Path

from . import APP_NAME


def profile_dir():
    override = os.environ.get("PYMOL_AI_ASSISTANT_PROFILE")
    if override:
        path = Path(override).expanduser().resolve()
    elif sys.platform == "darwin":
        path = Path.home() / "Library/Application Support" / APP_NAME
    elif sys.platform == "win32":
        path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pymol-ai-assistant"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.chmod(0o700)
    return path


def resources_dir():
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent.parent / "Resources"
                if sys.platform == "darwin" else Path(sys.executable).resolve().parent)
    return Path(__file__).resolve().parents[1]


def helper_path():
    path = resources_dir() / "ai" / ("pymol-ai-assistant.exe" if os.name == "nt" else "pymol-ai-assistant")
    return path


def write_json(path, value):
    """Atomic, private settings and local history, outside exported documents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".assistant-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
