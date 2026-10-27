"""Rebuild the Intel package from pinned official upstream and checked-in sources.

Developer prerequisites: Intel Mac, Xcode Command Line Tools, Rust, and an
isolated native dependency prefix with Python 3.11, GLEW, GLM, libpng, freetype,
libxml2 and libnetcdf. For example, prepare a separate conda-forge environment.
The built .app does not require that environment on end users' computers.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/schrodinger/pymol-open-source.git"
COMMIT = "f51e58f6b08308c41c85b9d12a23231f49ca325a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-prefix", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "x86_64":
        raise SystemExit("Build on an Intel Mac for this initial package.")
    prefix, work, output = (p.expanduser().resolve() for p in [args.native_prefix, args.work, args.output])
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    source = work / "pymol-upstream"
    if not source.exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", "v3.1.0", UPSTREAM, str(source)], check=True)
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise SystemExit("The upstream checkout differs from the pinned commit.")
    python = work / "build-env/bin/python"
    if not python.exists():
        subprocess.run([str(prefix / "bin/python"), "-m", "venv", str(python.parents[1])], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-build.txt")], check=True)
    environment = dict(os.environ, PREFIX_PATH=str(prefix), CC="/usr/bin/clang", CXX="/usr/bin/clang++", MACOSX_DEPLOYMENT_TARGET="11.0")
    environment["PATH"] = str(python.parent) + os.pathsep + environment.get("PATH", "/usr/bin:/bin")
    subprocess.run([str(python), "-m", "pip", "install", "--no-build-isolation", "--config-settings", "use-msgpackc=no", str(source)], env=environment, check=True)
    environment["CARGO_TARGET_DIR"] = str(work / "rust-target")
    subprocess.run([args.cargo, "test", "--locked", "--manifest-path", str(ROOT / "ai-helper/Cargo.toml")], env=environment, check=True)
    subprocess.run([args.cargo, "build", "--release", "--locked", "--manifest-path", str(ROOT / "ai-helper/Cargo.toml")], env=environment, check=True)
    (ROOT / "ai").mkdir(exist_ok=True)
    shutil.copy2(work / "rust-target/release/pymol-ai-assistant", ROOT / "ai/pymol-ai-assistant")
    subprocess.run([str(python), str(ROOT / "scripts/collect_licenses.py"), "--native-prefix", str(prefix), "--cargo", args.cargo], env=environment, check=True)
    subprocess.run([str(python), str(ROOT / "scripts/build_icons.py"), str(ROOT / "artwork/PyMOL-upstream.svg"), str(ROOT / "icons")], env=environment, check=True)
    environment["PYTHONPATH"] = str(ROOT)
    subprocess.run([str(python), "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], env=environment, check=True)
    environment["PYMOL_AI_BUILD_DIR"] = str(work / "freeze")
    subprocess.run([str(python), str(ROOT / "setup.py"), "bdist_mac"], cwd=ROOT, env=environment, check=True)
    bundle = work / "freeze/PyMOL AI-Assistant.app"
    subprocess.run([str(python), str(ROOT / "scripts/audit_bundle.py"), str(bundle), "--report", str(output / "architecture-and-dependencies.json")], check=True)
    test_directory = work / "packaged-self-test"
    test_directory.mkdir(exist_ok=True)
    environment["PYMOL_AI_ASSISTANT_PROFILE"] = str(work / "self-test-profile")
    subprocess.run([str(bundle / "Contents/MacOS/PyMOL AI-Assistant"), "--self-test=" + str(test_directory)], env=environment, timeout=90, check=True)
    import json
    if not json.loads((test_directory / "result.json").read_text()).get("ok"):
        raise SystemExit("Packaged application self-test failed.")
    destination = output / bundle.name
    if destination.exists():
        raise SystemExit("Output app already exists; choose a fresh output folder.")
    shutil.copytree(bundle, destination, symlinks=True)
    print(destination)


if __name__ == "__main__":
    main()

