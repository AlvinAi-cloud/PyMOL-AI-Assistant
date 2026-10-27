"""Docked Qt assistant and account controls for PyMOL's existing desktop UI."""
import html
import json
import os
import sys
from pathlib import Path

from pymol.Qt import QtCore, QtGui, QtWidgets

from . import APP_NAME, __version__
from .bridge import AiBridge
from .config import profile_dir, write_json, resources_dir
from .tools import MolecularTools
from .agent import AssistantAgent

ASSISTANT_PANEL_WIDTH = 238  # 30% narrower than the original 340-pixel panel.

ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "compatible": "http://127.0.0.1:11434/v1",
}


def button(text, callback):
    widget = QtWidgets.QPushButton(text)
    widget.clicked.connect(callback)
    return widget


class AccountsDialog(QtWidgets.QDialog):
    def __init__(self, owner, refresh=True):
        super().__init__(owner)
        self.owner = owner
        self.bridge = owner.bridge
        self.setWindowTitle("Accounts and Models — " + APP_NAME)
        self.resize(610, 540)
        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)
        api = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(api)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.provider = QtWidgets.QComboBox()
        for label, key in [("OpenAI API", "openai"), ("Anthropic / Claude", "anthropic"), ("Google Gemini", "gemini"), ("Compatible / local API", "compatible")]:
            self.provider.addItem(label, key)
        self.endpoint = QtWidgets.QLineEdit()
        self.key = QtWidgets.QLineEdit()
        self.key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.key.setPlaceholderText("Your API key; leave blank to keep the active connection")
        self.remember = QtWidgets.QCheckBox("Remember this API connection on this computer")
        self.remember.setChecked(True)
        form.addRow("Provider", self.provider)
        form.addRow("API base URL", self.endpoint)
        form.addRow("API key", self.key)
        form.addRow(self.remember)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(button("Refresh models", self.api_models))
        row.addWidget(button("Save and connect", self.connect_api))
        row.addWidget(button("Forget saved connection", self.forget_api))
        form.addRow(row)
        note = QtWidgets.QLabel("Connections are stored only in this app’s private configuration folder. API usage is billed by your provider. Local models can use a localhost endpoint.")
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(api, "API / local models")

        chat = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(chat)
        text = QtWidgets.QLabel("Connect your own eligible ChatGPT account in the system browser. This package has not been validated against a live account. Other apps’ accounts and tokens are never imported.")
        text.setWordWrap(True)
        chat_layout.addWidget(text)
        chat_layout.addWidget(button("Continue with ChatGPT", self.sign_in))
        self.accounts = QtWidgets.QComboBox()
        chat_layout.addWidget(self.accounts)
        actions = QtWidgets.QHBoxLayout()
        for label, action in [("Use saved account", "activate"), ("Sign in again", "sign_in"), ("Sign out", "sign_out")]:
            actions.addWidget(button(label, lambda _checked=False, action=action: self.account_action(action)))
        chat_layout.addLayout(actions)
        chat_layout.addWidget(button("Refresh account models", self.account_models))
        chat_layout.addWidget(button("Cancel sign-in", lambda: self.bridge.request("cancel_login", self.notice)))
        chat_layout.addStretch()
        tabs.addTab(chat, "ChatGPT account")

        model_row = QtWidgets.QFormLayout()
        model_row.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.model = QtWidgets.QComboBox()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.model.setCurrentText(owner.model)
        self.model.setMinimumContentsLength(25)
        model_row.addRow("Model ID", self.model)
        layout.addLayout(model_row)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(button("Use selected model", self.set_model))
        controls.addWidget(button("Test connection", self.test))
        controls.addWidget(button("Disconnect for now", self.disconnect))
        layout.addLayout(controls)
        self.status = QtWidgets.QLabel("Model discovery sends no molecular data. Test connection sends a small request and may use provider quota.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(button("Close", self.close))
        self.provider.currentIndexChanged.connect(self.provider_changed)
        self.provider_changed()
        if owner.connection and owner.connection.get("provider") in ENDPOINTS:
            self.provider.setCurrentIndex(self.provider.findData(owner.connection["provider"]))
            self.endpoint.setText(owner.connection.get("endpoint", self.endpoint.text()))
        if refresh:
            self.bridge.request("status", self.account_status)

    def provider_changed(self, *_args):
        key = self.provider.currentData()
        self.endpoint.setText(ENDPOINTS[key])
        self.endpoint.setReadOnly(key != "compatible")

    def connection(self):
        return {"provider": self.provider.currentData(), "endpoint": self.endpoint.text().strip(), "apiKey": self.key.text().strip()}

    def notice(self, value, error):
        self.status.setText(error or (value or {}).get("notice", "Done."))

    def model_list(self, value, error):
        if error:
            self.status.setText(error)
            return
        current = self.model.currentText()
        self.model.clear()
        for item in (value or {}).get("models", []):
            identifier = item.get("id", item.get("slug", ""))
            if identifier:
                self.model.addItem(identifier)
        if current:
            self.model.setCurrentText(current)
        self.status.setText("Models refreshed. Choose a model ID, then use it.")

    def using_saved(self):
        current = self.owner.connection or {}
        return not self.key.text() and current.get("provider") == self.provider.currentData() and current.get("endpoint") == self.endpoint.text().strip()

    def api_models(self):
        self.status.setText("Fetching available models…")
        arguments = {} if self.using_saved() else {"connection": self.connection()}
        self.bridge.request("models", self.model_list, **arguments)

    def connect_api(self):
        if not self.model.currentText().strip():
            self.status.setText("Choose or enter a model ID first.")
            return
        if self.using_saved():
            self.set_model()
            return
        self.status.setText("Saving this app’s connection…")
        self.bridge.request("connect", self.api_connected, connection=self.connection(), model=self.model.currentText().strip(), remember=self.remember.isChecked())

    def api_connected(self, value, error):
        if error:
            self.status.setText(error)
            return
        self.key.clear()
        self.owner.restored(value, None)
        self.status.setText("Connected. Use Test connection to verify provider access.")

    def set_model(self):
        selected = self.model.currentText().strip()
        def done(value, error):
            if not error:
                self.owner.model = selected
                self.owner.update_status()
            self.notice(value, error)
        self.bridge.request("set_model", done, model=selected)

    def test(self):
        self.status.setText("Testing connection…")
        self.bridge.request("test", self.notice, model=self.model.currentText().strip())

    def forget_api(self):
        def done(value, error):
            self.notice(value, error)
            if not error:
                self.key.clear()
                self.owner.connection = None
                self.owner.update_status()
        self.bridge.request("forget", done)

    def disconnect(self):
        def done(value, error):
            self.notice(value, error)
            if not error:
                self.owner.connection = None
                self.owner.update_status()
        self.bridge.request("disconnect", done)

    def account_status(self, value, error):
        if error:
            self.status.setText(error)
            return
        status = (value or {}).get("chatgpt", {})
        self.accounts.clear()
        for account in status.get("accounts", []):
            self.accounts.addItem(account.get("label") or account.get("email") or "Saved account", account["id"])
        active = status.get("activeId")
        if active:
            self.accounts.setCurrentIndex(self.accounts.findData(active))
            self.owner.connection = {"provider": "chatgpt"}
            self.owner.update_status()
        self.status.setText(status.get("notice") or "Account status updated.")

    def sign_in(self):
        self.status.setText("Complete sign-in and consent in the system browser…")
        self.bridge.request("sign_in", self.account_status)

    def account_action(self, action):
        identifier = self.accounts.currentData()
        if not identifier:
            self.status.setText("Select a saved account, or continue with ChatGPT to add one.")
            return
        self.status.setText("Updating account…")
        def done(value, error):
            if action == "sign_out" and not error:
                self.owner.connection = None
                self.owner.update_status()
            self.account_status(value, error)
        self.bridge.request(action, done, registrationId=identifier)

    def account_models(self):
        identifier = self.accounts.currentData()
        if not identifier:
            self.status.setText("Sign in or select an account first.")
            return
        self.bridge.request("account_models", self.model_list, registrationId=identifier)


class AssistantDock(QtWidgets.QDockWidget):
    def __init__(self, window):
        super().__init__("AI Assistant", window)
        self.setObjectName("PyMOL_AI_Assistant")
        self.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.setMinimumWidth(ASSISTANT_PANEL_WIDTH)
        from .vision import capture_view
        self.tools = MolecularTools(window.cmd, capture=lambda target: capture_view(window, target))
        self.cmd = window.cmd
        self.connection = None
        self.model = ""
        self.history = []
        self.accounts_dialog = None
        self.bridge = AiBridge(self)
        self.agent = AssistantAgent(self.bridge, self.tools, lambda: self.history, self)
        container = QtWidgets.QWidget()
        self.setWidget(container)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        row = QtWidgets.QHBoxLayout()
        self.accounts_button = button("Accounts…", self.accounts)
        self.accounts_button.setToolTip("Accounts and Models")
        row.addWidget(self.accounts_button)
        row.addWidget(button("Example", self.example))
        layout.addLayout(row)
        self.chat = QtWidgets.QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setMinimumHeight(180)
        layout.addWidget(self.chat, 1)
        self.input = QtWidgets.QPlainTextEdit()
        self.input.setPlaceholderText("Ask about the current structure, or describe a view to prepare…")
        self.input.setMinimumHeight(100)
        self.input.setMaximumHeight(150)
        layout.addWidget(self.input)
        controls = QtWidgets.QHBoxLayout()
        self.send_button = button("Send", self.send)
        self.cancel_button = button("Cancel", self.agent.cancel)
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.send_button)
        controls.addWidget(self.cancel_button)
        self.clear_button = button("Clear", self.clear)
        self.clear_button.setToolTip("Clear conversation")
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)
        self.activity = QtWidgets.QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setPlaceholderText("PyMOL commands and results appear here as the AI works.")
        self.activity.setMinimumHeight(54)
        self.activity.setMaximumHeight(85)
        layout.addWidget(self.activity)
        self.setStyleSheet("QDockWidget { color: #1c2d3b; } QDockWidget QWidget { font-size: 12px; } QTextBrowser, QPlainTextEdit { border: 1px solid #bbc8d2; border-radius: 5px; padding: 6px; } QPushButton { padding: 5px 8px; }")
        self.bridge.ready.connect(self.restore)
        self.bridge.unavailable.connect(self.set_status)
        self.agent.message.connect(self.append)
        self.agent.status.connect(self.set_status)
        self.agent.activity.connect(self.set_activity)
        self.agent.busy_changed.connect(self.set_busy)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.bridge.shutdown)
        self.load_history()
        self.render()
        self.bridge.start()

    def restore(self):
        self.bridge.request("restore", self.restored)

    def restored(self, value, error):
        if error:
            self.set_status(error)
            return
        if (value or {}).get("connection"):
            self.connection = value["connection"]
            self.model = self.connection.get("model", self.model)
        elif (value or {}).get("chatgpt", {}).get("activeId"):
            self.connection = {"provider": "chatgpt"}
            self.bridge.request("status", self.restore_model)
        self.update_status()

    def restore_model(self, value, error):
        if not error:
            self.model = (value or {}).get("model", self.model)
            self.update_status()

    def update_status(self):
        if self.connection:
            self.set_status("Connected: " + self.connection.get("provider", "AI") + (" · " + self.model if self.model else " · choose a model"))
        else:
            self.set_status("Connect AI in Accounts.")

    def accounts(self):
        self.accounts_dialog = AccountsDialog(self)
        self.accounts_dialog.exec()

    def set_status(self, text):
        self._activity_status = text
        self.refresh_activity()

    def set_activity(self, text):
        self._activity_trace = text
        self.refresh_activity()

    def refresh_activity(self):
        self.activity.setPlainText(getattr(self, "_activity_status", "") + "\n" + getattr(self, "_activity_trace", ""))

    def load_history(self):
        path = profile_dir() / "conversation.json"
        try:
            if path.is_file() and path.stat().st_size < 1_000_000:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.history = [row for row in data[-60:] if isinstance(row, dict) and row.get("role") in {"You", "Assistant", "Local tools"} and isinstance(row.get("text"), str)]
        except (OSError, ValueError):
            pass

    def render(self):
        if not self.history:
            self.chat.setHtml("<p><b>Work with your molecular scene</b></p><p>Open a structure with File → Open, or load the bundled example using Example.</p><p>Describe a task. The AI runs PyMOL commands, reads their results, and continues automatically.</p>")
            return
        self.chat.setHtml("".join("<p><b>" + html.escape(row["role"]) + "</b><br>" + html.escape(row["text"]).replace("\n", "<br>") + "</p>" for row in self.history))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def append(self, role, text):
        self.history.append({"role": role, "text": str(text)[:12_000]})
        self.history = self.history[-60:]
        write_json(profile_dir() / "conversation.json", self.history)
        self.render()

    def clear(self):
        self.history = []
        self._activity_trace = ""
        self.activity.clear()
        write_json(profile_dir() / "conversation.json", [])
        self.render()

    def send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if not self.connection or not self.model:
            self.set_status("Open Accounts and Models to connect and choose a model first.")
            return
        if len(text) > 12_000:
            self.set_status("Please shorten the message to 12,000 characters.")
            return
        self.append("You", text)
        self.input.clear()
        self._activity_trace = ""
        self.activity.clear()
        self.agent.start(self.model)

    def set_busy(self, busy):
        self.send_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.clear_button.setEnabled(not busy)
        self.accounts_button.setEnabled(not busy)

    def example(self):
        name = "example_1hpv"
        if name in self.cmd.get_names("objects"):
            self.cmd.zoom(name)
            return
        path = Path(os.environ["PYMOL_DATA"]) / "tut/1hpv.pdb"
        self.cmd.load(str(path), name)
        self.cmd.hide("everything", name)
        self.cmd.show("cartoon", name)
        self.cmd.color("marine", name)
        self.cmd.show("sticks", name + " and organic")
        self.cmd.util.cbag(name + " and organic")
        self.cmd.bg_color("white")
        self.cmd.orient(name)
        self.set_status("Loaded the bundled PyMOL tutorial structure, 1HPV.")


