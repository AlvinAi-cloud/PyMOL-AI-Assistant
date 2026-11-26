"""Real-engine checks for the explicit translucent-protein focus preset."""
import tempfile
import unittest

import pymol2

from pymol_ai_assistant.focus import apply_focus, default_focus_selection, focus_target
from pymol_ai_assistant.tools import MolecularTools


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.engine = pymol2.PyMOL()
        self.engine.start()
        self.cmd = self.engine.cmd
        self.cmd.fab('ACDEFG', 'chain_model')
        self.cmd.fragment('benzene', 'ligand')
        self.cmd.pseudoatom('water', resn='HOH')
        self.cmd.hide('everything', 'all')
        self.cmd.show('cartoon', 'chain_model')
        self.cmd.show('spheres', 'ligand or water')
        self.cmd.color('teal', 'chain_model')
        self.cmd.color('yellow', 'ligand')
        self.cmd.color('red', 'water')
        self.cmd.alter('all', 'b=23')
        self.cmd.set('cartoon_transparency', .15, 'chain_model')
        self.directory = tempfile.TemporaryDirectory()
        self.tools = MolecularTools(self.cmd, self.directory.name)

    def tearDown(self):
        self.engine.stop()
        self.directory.cleanup()

    def properties(self, selection='all'):
        rows = []
        self.cmd.iterate_state(1, selection,
            'rows.append((model,index,color,b,x,y,z))', space={'rows': rows})
        return rows

    def representations(self, selection='all'):
        result = {}
        for representation in ['cartoon', 'sticks', 'lines', 'spheres', 'surface', 'ribbon']:
            rows = []
            self.cmd.iterate('(' + selection + ') and rep ' + representation,
                             'rows.append((model,index))', space={'rows': rows})
            result[representation] = rows
        return result

    def atom_setting(self, setting, selection):
        values = []
        self.cmd.iterate(selection, 'values.append(s.' + setting + ')', space={'values': values})
        return values

    def bond_values(self, setting, selection):
        return [bond[2] for _model, bonds in self.cmd.get_bond(setting, selection, selection)
                for bond in bonds]

    def focus(self, selection='organic'):
        self.tools.apply([{'operation': 'graphics_focus', 'selection': selection}])

    def test_ligand_focus_uses_translucent_protein_and_opaque_sticks(self):
        self.cmd.set('stick_transparency', .5, 'ligand')
        self.tools.graphics.apply_preset('studio')
        before = self.properties()
        view = self.cmd.get_view()
        lighting = self.tools.graphics.state()
        water = self.representations('water')
        names = self.cmd.get_names('all')
        self.focus()
        self.assertEqual(self.properties(), before)
        self.assertEqual(self.cmd.get_view(), view)
        self.assertEqual(self.tools.graphics.state(), lighting)
        self.assertEqual(self.representations('water'), water)
        self.assertEqual(self.cmd.get_names('all'), names)
        self.assertEqual(self.cmd.count_atoms('polymer.protein and rep cartoon'),
                         self.cmd.count_atoms('polymer.protein'))
        values = self.atom_setting('cartoon_transparency', 'polymer.protein')
        self.assertTrue(values)
        self.assertTrue(all(abs(value - .7) < 1e-5 for value in values))
        self.assertEqual(self.cmd.count_atoms('ligand and rep sticks'), self.cmd.count_atoms('ligand'))
        values = self.bond_values('stick_transparency', 'ligand')
        self.assertTrue(values)
        self.assertTrue(all(abs(value) < 1e-6 for value in values))

    def test_ligand_sticks_replace_covering_reps_only_for_target(self):
        self.cmd.create('other_ligand', 'ligand')
        self.cmd.label('ligand and name C01', '"Bound ligand"')
        non_target = 'other_ligand or water'
        before = self.representations(non_target)
        for representation in ('spheres', 'surface', 'mesh', 'dots'):
            self.cmd.show(representation, 'ligand')
        self.focus('ligand')
        for representation in ('spheres', 'surface', 'mesh', 'dots'):
            self.assertEqual(self.cmd.count_atoms('ligand and rep ' + representation), 0)
        self.assertGreater(self.cmd.count_atoms('ligand and rep labels'), 0)
        self.assertEqual(self.representations(non_target), before)

    def test_selected_atom_expands_to_its_protein_residue(self):
        selected = 'chain_model and resi 3 and name CA'
        target = focus_target(self.cmd, selected)
        self.assertEqual(self.cmd.count_atoms(target), self.cmd.count_atoms('chain_model and resi 3'))
        before = self.properties()
        self.focus(selected)
        self.assertEqual(self.properties(), before)
        self.assertEqual(self.cmd.count_atoms('polymer.protein and rep sticks'),
                         self.cmd.count_atoms('chain_model and resi 3'))
        self.assertEqual(self.cmd.count_atoms('polymer.protein and rep sticks and not resi 3'), 0)
        values = self.bond_values('stick_transparency', 'chain_model and resi 3')
        self.assertTrue(values)
        self.assertTrue(all(abs(value) < 1e-6 for value in values))

    def test_existing_protein_surface_is_translucent_too(self):
        self.cmd.show('surface', 'chain_model and resi 1+2')
        surface = self.representations()['surface']
        self.focus()
        self.assertEqual(self.representations()['surface'], surface)
        values = self.atom_setting('transparency', 'polymer.protein')
        self.assertTrue(values)
        self.assertTrue(all(abs(value - .7) < 1e-5 for value in values))

    def test_focus_leaves_disabled_objects_untouched(self):
        self.cmd.create('hidden_protein', 'chain_model')
        self.cmd.create('hidden_ligand', 'ligand')
        self.cmd.hide('everything', 'hidden_protein')
        self.cmd.show('spheres', 'hidden_protein')
        self.cmd.show('surface', 'hidden_protein and resi 1')
        self.cmd.disable('hidden_protein')
        self.cmd.disable('hidden_ligand')
        hidden = 'hidden_protein or hidden_ligand'
        before = self.representations(hidden)
        opacity = self.atom_setting('cartoon_transparency', 'hidden_protein')

        result = apply_focus(self.cmd, default_focus_selection(self.cmd))

        self.assertEqual(result['proteinAtoms'], self.cmd.count_atoms('chain_model'))
        self.assertEqual(result['highlightedAtoms'], self.cmd.count_atoms('ligand'))
        self.assertEqual(result['retainedSurfaceAtoms'], 0)
        self.assertEqual(self.representations(hidden), before)
        self.assertEqual(self.atom_setting('cartoon_transparency', 'hidden_protein'), opacity)
        self.assertEqual(self.cmd.count_atoms('enabled and (' + hidden + ')'), 0)
        with self.assertRaises(ValueError):
            apply_focus(self.cmd, 'hidden_ligand')

    def test_default_focus_includes_only_active_mouse_selection(self):
        self.cmd.select('sele', 'chain_model and resi 3 and name CA', enable=0)
        target = focus_target(self.cmd, default_focus_selection(self.cmd))
        self.assertEqual(self.cmd.count_atoms(target), self.cmd.count_atoms('ligand'))
        self.cmd.enable('sele')
        target = focus_target(self.cmd, default_focus_selection(self.cmd))
        self.assertEqual(self.cmd.count_atoms(target),
                         self.cmd.count_atoms('ligand or (chain_model and resi 3)'))

    def test_disabled_parent_group_protects_enabled_descendants(self):
        self.cmd.create('group_protein', 'chain_model')
        self.cmd.create('group_ligand', 'ligand')
        self.cmd.group('members', 'group_protein group_ligand')
        self.cmd.group('parent+group', 'members')
        self.cmd.disable('parent+group')
        self.assertGreater(self.cmd.count_atoms('enabled and %members'), 0)
        before = self.representations('%members')

        result = apply_focus(self.cmd, default_focus_selection(self.cmd))

        self.assertEqual(result['proteinAtoms'], self.cmd.count_atoms('chain_model'))
        self.assertEqual(result['highlightedAtoms'], self.cmd.count_atoms('ligand'))
        self.assertEqual(self.representations('%members'), before)

    def test_undo_restores_representations_and_transparency(self):
        before = self.representations()
        opacity = self.atom_setting('cartoon_transparency', 'polymer.protein')
        properties = self.properties()
        self.focus()
        self.assertNotEqual(self.representations(), before)
        self.assertTrue(self.tools.undo())
        self.assertEqual(self.representations(), before)
        self.assertEqual(self.atom_setting('cartoon_transparency', 'polymer.protein'), opacity)
        self.assertEqual(self.properties(), properties)

    def test_lighting_presets_do_not_remove_focus(self):
        self.focus('organic or (chain_model and resi 3)')
        representations = self.representations()
        opacity = self.atom_setting('cartoon_transparency', 'polymer.protein')
        colors = self.properties()
        for name in ['simple', 'paper_cutout', 'studio']:
            self.tools.apply([{'operation': 'graphics_preset', 'preset': name}])
            self.assertEqual(self.representations(), representations)
            self.assertEqual(self.atom_setting('cartoon_transparency', 'polymer.protein'), opacity)
            self.assertEqual(self.properties(), colors)

    def test_invalid_or_absent_targets_fail_before_scene_changes(self):
        before = self.representations()
        opacity = self.atom_setting('cartoon_transparency', 'polymer.protein')
        for selection in ['none', '', 'water', 'all; delete all', 'no_such_object']:
            with self.assertRaises((ValueError, pymol2.pymol.CmdException)):
                self.focus(selection)
            self.assertEqual(self.representations(), before)
            self.assertEqual(self.atom_setting('cartoon_transparency', 'polymer.protein'), opacity)
        self.assertFalse(list(self.tools.directory.rglob('*.pse')))
        self.cmd.delete('ligand')
        with self.assertRaises(ValueError):
            apply_focus(self.cmd, 'organic')
        self.cmd.delete('chain_model')
        with self.assertRaises(ValueError):
            apply_focus(self.cmd, 'all')
