import json
import tempfile
import unittest
from pathlib import Path

import pymol2

from pymol_ai_assistant.tools import MolecularTools, parse_reply, response_text
from pymol_ai_assistant.associations import FILE_TYPES, set_preferred_types


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.pymol = pymol2.PyMOL()
        self.pymol.start()
        self.cmd = self.pymol.cmd
        self.cmd.fragment("gly", "glycine")
        self.temporary = tempfile.TemporaryDirectory()
        self.tools = MolecularTools(self.cmd, self.temporary.name)

    def tearDown(self):
        self.pymol.stop()
        self.temporary.cleanup()

    def colors(self, selection="glycine"):
        values = []
        self.cmd.iterate(selection, "values.append(color)", space={"values": values})
        return values

    def test_actions_and_checkpoint_undo_restore_color_and_selection(self):
        before = self.colors()
        self.tools.apply([
            {"operation": "select", "name": "ai_carbons", "selection": "glycine and elem C"},
            {"operation": "color", "selection": "ai_carbons", "color": "red"},
        ])
        self.assertGreater(self.cmd.count_atoms("ai_carbons"), 0)
        self.assertEqual(set(self.colors("ai_carbons")), {self.cmd.get_color_index("red")})
        self.assertTrue(self.tools.undo())
        self.assertNotIn("ai_carbons", self.cmd.get_names("selections"))
        self.assertEqual(self.colors(), before)

    def test_complete_proposal_validates_before_changing_scene(self):
        before = self.colors()
        with self.assertRaises(ValueError):
            self.tools.apply([
                {"operation": "color", "selection": "glycine", "color": "red"},
                {"operation": "zoom", "selection": "missing_object", "buffer": 3},
            ])
        self.assertEqual(self.colors(), before)
        self.assertFalse(list(Path(self.temporary.name).rglob("*.pse")))

    def test_unsupported_code_and_selection_commands_rejected(self):
        for selection in ["all; delete all", "all\npython pass", "@/private/tmp/atoms.txt"]:
            with self.assertRaises(ValueError):
                self.tools.validate([{"operation": "orient", "selection": selection}])
        with self.assertRaises(ValueError):
            parse_reply('{"message":"x","actions":[{"operation":"python","code":"pass"}]}')

    def test_distance_is_calculated_by_engine_and_requires_single_atoms(self):
        result = self.tools.apply([{"operation": "distance", "selection1": "glycine and name N", "selection2": "glycine and name CA", "name": "bond_measurement"}])
        expected = self.cmd.get_distance("glycine and name N", "glycine and name CA")
        self.assertIn("%.3f" % expected, result[0])
        with self.assertRaises(ValueError):
            self.tools.validate([{"operation": "distance", "selection1": "glycine", "selection2": "glycine and name N", "name": "ambiguous"}])

    def test_duplicate_created_names_rejected_before_changes(self):
        with self.assertRaises(ValueError):
            self.tools.apply([{"operation": "select", "name": "same_name", "selection": "glycine"}] * 2)
        self.assertNotIn("same_name", self.cmd.get_names("selections"))

    def test_context_excludes_coordinates_sequences_and_paths_by_default(self):
        self.cmd.select("sele", "glycine")
        context = self.tools.context()
        self.assertEqual(context["selectedAtoms"], self.cmd.count_atoms("glycine"))
        text = json.dumps(context)
        self.assertNotIn("coord", text)
        self.assertNotIn("Sequence", text)
        self.assertNotIn(self.temporary.name, text)
        self.tools.apply([{"operation":"get_sequence", "selection":"sele"}])
        fasta = self.tools.last_execution["results"][0]["result"]["fasta"]
        self.assertIn("G", fasta)
        self.assertFalse(list(Path(self.temporary.name).rglob("*.pse")))

    def test_inspection_is_read_only_and_does_not_persist_image_bytes(self):
        self.tools.capture = lambda target: ("data:image/jpeg;base64,/9j/", {"target":target})
        self.tools.apply([{"operation":"inspect_view", "target":"viewport"}])
        self.assertEqual(len(self.tools.images), 1)
        self.assertFalse(list(Path(self.temporary.name).rglob("*.pse")))
        self.assertNotIn("base64", (Path(self.temporary.name)/"last-operation.json").read_text())
        self.tools.begin_turn()
        self.assertEqual(self.tools.images, [])
        with self.assertRaises(ValueError):
            self.tools.apply([{"operation":"inspect_view", "target":"desktop"}])


class FormatTests(unittest.TestCase):
    def test_supported_provider_envelopes_and_nullable_error(self):
        self.assertEqual(response_text({"status": "completed", "error": None, "output": [{"content": [{"type": "output_text", "text": "answer"}]}]}), "answer")
        self.assertEqual(response_text({"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]}), "answer")
        self.assertEqual(response_text({"content": [{"type": "text", "text": "answer"}]}), "answer")
        self.assertEqual(response_text({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "answer"}]}}]}), "answer")
        with self.assertRaises(ValueError):
            response_text({"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]})

    def test_plain_text_is_not_executed_and_unexpected_fields_rejected(self):
        self.assertEqual(parse_reply("Please load a structure first."), ("Please load a structure first.", []))
        with self.assertRaises(ValueError):
            parse_reply('{"message":"x", "actions":[], "code":"pass"}')

    def test_only_checked_file_types_are_changed(self):
        class FakeLaunchServices:
            changed = []
            def register(self, bundle):
                self.bundle = bundle
            def preferred_uti(self, extension):
                return "test." + extension
            def set_handler(self, uti):
                self.changed.append(uti)
        native = FakeLaunchServices()
        changed, errors = set_preferred_types([2], native=native, bundle=Path("/Applications/Test.app"))
        self.assertEqual(changed, ["pse"])
        self.assertEqual(errors, [])
        self.assertEqual(set(native.changed), {FILE_TYPES[2]["uti"], "test.pse"})
        self.assertNotIn("test.pdb", native.changed)


if __name__ == "__main__":
    unittest.main()
