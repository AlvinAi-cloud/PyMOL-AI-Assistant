"""Read-only local guides, shared by the assistant and graphics menus."""
from pymol.Qt import QtCore, QtWidgets

from . import APP_NAME
from .help_content import HELP_PAGES

TOPICS = {
    'assistant': [
        ('assistant_start', 'Getting started…', 'Read how to connect a provider, choose a model and send your first molecular visualization request.'),
        ('assistant_capabilities', 'AI tools and examples…', 'Learn how the assistant examines the window, reads sequences, runs PyMOL commands and restores scene checkpoints.'),
    ],
    'presets': [
        ('presets_guide', 'Presets and options…', 'Read the descriptions of all eight lighting presets, independent controls and optional polymer color palettes.'),
        ('rendering_guide', 'Draw, Ray and image export…', 'Learn when to use Draw or Ray, how to inspect rendered previews, and how to export white or transparent PNG images.'),
    ],
}
NAVIGATION_LABELS = {
    'assistant_start': 'Getting started',
    'assistant_capabilities': 'AI tools & recovery',
    'presets_guide': 'Presets & options',
    'rendering_guide': 'Draw/Ray & export',
}


class PackageHelpDialog(QtWidgets.QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName('package_help_dialog')
        self.setWindowTitle('Help — ' + APP_NAME)
        self.resize(800, 650)
        layout = QtWidgets.QVBoxLayout(self)
        columns = QtWidgets.QHBoxLayout()
        self.topics = QtWidgets.QListWidget()
        self.topics.setObjectName('package_help_topics')
        self.topics.setMaximumWidth(210)
        self.topics.setMinimumWidth(170)
        self.topics.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setObjectName('package_help_text')
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.setReadOnly(True)
        self.browser.document().setDefaultStyleSheet(
            'body { font-family: sans-serif; } h2 { margin-top: 6px; } '
            'h3 { margin-top: 20px; } p, li { line-height: 135%; }')
        columns.addWidget(self.topics)
        columns.addWidget(self.browser, 1)
        layout.addLayout(columns)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        for key, (title, _html) in HELP_PAGES.items():
            item = QtWidgets.QListWidgetItem(NAVIGATION_LABELS[key])
            item.setToolTip(title)
            item.setData(QtCore.Qt.UserRole, key)
            self.topics.addItem(item)
        self.topics.currentItemChanged.connect(self.display_topic)

    def display_topic(self, item, _previous=None):
        if item is not None:
            self.browser.setHtml(HELP_PAGES[item.data(QtCore.Qt.UserRole)][1])
            self.browser.verticalScrollBar().setValue(0)

    def select_topic(self, key):
        for index in range(self.topics.count()):
            item = self.topics.item(index)
            if item.data(QtCore.Qt.UserRole) == key:
                self.topics.setCurrentItem(item)
                self.display_topic(item)
                return
        raise ValueError('Unknown help topic: ' + key)


def show_help(window, topic):
    dialog = getattr(window, 'package_help_dialog', None)
    if dialog is None:
        dialog = window.package_help_dialog = PackageHelpDialog(window)
    dialog.select_topic(topic)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def install_help_menu(window, parent_menu, section):
    # Use the graphics menu's hover-help subclass when adding its submenu.
    menu = type(parent_menu)('Help', parent_menu)
    menu.setObjectName(section + '_help_menu')
    menu.setToolTipsVisible(True)
    action = parent_menu.addMenu(menu)
    tip = 'Open the offline guide for ' + ('AI setup, supported tools and example requests.' if section == 'assistant'
                                        else 'lighting presets, rendering options, palettes and Draw/Ray export.')
    for setter in [action.setToolTip, action.setStatusTip, action.setWhatsThis]:
        setter(tip)
    for topic, label, tip in TOPICS[section]:
        action = menu.addAction(label)
        action.setObjectName('help_' + topic)
        for setter in [action.setToolTip, action.setStatusTip, action.setWhatsThis]:
            setter(tip)
        action.triggered.connect(lambda _checked=False, topic=topic: show_help(window, topic))
    return menu
