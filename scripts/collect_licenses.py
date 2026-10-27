"""Collect build metadata and license texts for Python, native and Rust components."""
import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copy_notices(directory, destination):
    if not directory.is_dir():
        return
    for path in directory.rglob("*"):
        if path.is_file() and path.name.lower().startswith(("license", "licence", "copying", "copyright", "notice")):
            target = destination / path.relative_to(directory)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-prefix", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    destination = ROOT / "licenses"
    packages = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        out = destination / "python" / (name + "-" + dist.version)
        out.mkdir(parents=True, exist_ok=True)
        (out / "METADATA.txt").write_text(dist.read_text("METADATA") or "Name: " + name + "\nVersion: " + dist.version + "\n")
        for entry in dist.files or []:
            if Path(str(entry)).name.lower().startswith(("license", "licence", "copying", "notice", "copyright")):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = out / str(entry).replace("../", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        packages.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License")})
    (destination / "python-build-environment.json").write_text(json.dumps(packages, indent=2) + "\n")
    native = []
    cache = args.native_prefix.parents[1] / "pkgs"
    for metadata in (args.native_prefix / "conda-meta").glob("*.json"):
        data = json.loads(metadata.read_text())
        native.append({key: data.get(key) for key in ["name", "version", "build", "channel", "url", "sha256", "license"]})
        folder = Path(data.get("link", {}).get("source") or cache / (data["name"] + "-" + data["version"] + "-" + data["build"]))
        copy_notices(folder / "info", destination / "native" / folder.name)
    (destination / "native-build-environment.json").write_text(json.dumps(native, indent=2) + "\n")
    for file in [args.native_prefix / "lib/python3.11/LICENSE.txt", args.native_prefix / "LICENSE.txt", args.native_prefix / "Lib/LICENSE.txt"]:
        if file.is_file():
            shutil.copy2(file, destination / "Python-LICENSE.txt")
    command = [args.cargo, "metadata", "--locked", "--format-version", "1", "--manifest-path", str(ROOT / "ai-helper/Cargo.toml")]
    metadata = json.loads(subprocess.check_output(command))
    rust = []
    for package in metadata["packages"]:
        if package["name"] == "pymol-ai-assistant":
            continue
        rust.append({key: package.get(key) for key in ["name", "version", "license", "source", "repository"]})
        parent = Path(package["manifest_path"]).parent
        for file in parent.iterdir():
            if file.is_file() and file.name.lower().startswith(("license", "licence", "copying", "copyright", "notice")):
                out = destination / "rust" / (package["name"] + "-" + package["version"])
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, out / file.name)
    (destination / "rust-dependencies.json").write_text(json.dumps(rust, indent=2) + "\n")


if __name__ == "__main__":
    main()
