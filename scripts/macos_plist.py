"""Generate Launch Services metadata for the native macOS build target."""
import plistlib
from pathlib import Path


def write_native_plist(template, destination, architecture):
    if architecture not in {"arm64", "x86_64"}:
        raise ValueError("Unsupported macOS target architecture: " + architecture)
    info = plistlib.loads(Path(template).read_bytes())
    info["LSArchitecturePriority"] = [architecture]
    # arm64 dependencies cannot run inside the launcher's Intel slice.
    if architecture == "arm64":
        info["LSRequiresNativeExecution"] = True
        info["CFBundleVersion"] = "6"
    else:
        info.pop("LSRequiresNativeExecution", None)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(plistlib.dumps(info))
    return destination
