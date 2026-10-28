"""Guard native architecture selection for separate Intel and ARM apps."""
import plistlib
from pathlib import Path
import tempfile
import unittest
from scripts.macos_plist import write_native_plist


class NativeMacPlistTests(unittest.TestCase):
    def test_native_build_overrides_inherited_intel_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.plist"
            template.write_bytes(plistlib.dumps({"LSArchitecturePriority": ["x86_64"], "CFBundleIdentifier": "test.app"}))
            for architecture in ["arm64", "x86_64"]:
                info = plistlib.loads(write_native_plist(template, root / architecture / "Info.plist", architecture).read_bytes())
                self.assertEqual(info["LSArchitecturePriority"], [architecture])
                self.assertEqual(info["CFBundleIdentifier"], "test.app")
                self.assertEqual(info.get("LSRequiresNativeExecution", False), architecture == "arm64")
            self.assertEqual(plistlib.loads(template.read_bytes())["LSArchitecturePriority"], ["x86_64"])
