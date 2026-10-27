"""Automatic assistant → PyMOL → result → assistant loop."""
import json
import uuid

from pymol.Qt import QtCore

from .commands import CommandCancelled
from .tools import SYSTEM_PROMPT, parse_reply, response_text


def execution_text(execution):
    lines = []
    for item in execution.get("results", []):
        if isinstance(item, dict):
            lines.append("PyMOL> " + item.get("command", ""))
            if item.get("output"):
                lines.append(item["output"])
            if item.get("result") is not None:
                lines.append("Result: " + str(item["result"]))
        else:
            lines.append(str(item))
    if execution.get("sceneRestored"):
        lines.append("Restored the automatic scene checkpoint.")
    return "\n".join(lines) or "Molecular actions completed."


class ToolWorker(QtCore.QObject):
    # Like the ChatMol interaction design, PyMOL operations stay on Qt's main
    # thread; the native AI service handles inference without blocking the GUI.
    result_ready = QtCore.Signal(object)
    finished = QtCore.Signal()

    def __init__(self, tools, actions, parent):
        super().__init__(parent)
        self.tools, self.actions = tools, actions
        self.running = False

    def isRunning(self):
        return self.running

    def start(self):
        self.running = True
        QtCore.QTimer.singleShot(0, self.run)

    def run(self):
        try:
            outputs = self.tools.apply(self.actions, grouped=True)
            result = {"ok": True, "outputs": outputs, "execution": self.tools.last_execution}
        except Exception as error:
            result = {"ok": False, "error": str(error), "cancelled": isinstance(error, CommandCancelled), "execution": self.tools.last_execution}
        self.running = False
        self.result_ready.emit(result)
        self.finished.emit()


class AssistantAgent(QtCore.QObject):
    message = QtCore.Signal(str, str)
    status = QtCore.Signal(str)
    activity = QtCore.Signal(str)
    busy_changed = QtCore.Signal(bool)
    finished = QtCore.Signal()
    MAX_STEPS = 8

    def __init__(self, bridge, tools, history, parent=None):
        super().__init__(parent)
        self.bridge, self.tools, self.history = bridge, tools, history
        self.active = False
        self.worker = None
        self.token = None

    def start(self, model):
        if self.active:
            return
        self.model = model
        self.token = uuid.uuid4().hex
        self.step = 0
        self.results = []
        self.stopped = False
        self.active = True
        self.tools.begin_turn()
        self.busy_changed.emit(True)
        self.request_next()

    def cancel(self):
        if not self.active:
            return
        self.stopped = True
        self.tools.cancelled.set()
        self.status.emit("Stopping after the current command…")
        self.bridge.request("cancel", lambda *_args: None)

    def request_next(self):
        if self.stopped:
            self.finish("Stopped. Completed changes remain; you can ask the assistant to restore its checkpoint.")
            return
        if self.step >= self.MAX_STEPS:
            self.finish("Stopped after eight assistant steps. Ask to continue if more work is needed.")
            return
        self.step += 1
        self.status.emit("AI working · step %d/%d" % (self.step, self.MAX_STEPS))
        try:
            context = self.tools.context()
            prompt = json.dumps({"scene": context, "conversation": self.history()[-12:], "toolResults": self.results[-6:]}, ensure_ascii=False)
            token = self.token
            images, self.tools.images = self.tools.images, []
            self.bridge.request("request", lambda value, error: self.reply(value, error, token), model=self.model, system=SYSTEM_PROMPT, prompt=prompt, images=images)
        except Exception as error:
            self.finish("Could not read the current scene: " + str(error))

    def reply(self, value, error, token):
        if token != self.token or not self.active:
            return
        if self.stopped:
            self.finish("Stopped. Completed changes remain; ask to restore the checkpoint to reverse scene changes.")
            return
        if error:
            self.finish(error)
            return
        try:
            text = response_text(value)
            if not text:
                raise ValueError("The provider returned no text.")
            message, actions = parse_reply(text)
        except Exception as error:
            self.results.append({"ok": False, "error": "Invalid assistant response: " + str(error)})
            self.status.emit("Requesting a corrected assistant response…")
            QtCore.QTimer.singleShot(0, self.request_next)
            return
        if message:
            self.message.emit("Assistant", message)
        if not actions:
            self.finish()
            return
        self.activity.emit("\n".join(action.get("command", json.dumps(action)) for action in actions))
        self.status.emit("Executing PyMOL commands…")
        worker = ToolWorker(self.tools, actions, self)
        self.worker = worker
        worker.result_ready.connect(self.tool_result)
        def cleanup():
            if self.worker is worker:
                self.worker = None
            worker.deleteLater()
        worker.finished.connect(cleanup)
        worker.start()

    def tool_result(self, result):
        execution = result.get("execution", {})
        trace = execution_text(execution)
        if result.get("error"):
            trace += "\n" + result["error"]
        self.activity.emit(trace)
        self.message.emit("Local tools", trace[:12_000])
        self.results.append({"ok": result["ok"], "error": result.get("error"), "execution": json.dumps(execution, ensure_ascii=False)[:80_000]})
        if self.stopped or result.get("cancelled"):
            self.finish("Stopped. Completed changes remain; ask the assistant to restore its checkpoint if needed.")
        else:
            QtCore.QTimer.singleShot(0, self.request_next)

    def finish(self, notice=None):
        if notice:
            self.message.emit("Assistant", notice)
            self.status.emit(notice)
        self.active = False
        self.busy_changed.emit(False)
        if not notice:
            self.status.emit("Ready · " + self.model)
        self.finished.emit()
