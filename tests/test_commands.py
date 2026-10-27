import json
import tempfile
import unittest

import pymol2

from pymol_ai_assistant.tools import MolecularTools


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.pymol = pymol2.PyMOL()
        self.pymol.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.cmd = self.pymol.cmd
        self.tools = MolecularTools(self.cmd, self.temporary.name)

    def tearDown(self):
        self.pymol.stop()
        self.temporary.cleanup()

    def command(self, text, **kwargs):
        return self.tools.apply([{"operation": "command", "command": text}], **kwargs)

    def test_native_interpreter_runs_batches_and_returns_real_values(self):
        results = self.command("fragment gly, example; count_atoms example\nalter example, b=25\niterate name CA, print(name, b)")
        self.assertEqual(self.cmd.count_atoms("example"), 7)
        self.assertEqual(json.loads(results[1])["result"], 7)
        self.assertIn("CA 25.0", json.loads(results[-1])["output"])

    def test_native_errors_are_reported_and_scene_changes_rolled_back(self):
        self.command("fragment gly, original")
        with self.assertRaises(RuntimeError):
            self.command("delete original; color not_a_real_color, all")
        self.assertEqual(self.cmd.count_atoms("original"), 7)
        self.assertTrue(self.tools.last_execution["sceneRestored"])
        self.assertFalse(self.tools.last_execution["ok"])
        self.assertIn("Error", self.tools.last_execution["results"][-1]["output"])

    def test_checkpoint_groups_multiple_rounds_and_query_does_not_replace_it(self):
        self.tools.begin_turn()
        self.command("fragment gly, example", grouped=True)
        checkpoint = self.tools.last_checkpoint
        self.command("color red, example", grouped=True)
        self.assertEqual(checkpoint, self.tools.last_checkpoint)
        self.command("count_atoms all")
        self.assertEqual(checkpoint, self.tools.last_checkpoint)
        self.tools.apply([{"operation": "restore_checkpoint"}])
        self.assertEqual(self.cmd.count_atoms("all"), 0)

    def test_recovery_survives_new_controller(self):
        self.command("fragment gly, original")
        self.command("delete original")
        restarted = MolecularTools(self.cmd, self.temporary.name)
        restarted.apply([{"operation": "restore_checkpoint"}])
        self.assertEqual(self.cmd.count_atoms("original"), 7)

    def test_context_includes_maps_for_broader_command_control(self):
        self.command("fragment gly, example; map_new density, gaussian, 1.0, example")
        objects = {item["name"]: item for item in self.tools.context()["objects"]}
        self.assertEqual(objects["density"]["type"], "object:map")

    def test_python_shell_script_and_callback_paths_rejected_before_changes(self):
        for text in ["system echo x", "/print('x')", "color = __import__('os')", "run /tmp/a.py", "load /tmp/a.py",
                     "alias bad, python", "mdo 1, print('x')", "alter all, __import__('os').getcwd()", "iterate all, print(name, file=p)"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.command("fragment gly, must_not_appear\n" + text)
            self.assertNotIn("must_not_appear", self.cmd.get_names("objects"))

    def test_cancel_stops_before_next_batch(self):
        self.tools.begin_turn()
        self.tools.cancelled.set()
        with self.assertRaises(RuntimeError):
            self.command("fragment gly, example", grouped=True)
        self.assertEqual(self.cmd.count_atoms("all"), 0)


if __name__ == "__main__":
    unittest.main()
