"""Create a DMG, per-user Windows installer, or native Ubuntu DEB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pymol_ai_assistant import __version__
from pymol_ai_assistant.desktop import DESKTOP_ID, FORMATS


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def frozen_bundle(work):
    if sys.platform == "darwin":
        return work / "freeze/PyMOL AI-Assistant.app"
    candidates = list((work / "freeze").glob("exe.*"))
    if len(candidates) != 1:
        raise RuntimeError("Expected one native frozen executable directory")
    return candidates[0]


def linux_deb(bundle, output, work):
    stage = work / "deb-root"
    if stage.exists():
        shutil.rmtree(stage)
    app = stage / "opt/pymol-ai-assistant"
    shutil.copytree(bundle, app, symlinks=True)
    desktop = stage / "usr/share/applications" / DESKTOP_ID
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\nType=Application\nName=PyMOL AI-Assistant\nComment=Molecular visualization with an AI assistant\nExec=\"/opt/pymol-ai-assistant/PyMOL AI-Assistant\" %F\nIcon=pymol-ai-assistant\nTerminal=false\nCategories=Education;Science;Chemistry;\nMimeType=" + ";".join(sorted({m for _, m, _ in FORMATS})) + ";\n")
    from PyQt5.QtGui import QImage
    def copy_icon(source, destination, size):
        if not QImage(str(source)).scaled(size, size).save(str(destination)):
            raise RuntimeError("Could not create desktop icon")
    for size in [48, 128, 256, 512]:
        for name in ["PyMOL", "PDB", "CIF", "PSE", "MOL", "MOL2"]:
            target = stage / ("usr/share/icons/hicolor/%dx%d" % (size, size)) / ("apps" if name == "PyMOL" else "mimetypes")
            target.mkdir(parents=True, exist_ok=True)
            if name == "PyMOL":
                copy_icon(ROOT / "icons/PyMOL.png", target / "pymol-ai-assistant.png", size)
            else:
                for _, mime, icon in FORMATS:
                    if icon == name:
                        copy_icon(ROOT / ("icons/" + icon + ".png"), target / (mime.replace("/", "-") + ".png"), size)
    namespace = "http://www.freedesktop.org/standards/shared-mime-info"
    import xml.etree.ElementTree as ET
    ET.register_namespace("", namespace)
    mime_root = Element("{" + namespace + "}mime-info")
    for mime in sorted({m for _, m, _ in FORMATS}):
        node = SubElement(mime_root, "{" + namespace + "}mime-type", type=mime)
        SubElement(node, "{" + namespace + "}comment").text = "PyMOL molecular document"
        for ext, m, _ in FORMATS:
            if m == mime:
                SubElement(node, "{" + namespace + "}glob", pattern="*." + ext)
    path = stage / "usr/share/mime/packages/pymol-ai-assistant.xml"
    path.parent.mkdir(parents=True)
    ElementTree(mime_root).write(path, encoding="utf-8", xml_declaration=True)
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "control").write_text("Package: pymol-ai-assistant\nVersion: " + __version__ + "\nArchitecture: amd64\nMaintainer: PyMOL AI-Assistant contributors\nSection: science\nPriority: optional\nDepends: libc6 (>= 2.35), libgl1, libegl1, libglu1-mesa, libx11-6, libxext6, libxrender1, libxfixes3, libxcb1, libxcb-cursor0, libxcb-xinerama0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxkbcommon-x11-0, xdg-utils, shared-mime-info\nInstalled-Size: " + str(sum(p.stat().st_size for p in app.rglob("*") if p.is_file()) // 1024) + "\nDescription: Open-Source PyMOL with an integrated AI assistant\n Standalone desktop app based on official Open-Source PyMOL 3.1.0.\n")
    (control / "postinst").write_text("#!/bin/sh\nset -e\nupdate-desktop-database /usr/share/applications >/dev/null 2>&1 || true\nupdate-mime-database /usr/share/mime >/dev/null 2>&1 || true\nif command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true; fi\n")
    (control / "postrm").write_text((control / "postinst").read_text())
    for name in ["postinst", "postrm"]:
        (control / name).chmod(0o755)
    for path in stage.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    run(["desktop-file-validate", desktop])
    destination = output / ("PyMOL-AI-Assistant-" + __version__ + "-Ubuntu-amd64.deb")
    run(["dpkg-deb", "--root-owner-group", "--build", stage, destination])
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work, output = args.work.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = frozen_bundle(work)
    if sys.platform == "darwin":
        stage = work / "dmg-stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        shutil.copytree(bundle, stage / bundle.name, symlinks=True)
        os.symlink("/Applications", stage / "Applications")
        destination = output / ("PyMOL-AI-Assistant-" + __version__ + "-macOS-" + platform.machine() + ".dmg")
        run(["hdiutil", "create", "-volname", "PyMOL AI-Assistant", "-srcfolder", stage, "-ov", "-format", "UDZO", destination])
        run(["hdiutil", "verify", destination])
    elif os.name == "nt":
        compiler = shutil.which("ISCC.exe") or str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe")
        run([compiler, "/DAppVersion=" + __version__, "/DBundleDir=" + str(bundle), "/DOutputDir=" + str(output), ROOT / "packaging/windows/installer.iss"])
        destination = output / ("PyMOL-AI-Assistant-" + __version__ + "-Windows-x64-Setup.exe")
    else:
        destination = linux_deb(bundle, output, work)
    (output / "SHA256SUMS.txt").write_text(hashlib.sha256(destination.read_bytes()).hexdigest() + "  " + destination.name + "\n")
    print(destination)


if __name__ == "__main__":
    main()