def install(window):
    dock = AssistantDock(window)
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    window.resize(1320, 850)
    window.resizeDocks([dock], [ASSISTANT_PANEL_WIDTH], QtCore.Qt.Horizontal)
    window.setWindowTitle(APP_NAME + " — Open-Source PyMOL " + window.cmd.get_version()[0])
    application = QtWidgets.QApplication.instance()
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    icon_path = resources_dir() / ("icon.icns" if getattr(sys, "frozen", False) and sys.platform == "darwin" else "icons/PyMOL.png")
    if not icon_path.exists():
        icon_path = resources_dir() / "icons/PyMOL.icns"
    icon = QtGui.QIcon(str(icon_path))
    if not icon.isNull():
        application.setWindowIcon(icon)
        window.setWindowIcon(icon)
    menu = window.menuBar().addMenu("AI Assistant")
    menu.addAction(dock.toggleViewAction())
    menu.addAction("Accounts and Models…", dock.accounts)
    from .associations import show_file_types
    menu.addAction("File Types…", lambda: show_file_types(window))
    menu.addSeparator()
    menu.addAction("Load bundled example", dock.example)
    menu.addAction("About this standalone package…", lambda: QtWidgets.QMessageBox.about(window, APP_NAME,
        APP_NAME + " " + __version__ + "\n\nUnofficial standalone package based on official Open-Source PyMOL.\nPyMOL is a trademark of Schrödinger, LLC. This package is independently prepared and is not endorsed by Schrödinger.\n\nAI connection components adapted from RDataCraft and PlasmidCraft.\nApplication integration: GPL-3.0-or-later. See bundled licenses and source.\n\nLive provider/account access is not verified by the offline tests."))
    window.ai_assistant = dock
    return dock
