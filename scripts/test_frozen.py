"""Exercise the frozen native GUI with isolated profiles and a mock AI provider."""
import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

from package_native import frozen_bundle
from ci_windows_graphics import test_driver
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    bundle = frozen_bundle(work)
    executable = bundle / "Contents/MacOS/PyMOL AI-Assistant" if sys.platform == "darwin" else bundle / ("PyMOL AI-Assistant.exe" if os.name == "nt" else "PyMOL AI-Assistant")
    if sys.platform == "darwin":
        import plistlib
        from pymol_ai_assistant import __version__
        info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
        assert info["CFBundleShortVersionString"] == __version__, "Wrong frozen app version for this source"
    environment = dict(os.environ, PYMOL_AI_SKIP_SETUP="1", PYMOL_QA_EXPECT_ARCH=platform.machine())
    # No conda DLL/Qt paths inherited at runtime. Use only the frozen app.
    for name in ["PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"]:
        environment.pop(name, None)
    if os.name == "nt":
        system = Path(os.environ.get("SystemRoot", "C:/Windows"))
        environment["PATH"] = os.pathsep.join(map(str, [executable.parent, system / "System32", system]))
    else:
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    with test_driver(executable.parent):
        for name in ["QT_OPENGL", "QT_OPENGL_DLL"]:
            if name in os.environ:
                environment[name] = os.environ[name]
        for script, folder, setting in [("qa_draw_ray_popup.py", "popup", "PYMOL_POPUP_QA"), ("qa_gui_agent.py", "agent", "PYMOL_AI_QA_OUTPUT")]:
            output = work / ("qa-" + folder)
            output.mkdir(exist_ok=True)
            result = output / "result.json"
            result.unlink(missing_ok=True)
            environment[setting] = str(output)
            environment["PYMOL_AI_ASSISTANT_PROFILE"] = str(output / "profile")
            with (output / "stdout.log").open("w") as log:
                arguments = [str(executable), "-r", str(ROOT / "scripts" / script)]
                if sys.platform == "darwin":
                    # Exercise Finder/Launch Services architecture selection.
                    arguments = ["/usr/bin/open", "-n", "-W", str(bundle), "--args", "-r", str(ROOT / "scripts" / script)]
                subprocess.run(arguments, env=environment, timeout=100, check=True, stdout=log, stderr=subprocess.STDOUT)
            if not result.is_file() or not json.loads(result.read_text()).get("ok"):
                raise SystemExit("Frozen GUI regression failed: " + str(result))


if __name__ == "__main__":
    main()
