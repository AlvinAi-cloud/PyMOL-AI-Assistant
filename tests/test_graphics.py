"""Verify actual rendering settings, molecular preservation and AI recovery."""
import json
import tempfile
import unittest
from pathlib import Path
import pymol2
from pymol_ai_assistant.graphics import PRESETS
from pymol_ai_assistant.tools import MolecularTools, parse_reply, SYSTEM_PROMPT


class GraphicsTests(unittest.TestCase):
    def setUp(self):
        self.engine = pymol2.PyMOL()
        self.engine.start()
        self.cmd = self.engine.cmd
        self.cmd.fragment('ala', 'sample_model')
        self.cmd.color('cyan', 'sample_model')
        self.cmd.show('sticks', 'sample_model')
        self.directory = tempfile.TemporaryDirectory()
        self.tools = MolecularTools(self.cmd, self.directory.name)

    def tearDown(self):
        self.engine.stop()
        self.directory.cleanup()

    def colors(self, model='sample_model'):
        colors = []
        self.cmd.iterate('model ' + model, 'colors.append(color)', space={'colors':colors})
        return colors

    def test_all_six_presets_preserve_camera_coordinates_and_representations(self):
        self.assertEqual(len(PRESETS), 6)
        view = self.cmd.get_view()
        coordinates = self.cmd.get_coords().copy()
        session_reps = [self.cmd.count_atoms('rep ' + rep) for rep in ['sticks','lines','cartoon','surface','spheres']]
        colors = self.colors()
        for name in PRESETS:
            self.tools.apply([{'operation':'graphics_preset','preset':name}])
            self.assertEqual(self.cmd.get_view(), view)
            self.assertTrue((self.cmd.get_coords() == coordinates).all())
            self.assertEqual([self.cmd.count_atoms('rep ' + rep) for rep in ['sticks','lines','cartoon','surface','spheres']], session_reps)
            self.assertEqual(self.colors(), colors)
            self.assertEqual(self.tools.last_execution['results'][0]['result']['preset'], name)
        self.assertEqual(self.colors(), colors)

    def test_independent_options_override_presets_and_context_reports_native_changes(self):
        self.tools.apply([{'operation':'graphics_preset','preset':'full'},
            {'operation':'graphics_options','options':{'shadows':False,'silhouettes':True,'background':'transparent','material':'matte','depth_cue':True}}])
        state = self.tools.context()['graphics']['current']
        for key, value in dict(shadows=False,silhouettes=True,background='transparent',material='matte',depth_cue=True).items():
            self.assertEqual(state[key],value)
        self.tools.apply([{'operation':'command','command':'set ray_shadows, 1; set specular, 0.7; set reflect, 0.35'}])
        current = self.tools.context()['graphics']['current']
        self.assertTrue(current['shadows'])
        self.assertEqual(current['material'],'glossy')
        self.tools.apply([{'operation':'graphics_preset','preset':'simple'}])
        state = self.tools.graphics.state()
        self.assertEqual(state['background'],'transparent')
        self.assertFalse(state['silhouettes'])
        self.assertFalse(state['depth_cue'])
        self.tools.apply([{'operation':'graphics_preset','preset':'publication'}])
        self.assertEqual(self.tools.graphics.state()['background'],'white')

    def test_bad_options_validate_whole_batch_before_changes(self):
        before = self.tools.graphics.state()
        for invalid in [{'shadows':'false'}, {'background':'blue'}, {'material':'python'}, {'depth_cue':1}, {'ambient':.3}, {}, {'shadows':None}]:
            with self.assertRaises(ValueError):
                self.tools.apply([{'operation':'graphics_preset','preset':'full'}, {'operation':'graphics_options','options':invalid}])
            self.assertEqual(self.tools.graphics.state(),before)
        self.assertFalse(list(Path(self.directory.name).rglob('*.pse')))
        with self.assertRaises(ValueError):
            self.tools.apply([{'operation':'graphics_preset','preset':'not_a_preset'}])

    def test_graphics_changes_survive_session_roundtrip_and_undo(self):
        original = self.colors()
        before = self.tools.graphics.state()
        self.tools.apply([{'operation':'graphics_preset','preset':'illustration'},
                          {'operation':'graphics_options','options':{'background':'transparent','material':'glossy'}}])
        expected = self.tools.graphics.state()
        scene = Path(self.directory.name)/'scene.pse'
        self.cmd.save(str(scene))
        self.tools.apply([{'operation':'graphics_reset'}])
        self.cmd.load(str(scene))
        self.assertEqual(self.tools.graphics.state(),expected)
        # Undo the prior reset, then undo the grouped illustration/options turn.
        self.assertTrue(self.tools.undo())
        self.assertTrue(self.tools.undo())
        self.assertEqual(self.tools.graphics.state(),before)
        self.assertEqual(self.colors(),original)

    def test_removed_gold_preset_is_rejected_without_changes(self):
        before = self.tools.graphics.state()
        colors = self.colors()
        with self.assertRaises(ValueError):
            self.tools.apply([{'operation':'graphics_preset','preset':'gold_illustration'}])
        self.assertEqual(self.tools.graphics.state(),before)
        self.assertEqual(self.colors(),colors)
        self.assertNotIn('gold_illustration', SYSTEM_PROMPT)
        self.assertNotIn('Gold Illustration', json.dumps(self.tools.context()['graphics']))

    def test_ai_schema_and_discovery_advertise_graphics_tools(self):
        action = {'operation':'graphics_options','options':{'background':'transparent'}}
        self.assertEqual(parse_reply(json.dumps({'message':'','actions':[action]}))[1],[action])
        context = self.tools.context()['graphics']
        self.assertEqual({p['id'] for p in context['presets']},set(PRESETS))
        self.assertIn('graphics_preset',SYSTEM_PROMPT)
        self.assertIn('graphics_reset',SYSTEM_PROMPT)


class ReviewProfileTests(unittest.TestCase):
    def test_review_marker_uses_private_profile_and_keeps_explicit_override(self):
        from unittest import mock
        from pymol_ai_assistant import config, __version__
        import sys
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resources = root / 'Resources'
            resources.mkdir()
            (resources / 'LOCAL_REVIEW').write_text('local review')
            with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.object(sys, 'platform', 'darwin'), mock.patch.object(config, 'resources_dir', return_value=resources), mock.patch.object(Path, 'home', return_value=root), mock.patch.dict(config.os.environ, {'PYMOL_AI_ASSISTANT_PROFILE':''}):
                self.assertTrue(config.is_review_build())
                self.assertEqual(config.profile_dir().name, 'PyMOL AI-Assistant Local Review ' + __version__)
                with mock.patch.dict(config.os.environ, {'PYMOL_AI_ASSISTANT_PROFILE':str(root/'qa')}):
                    self.assertEqual(config.profile_dir(),(root/'qa').resolve())
