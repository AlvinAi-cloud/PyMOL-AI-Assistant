"""Build pinned official PyMOL and the helper on the current native host."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--skip-engine", action="store_true", help="Reuse the locally compiled pinned engine for development")
    args = p.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    prefix = Path(sys.prefix)
    native = prefix / "Library" if os.name == "nt" else prefix
    environment["PREFIX_PATH"] = str(native)
    if os.name == "nt":
        environment["PATH"] = str(native / "bin") + os.pathsep + environment.get("PATH", "")
    elif sys.platform == "darwin":
        environment.update(CC="/usr/bin/clang", CXX="/usr/bin/clang++", MACOSX_DEPLOYMENT_TARGET="11.0")
    if not args.skip_engine:
        manifest = json.loads((ROOT / "upstream/manifest.json").read_text())
        archive = ROOT / "upstream" / manifest["archive"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["sha256"], "Upstream archive checksum mismatch"
        extracted = work / "upstream"
        if extracted.exists():
            shutil.rmtree(extracted)
        extracted.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(extracted, filter="data")
        source = next(extracted.glob("*/setup.py")).parent
        # Build via official setuptools options; source files are not patched.
        run([sys.executable, "setup.py", "--use-msgpackc=no", "install"], cwd=source, env=environment)
    environment["CARGO_TARGET_DIR"] = str(work / "rust-target")
    run(["cargo", "test", "--locked", "--manifest-path", ROOT / "ai-helper/Cargo.toml"], env=environment)
    run(["cargo", "build", "--release", "--locked", "--manifest-path", ROOT / "ai-helper/Cargo.toml"], env=environment)
    filename = "pymol-ai-assistant.exe" if os.name == "nt" else "pymol-ai-assistant"
    (ROOT / "ai").mkdir(exist_ok=True)
    # Never include a helper binary copied from a different architecture.
    for old in (ROOT / "ai").iterdir():
        if old.is_file():
            old.unlink()
    shutil.copy2(work / "rust-target/release" / filename, ROOT / "ai" / filename)
    run([sys.executable, ROOT / "scripts/build_icons.py", ROOT / "artwork/PyMOL-upstream.svg", ROOT / "icons"], env=environment)
    run([sys.executable, ROOT / "scripts/collect_licenses.py", "--native-prefix", prefix], env=environment)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, env=environment)
    environment["PYMOL_AI_BUILD_DIR"] = str(work / "freeze")
    run([sys.executable, "setup.py", "bdist_mac" if sys.platform == "darwin" else "build_exe"], cwd=ROOT, env=environment)


if __name__ == "__main__":
    main()
