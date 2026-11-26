"""One graphics menu shared by the menu bar and native quick-button area."""
import textwrap

from pymol.Qt import QtCore, QtGui, QtWidgets
from .graphics import PRESETS, PALETTES, RENDER_NOTE, HELP
from .focus import FOCUS_HELP, default_focus_selection


def set_help(action, text):
    action.setToolTip(textwrap.fill(text, width=58))
    action.setWhatsThis(text)
    action.setStatusTip(text)



class HelpMenu(QtWidgets.QMenu):
    """Show action help for both Qt popups and native macOS menu highlights."""
    def __init__(self, title, parent):
        super().__init__(title, parent)
        self.setToolTipsVisible(True)
        self._help_action = None
        self._help_open = False
        self._help_timer = QtCore.QTimer(self)
        self._help_timer.setSingleShot(True)
        self._help_timer.setInterval(650)
        self._help_timer.timeout.connect(self.show_action_help)
        self.aboutToShow.connect(self.help_opened)
        self.aboutToHide.connect(self.help_closed)
        self.hovered.connect(self.help_hovered)

    def help_opened(self):
        self._help_open = True

    def help_closed(self):
        self._help_open = False
        self._help_timer.stop()
        QtWidgets.QToolTip.hideText()

    def help_hovered(self, action):
        self._help_action = action
        self._help_timer.stop()
        QtWidgets.QToolTip.hideText()
        if action.isEnabled() and action.toolTip():
            self._help_timer.start()

    def show_action_help(self):
        action = self._help_action
        if self._help_open and action and action.isEnabled() and action.toolTip():
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos() + QtCore.QPoint(16, 20), action.toolTip())


