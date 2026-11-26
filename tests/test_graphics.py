"""Verify actual rendering settings, molecular preservation and AI recovery."""
import json
import tempfile
import unittest
from pathlib import Path
import pymol2
from pymol_ai_assistant.graphics import PRESETS, PALETTES
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

    def test_all_eight_presets_preserve_camera_coordinates_and_representations(self):
        self.assertEqual(len(PRESETS), 8)
        self.assertEqual(list(PRESETS)[:6], ['simple','soft','full','flat','publication','illustration'])
        self.assertEqual(set(PRESETS) - set(list(PRESETS)[:6]), {'paper_cutout','studio'})
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

    def test_original_six_keep_their_lighting_and_background_contracts(self):
        for name in ['simple','soft','full','flat','publication','illustration']:
            self.tools.graphics.set_options({'background':'black','projection':'perspective','quality':'high'})
            self.tools.apply([{'operation':'graphics_preset','preset':name}])
            state = self.tools.graphics.state()
            self.assertEqual(state['background'], 'white' if name == 'publication' else 'black')
            self.assertEqual(state['projection'], 'perspective')
            self.assertEqual(state['quality'], 'high')
            self.assertEqual(state['silhouettes'], name in {'publication','illustration'})
            self.assertEqual(state['shadows'], name == 'full')
            self.assertEqual(state['surface_depth'], name in {'soft','full'})
            if name in {'flat','illustration'}:
                self.assertAlmostEqual(state['ambient'], 1)
                self.assertAlmostEqual(state['direct'], 0)

    def test_new_options_are_independent_and_report_manual_settings(self):
        self.tools.apply([{'operation':'graphics_preset','preset':'simple'},
            {'operation':'graphics_options','options':{'surface_depth':True,'outline_strength':'fine',
                'outline_color':'charcoal','projection':'orthographic','quality':'high'}}])
        state = self.tools.context()['graphics']['current']
        for key, value in {'surface_depth':True,'outline_strength':'fine','outline_color':'charcoal',
                           'projection':'orthographic','quality':'high'}.items():
            self.assertEqual(state[key],value)
        self.assertFalse(state['shadows'])
        self.assertFalse(state['silhouettes'], 'Configuring contours must not enable them implicitly')
        self.assertGreater(self.cmd.get_setting_int('ambient_occlusion_mode'), 0)
        self.assertGreater(self.cmd.get_setting_int('antialias'), 1)
        fine = self.cmd.get_setting_float('ray_trace_gain')
        self.tools.apply([{'operation':'graphics_options','options':{'outline_strength':'bold','outline_color':'black'}}])
        self.assertGreater(self.cmd.get_setting_float('ray_trace_gain'), fine)
        self.assertEqual(tuple(self.cmd.get_color_tuple(self.cmd.get_setting_int('ray_trace_color'))), (0.,0.,0.))
        for key, choices in {'surface_depth':[False,True],'outline_strength':['fine','standard','bold'],
                             'outline_color':['charcoal','black','gray'],
                             'projection':['orthographic','perspective'],'quality':['standard','high']}.items():
            for value in choices:
                self.tools.apply([{'operation':'graphics_options','options':{key:value}}])
                self.assertEqual(self.tools.graphics.state()[key],value)
        self.cmd.set('ambient_occlusion_mode', 1)
        self.cmd.set('ray_trace_gain', .031)
        self.cmd.set('ray_trace_color', 'red')
        self.cmd.set('orthoscopic', 0)
        self.cmd.set('antialias', 4)
        current = self.tools.context()['graphics']['current']
        self.assertTrue(current['surface_depth'])
        self.assertEqual(current['outline_strength'],'custom')
        self.assertEqual(current['outline_color'],'custom')
        self.assertEqual(current['projection'],'perspective')
        self.assertEqual(current['quality'],'custom')

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

    def test_background_choices_replace_saved_gradients_and_images(self):
        from pymol.Qt import QtGui

        graphics = self.tools.graphics
        cmd = self.cmd
        cmd.set('ray_opaque_background', -1)
        cmd.set('opaque_background', 0)
        self.assertEqual(graphics.state()['background'], 'transparent')

        folder = Path(self.directory.name)
        background = QtGui.QImage(8, 8, QtGui.QImage.Format_RGB32)
        background.fill(QtGui.QColor('red'))
        image_path = folder / 'red.png'
        self.assertTrue(background.save(str(image_path)))
        cmd.set('bg_image_filename', str(image_path))
        cmd.set('bg_gradient', 1)
        self.assertEqual(graphics.state()['background'], 'custom')
        for choice, expected in [('white', (255, 255, 255, 255)), ('transparent', None)]:
            graphics.set_options({'background': choice})
            self.assertEqual(graphics.state()['background'], choice)
            path = folder / (choice + '.png')
            cmd.png(str(path), 100, 80, ray=1, quiet=1)
            rendered = QtGui.QImage(str(path))
            self.assertEqual((rendered.width(), rendered.height()), (100, 80))
            pixel = rendered.pixelColor(0, 0)
            if expected is None:
                self.assertEqual(pixel.alpha(), 0)
            else:
                self.assertEqual(pixel.getRgb(), expected)

    def test_menu_projection_synchronizes_viewport_and_ray(self):
        graphics = self.tools.graphics
        self.cmd.set('orthoscopic', 0)
        self.cmd.set('ray_orthoscopic', 1)
        state = graphics.state()
        self.assertEqual(state['projection'], 'custom')
        self.assertEqual(state['viewportProjection'], 'perspective')
        self.assertEqual(state['rayProjection'], 'orthographic')
        graphics.set_options({'projection': 'perspective'})
        self.assertEqual(graphics.state()['projection'], 'perspective')
        self.assertEqual(graphics.state()['rayProjection'], 'perspective')

    def test_bad_options_validate_whole_batch_before_changes(self):
        before = self.tools.graphics.state()
        for invalid in [{'shadows':'false'}, {'background':'blue'}, {'material':'python'}, {'depth_cue':1},
                        {'ambient':.3}, {}, {'shadows':None}, {'surface_depth':1}, {'surface_depth':'true'},
                        {'outline_strength':'huge'}, {'outline_strength':.05}, {'outline_color':'red'},
                        {'projection':'parallel'}, {'quality':2}, {'quality':'ultra'}]:
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
                          {'operation':'graphics_options','options':{'background':'transparent','material':'glossy',
                              'surface_depth':True,'outline_strength':'bold','outline_color':'gray',
                              'projection':'perspective','quality':'high'}}])
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
        self.assertIn('graphics_palette',SYSTEM_PROMPT)
        self.assertEqual({p['id'] for p in context['palettes']},set(PALETTES))
        for key in ['surface_depth','outline_strength','outline_color','projection','quality']:
            self.assertIn(key,context['availableOptions'])

    def polymer_scene(self):
        self.cmd.delete('sample_model')
        self.cmd.fab('AGST', 'poly_one')
        self.cmd.fab('GAS', 'poly_two')
        # Identical chain IDs in different objects must still get distinct chain colors.
        self.cmd.alter('poly_one or poly_two', "chain='A'")
        self.cmd.pseudoatom('ligand', pos=[2,3,4], resn='LIG', name='C1', elem='C')
        self.cmd.pseudoatom('water', pos=[6,3,4], resn='HOH', name='O', elem='O')
        self.cmd.alter('all', 'b = 10 + index * 2')
        self.cmd.color('cyan', 'polymer')
        self.cmd.color('magenta', 'ligand')
        self.cmd.color('red', 'water')
        self.cmd.hide('everything', 'all')
        self.cmd.show('cartoon', 'polymer')
        self.cmd.show('spheres', 'ligand or water')
        self.cmd.orient('all')
        self.cmd.turn('y',19)
        self.cmd.turn('x',-11)
        self.assertGreater(self.cmd.count_atoms('polymer'),0)
        self.assertEqual(self.cmd.count_atoms('not polymer'),2)

    def atom_properties(self, selection='all'):
        rows = []
        self.cmd.iterate(selection, 'rows.append((model,index,segi,chain,resi,color,b))', space={'rows':rows})
        return rows

    def test_each_palette_preserves_molecular_data_and_can_be_undone(self):
        self.polymer_scene()
        original = self.atom_properties()
        nonpolymer = self.atom_properties('not polymer')
        coordinates = self.cmd.get_coords().copy()
        view = self.cmd.get_view()
        reps = [self.cmd.count_atoms('rep ' + rep) for rep in ['sticks','lines','cartoon','surface','spheres']]
        for palette in PALETTES:
            self.tools.apply([{'operation':'graphics_palette','palette':palette,'selection':'all'}])
            result = self.tools.last_execution['results'][0]['result']
            self.assertEqual(result['palette'],palette)
            self.assertEqual(result['polymerAtomsColored'],self.cmd.count_atoms('polymer'))
            self.assertEqual(result['chainsColored'],2)
            self.assertEqual(self.atom_properties('not polymer'),nonpolymer)
            self.assertEqual([row[:-2] + (row[-1],) for row in self.atom_properties()],
                             [row[:-2] + (row[-1],) for row in original])
            self.assertTrue((self.cmd.get_coords() == coordinates).all())
            self.assertEqual(self.cmd.get_view(),view)
            self.assertEqual([self.cmd.count_atoms('rep ' + rep) for rep in ['sticks','lines','cartoon','surface','spheres']],reps)
            chain_colors = {}
            residue_colors = {}
            for model,index,segi,chain,resi,color,b in self.atom_properties('polymer'):
                chain_colors.setdefault((model,segi,chain),set()).add(color)
                residue_colors.setdefault((model,segi,chain,resi),set()).add(color)
            self.assertTrue(all(len(colors)==1 for colors in residue_colors.values()))
            if palette == 'residue_gradient':
                self.assertTrue(all(len(colors)>1 for colors in chain_colors.values()))
                first = [next(iter(colors)) for key,colors in residue_colors.items() if key[-1]=='1']
                self.assertEqual(len(set(first)),1, 'The residue gradient should restart for each chain')
            else:
                self.assertTrue(all(len(colors)==1 for colors in chain_colors.values()))
                self.assertEqual(len(set.union(*chain_colors.values())),2)
            self.assertNotEqual(self.atom_properties('polymer'), [row for row in original if row[0].startswith('poly_')])
            self.assertTrue(self.tools.undo())
            self.assertEqual(self.atom_properties(),original)

    def test_palette_only_recolors_the_selected_polymer_subset(self):
        self.polymer_scene()
        target = 'poly_one and resi 2+3'
        untouched = self.atom_properties('not (' + target + ')')
        selected = self.atom_properties(target)
        self.tools.apply([{'operation':'graphics_palette','palette':'pastel_chains','selection':target}])
        self.assertEqual(self.atom_properties('not (' + target + ')'),untouched)
        self.assertNotEqual(self.atom_properties(target),selected)
        self.assertTrue(self.tools.undo())
        self.assertEqual(self.atom_properties(target),selected)
        self.tools.apply([{'operation':'select','name':'new_palette_target','selection':target},
                          {'operation':'graphics_palette','palette':'pastel_chains','selection':'new_palette_target'}])
        self.assertEqual(self.atom_properties('not (' + target + ')'),untouched)
        self.assertNotEqual(self.atom_properties(target),selected)

    def test_invalid_palette_and_nonpolymer_selections_validate_before_mutation(self):
        self.polymer_scene()
        original = self.atom_properties()
        before = self.tools.graphics.state()
        for palette, target in [('unknown','polymer'), ('pastel_chains','none'),
                                ('pastel_chains','ligand or water'), ('pastel_chains',''),
                                ('pastel_chains','polymer; color red, all')]:
            with self.assertRaises(ValueError):
                self.tools.apply([{'operation':'graphics_preset','preset':'studio'},
                                  {'operation':'graphics_palette','palette':palette,'selection':target}])
            self.assertEqual(self.atom_properties(),original)
            self.assertEqual(self.tools.graphics.state(),before)
        with self.assertRaises(ValueError):
            self.tools.apply([{'operation':'graphics_palette','palette':'pastel_chains'}])
        self.assertFalse(list(Path(self.directory.name).rglob('*.pse')))

    def test_presets_and_reset_never_implicitly_recolor_a_palette(self):
        self.polymer_scene()
        self.tools.apply([{'operation':'graphics_palette','palette':'contrast_chains','selection':'polymer'}])
        colored = self.atom_properties()
        for preset in PRESETS:
            self.tools.apply([{'operation':'graphics_preset','preset':preset}])
            self.assertEqual(self.atom_properties(),colored)
        self.tools.apply([{'operation':'graphics_reset'}])
        self.assertEqual(self.atom_properties(),colored)


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
