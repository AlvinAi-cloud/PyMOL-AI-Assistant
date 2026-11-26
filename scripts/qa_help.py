"""Check both local help menus in the real GUI without changing the scene."""
import json
import os
from pathlib import Path
import traceback

from pymol.Qt import QtCore, QtWidgets
from pmg_qt import pymol_qt_gui
from pymol_ai_assistant.help_content import HELP_PAGES
from pymol_ai_assistant.graphics import PRESETS
from pymol_ai_assistant.config import is_review_build

OUT = Path(os.environ['PYMOL_HELP_QA']).resolve()
OUT.mkdir(parents=True, exist_ok=True)


def finish(error=None):
    if (OUT / 'result.json').exists():
        return
    (OUT / 'result.json').write_text(json.dumps({'ok': error is None, 'error': error,
        'helpTopics': list(HELP_PAGES) if error is None else []}, indent=2))
    pymol_qt_gui.window.close()


def ready():
    try:
        w = pymol_qt_gui.window
        if not hasattr(w, 'graphics_ui'):
            QtCore.QTimer.singleShot(200, ready)
            return
        w.ai_assistant.example()
        before_view = w.cmd.get_view()
        before_session = w.cmd.get_session()
        before_graphics = w.ai_assistant.tools.graphics.state()
        before_history = list(w.ai_assistant.history)
        assistant_menu = next(action.menu() for action in w.menuBar().actions()
                              if action.text() == 'AI Assistant')
        file_types_visible = any(action.text().startswith('File Types') for action in assistant_menu.actions())
        assert file_types_visible != is_review_build()
        # Help remains accessible while an AI operation locks graphics editing.
        w.graphics_ui.set_busy(True)
        assert w.graphics_ui.menu.menuAction().isEnabled()
        assert not w.graphics_ui.focus_action.isEnabled()
        dialog = None
        for section, keys in [('assistant', ['assistant_start', 'assistant_capabilities']),
                              ('presets', ['presets_guide', 'rendering_guide'])]:
            menu = w.findChild(QtWidgets.QMenu, section + '_help_menu')
            assert menu and len(menu.actions()) == 2
            for key in keys:
                action = w.findChild(QtWidgets.QAction, 'help_' + key)
                assert action in menu.actions()
                action.trigger()
                current = w.package_help_dialog
                assert current.isVisible() and not current.isModal()
                assert dialog is None or current is dialog
                dialog = current
                assert dialog.topics.currentItem().data(QtCore.Qt.UserRole) == key
                text = dialog.browser.toPlainText()
                assert HELP_PAGES[key][0] in text and len(text) > 600
                if key == 'presets_guide':
                    for label, _, _ in PRESETS.values():
                        assert label in text
                    assert 'Pastel chains' in text and 'Residue gradient' in text
                    assert 'Combinations to try' in text
                if key == 'rendering_guide':
                    assert 'Ray' in text and 'transparent' in text and 'Draw' in text
                dialog.grab().save(str(OUT / (key + '.png')))
                dialog.close()
        assert w.cmd.get_view() == before_view
        # No atom/object/render setting changes or assistant conversation entries.
        after = w.cmd.get_session()
        for key in ['names', 'view']:
            assert after.get(key) == before_session.get(key), key
        assert w.ai_assistant.tools.graphics.state() == before_graphics
        assert w.ai_assistant.history == before_history
        w.graphics_ui.set_busy(False)
        w.cmd.select('sele', 'example_1hpv and resi 25 and polymer.protein')
        w.graphics_ui.focus_action.trigger()
        result = w.ai_assistant.tools.last_execution
        assert result['ok']
        focus = result['results'][0]['result']
        assert focus['highlightedAtoms'] > 0 and focus['proteinTransparency'] == .70
        assert w.cmd.get_view() == before_view
        assert w.cmd.count_atoms('polymer.protein and rep cartoon') > 0
        assert w.cmd.count_atoms('organic and rep sticks') > 0
        assert w.cmd.count_atoms('sele and polymer.protein and not rep sticks') == 0
        w.cmd.png(str(OUT / 'focus-ray.png'), width=650, height=450, ray=1, quiet=1)
        assert (OUT / 'focus-ray.png').stat().st_size > 0
        finish()
    except Exception:
        finish(traceback.format_exc())


QtCore.QTimer.singleShot(900, ready)
QtCore.QTimer.singleShot(20000, lambda: finish('Help GUI test timed out'))