class GraphicsMenu:
    def __init__(self, window, dock):
        self.window, self.dock = window, dock
        self.menu = HelpMenu('Presets', window)
        window.menuBar().addMenu(self.menu)
        self.menu.setObjectName('graphics_presets_menu')
        self.presets, self.toggles, self.choices, self.palettes = {}, {}, {}, {}
        self.rendering_submenus = []
        for key, (label, description, _settings) in PRESETS.items():
            action = self.menu.addAction(label)
            action.setObjectName('graphics_preset_' + key)
            set_help(action, description)
            action.triggered.connect(lambda _checked=False, key=key: self.apply({'operation': 'graphics_preset', 'preset': key}))
            self.presets[key] = action
        self.menu.addSeparator()
        self.focus_action = self.menu.addAction('Transparent protein + highlights')
        self.focus_action.setObjectName('graphics_focus_transparent_protein')
        set_help(self.focus_action, FOCUS_HELP)
        self.focus_action.triggered.connect(self.focus)
        self.menu.addSeparator()
        for key, label, tip in [
            ('shadows', 'Shadows (Ray)', HELP['shadows']),
            ('silhouettes', 'Silhouettes (Ray)', HELP['silhouettes']),
            ('depth_cue', 'Depth cue', HELP['depth_cue']),
            ('surface_depth', 'Surface depth (AO)', HELP['surface_depth'])]:
            action = self.menu.addAction(label)
            action.setCheckable(True)
            action.setObjectName('graphics_option_' + key)
            set_help(action, tip)
            action.triggered.connect(lambda checked, key=key: self.options({key: checked}))
            self.toggles[key] = action
        for key, title, entries in [
            ('background', 'Background', [('white','White'),('black','Black'),('transparent','Transparent PNG')]),
            ('material', 'Material', [('matte','Matte'),('glossy','Glossy')]),
            ('outline_strength', 'Outline strength (Ray)', [('fine','Fine'),('standard','Standard'),('bold','Bold')]),
            ('outline_color', 'Outline color (Ray)', [('charcoal','Charcoal'),('black','Black'),('gray','Gray')]),
            ('projection', 'Projection', [('orthographic','Orthographic'),('perspective','Perspective')]),
            ('quality', 'Render quality (Ray)', [('standard','Standard'),('high','High (slower)')])]:
            submenu = HelpMenu(title, self.menu)
            self.menu.addMenu(submenu)
            self.rendering_submenus.append(submenu)
            set_help(submenu.menuAction(), HELP[key])
            group = QtWidgets.QActionGroup(submenu)
            group.setExclusive(True)
            self.choices[key] = {}
            for value, label in entries:
                action = submenu.addAction(label)
                action.setCheckable(True)
                action.setObjectName('graphics_' + key + '_' + value)
                group.addAction(action)
                set_help(action, HELP[key + "_" + value])
                action.triggered.connect(lambda _checked=False, key=key, value=value: self.options({key:value}))
                self.choices[key][value] = action
        palette_menu = HelpMenu('Polymer colors', self.menu)
        palette_menu.setObjectName('graphics_polymer_colors_menu')
        self.menu.addMenu(palette_menu)
        self.rendering_submenus.append(palette_menu)
        set_help(palette_menu.menuAction(), HELP['palettes'])
        for key, (label, description) in PALETTES.items():
            action = palette_menu.addAction(label)
            action.setObjectName('graphics_palette_' + key)
            set_help(action, description)
            action.triggered.connect(lambda _checked=False, key=key: self.apply(
                {'operation':'graphics_palette', 'palette':key, 'selection':'polymer'}))
            self.palettes[key] = action
        self.menu.addSeparator()
        self.preview_action = self.menu.addAction('Render preview (Ray)')
        self.preview_action.setObjectName('graphics_render_preview')
        set_help(self.preview_action, HELP['render_preview'])
        self.preview_action.triggered.connect(self.render_preview)
        reset = self.menu.addAction('Reset graphics')
        set_help(reset, HELP['reset'])
        reset.triggered.connect(lambda: self.apply({'operation':'graphics_reset'}))
        self.edit_actions = [*self.presets.values(), self.focus_action, *self.toggles.values(),
                             self.preview_action, reset]
        self.menu.addSeparator()
        from .help_ui import install_help_menu
        install_help_menu(window, self.menu, 'presets')
        note = self.menu.addAction('Shadows and outlines: use Draw/Ray')
        note.setEnabled(False)
        self.menu.aboutToShow.connect(self.refresh)
        self.button = QtWidgets.QPushButton('Presets')
        self.button.setObjectName('graphics_presets_button')
        self.button.setProperty('quickbutton', True)
        self.button.setAttribute(QtCore.Qt.WA_LayoutUsesWidgetRect)
        self.button.setToolTip(textwrap.fill(HELP['button'], width=58))
        self.button.setMenu(self.menu)
        self.install_shortcut()
        dock.agent.busy_changed.connect(self.set_busy)

    def set_busy(self, busy):
        for action in self.edit_actions:
            action.setEnabled(not busy)
        for submenu in self.rendering_submenus:
            submenu.setEnabled(not busy)

    def install_shortcut(self):
        # Wrap the Builder/Properties row without changing its parent layout's
        # item count: upstream captures the stretch index for dock relocation.
        builder = next((b for b in self.window.findChildren(QtWidgets.QPushButton)
                        if b.text() in {'Builder', 'Build'}), None)
        def wrap(layout):
            if layout is None:
                return False
            for index in range(layout.count()):
                child = layout.itemAt(index).layout()
                if child is None:
                    continue
                if builder is not None and child.indexOf(builder) >= 0:
                    row = layout.takeAt(index).layout()
                    row.setParent(None)
                    stack = QtWidgets.QVBoxLayout()
                    stack.setSpacing(6)
                    stack.addLayout(row)
                    stack.addWidget(self.button)
                    layout.insertLayout(index, stack)
                    return True
                if wrap(child):
                    return True
            return False
        ext = self.window.findChild(QtWidgets.QWidget, 'extgui')
        if ext is None or not wrap(ext.layout()):
            # Keep the shortcut available on versions with a different native UI.
            toolbar = self.window.addToolBar('Graphics presets')
            toolbar.setObjectName('graphics_presets_fallback_toolbar')
            toolbar.addWidget(self.button)

    def options(self, values):
        self.apply({'operation':'graphics_options','options':values})

    def focus(self):
        self.apply({'operation': 'graphics_focus', 'selection': default_focus_selection(self.window.cmd)})

    def apply(self, action):
        try:
            self.dock.tools.apply([action])
            if action['operation'] == 'graphics_preset':
                label = PRESETS[action['preset']][0]
            elif action['operation'] == 'graphics_palette':
                label = PALETTES[action['palette']][0] + ' applied to polymers; nonpolymer colors retained'
            elif action['operation'] == 'graphics_focus':
                label = 'Protein 70% transparent; ligands and selected residues shown as opaque sticks'
            else:
                label = 'Graphics updated'
            self.dock.set_status(label + '. ' + RENDER_NOTE)
            self.refresh()
        except Exception as error:
            QtWidgets.QMessageBox.warning(self.window, 'Graphics presets', str(error))

    def refresh(self):
        state = self.dock.tools.graphics.state()
        for key, action in self.toggles.items():
            action.setChecked(state[key])
        for key, choices in self.choices.items():
            for value, action in choices.items():
                action.setChecked(state[key] == value)

    def render_preview(self):
        try:
            width, height = self.window.cmd.get_viewport()
            scale = min(1, 900 / max(1, width))
            width, height = max(1, round(width * scale)), max(1, round(height * scale))
            self.dock.set_status('Ray preview requested. Rotate the molecule to return to the interactive view.')
            self.window.cmd.do('ray %d, %d, async=1' % (width, height))
        except Exception as error:
            QtWidgets.QMessageBox.warning(self.window, 'Graphics preview', str(error))
