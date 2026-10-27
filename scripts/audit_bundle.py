"""Reject Apple-Silicon-only binaries and dependencies outside the app/macOS."""
import argparse
import json
import subprocess
from pathlib import Path

MAGIC = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}


def audit(bundle, architecture="x86_64"):
    results, failures = [], []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in MAGIC:
                continue
        architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(path)], text=True).strip().split()
        if architecture not in architectures:
            failures.append(str(path.relative_to(bundle)) + ": lacks " + architecture)
        dependencies = []
        ids_output = subprocess.check_output(["/usr/bin/otool", "-D", str(path)], text=True)
        install_ids = {line.strip() for line in ids_output.splitlines() if line.strip() and not line.rstrip().endswith(":")}
        output = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True)
        for line in output.splitlines()[1:]:
            if not line.startswith("\t"):
                continue
            dependency = line.strip().split(" (compatibility", 1)[0]
            if dependency in install_ids:
                continue
            dependencies.append(dependency)
            if dependency.startswith("/") and not dependency.startswith(("/System/Library/", "/usr/lib/", "/Library/Apple/System/Library/")):
                failures.append(str(path.relative_to(bundle)) + ": external dependency " + dependency)
        results.append({"path": str(path.relative_to(bundle)), "architectures": architectures, "dependencies": dependencies})
    if not results:
        failures.append("No native executable found")
    return {"ok": not failures, "bundle": bundle.name, "nativeFiles": results, "failures": failures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--architecture", choices=["x86_64", "arm64"], default="x86_64")
    args = parser.parse_args()
    result = audit(args.bundle, args.architecture)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print("Native files:", len(result["nativeFiles"]))
    for failure in result["failures"]:
        print(failure)
    raise SystemExit(0 if result["ok"] else 1)
