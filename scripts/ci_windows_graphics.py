"""Pinned software OpenGL for headless Windows CI; never shipped in installers."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

URL = "https://github.com/pal1000/mesa-dist-win/releases/download/26.2.4/mesa3d-26.2.4-release-msvc.7z"
SHA256 = "351fc8c8b695878ffb3eaa044b3ead08672a48b1a045e3c3e3975811df0f6695"


def deploy(app):
    source = os.environ.get("PYMOL_CI_MESA")
    if os.name != "nt" or not source:
        return []
    copied = []
    for path in Path(source).glob("*.dll"):
        target = Path(app) / path.name
        if not target.exists():
            shutil.copy2(path, target)
            copied.append(target)
    if not (Path(app) / "opengl32.dll").is_file():
        raise RuntimeError("CI software OpenGL driver was not deployed")
    return copied


@contextmanager
def test_driver(app):
    files = deploy(app)
    try:
        yield
    finally:
        for path in files:
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "install"])
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--app", type=Path)
    args = parser.parse_args()
    if args.operation == "install":
        deploy(args.app)
        return
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "mesa.7z"
    request = urllib.request.Request(URL, headers={"User-Agent": "PyMOL-AI-Assistant-CI"})
    with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("CI Mesa archive checksum mismatch")
    executable = shutil.which("7z") or "C:/Program Files/7-Zip/7z.exe"
    subprocess.run([executable, "x", "-y", "-o" + str(root), str(archive), "x64/*"], check=True)
    driver = root / "x64"
    if not (driver / "opengl32.dll").is_file():
        raise RuntimeError("The expected x64 Mesa driver is missing")
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
        output.write("PYMOL_CI_MESA=" + str(driver) + "\nGALLIUM_DRIVER=llvmpipe\nLIBGL_ALWAYS_SOFTWARE=1\n")
    print("Pinned CI-only Mesa driver ready: " + str(driver))


if __name__ == "__main__":
    main()
