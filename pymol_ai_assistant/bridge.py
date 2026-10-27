"""Qt client for the RDataCraft/PlasmidCraft-derived private AI helper."""
import json
import uuid

from pymol.Qt import QtCore

from .config import helper_path, profile_dir


class AiBridge(QtCore.QObject):
    ready = QtCore.Signal()
    unavailable = QtCore.Signal(str)

    def __init__(self, parent=None, executable=None, profile=None):
        super().__init__(parent)
        self.callbacks = {}
        self.buffer = b""
        self.process = QtCore.QProcess(self)
        self.process.setProgram(str(executable or helper_path()))
        self.process.setArguments(["--profile", str(profile or (profile_dir() / "ai"))])
        self.process.started.connect(self.ready)
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(self.failed)
        self.process.finished.connect(self.finished)

    def start(self):
        self.process.start()

    def request(self, action, callback, **arguments):
        if self.process.state() != QtCore.QProcess.Running:
            callback(None, "The AI connection service is not running.")
            return
        identifier = uuid.uuid4().hex
        value = dict(arguments, id=identifier, action=action)
        encoded = (json.dumps(value, ensure_ascii=False) + "\n").encode()
        if len(encoded) > 1_900_000:
            callback(None, "The request is too large. Shorten the conversation or request a smaller molecular selection.")
            return
        self.callbacks[identifier] = callback
        if self.process.write(encoded) < 0:
            self.callbacks.pop(identifier, None)
            callback(None, "Could not write to the AI connection service.")

    def receive(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 2_000_000:
            self.process.kill()
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                envelope = json.loads(line)
                if not isinstance(envelope, dict):
                    raise ValueError("Invalid reply")
                callback = self.callbacks.pop(envelope.get("id"), None)
                if callback:
                    callback(envelope.get("value"), None if envelope.get("ok") else envelope.get("error", "AI request failed."))
            except (ValueError, TypeError):
                self.process.kill()
                return

    def failed(self, _error):
        self.unavailable.emit("The bundled AI service could not start. Molecular tools remain available.")

    def finished(self, *_args):
        callbacks, self.callbacks = self.callbacks, {}
        for callback in callbacks.values():
            callback(None, "The AI connection service stopped.")

    def shutdown(self):
        self.callbacks.clear()
        self.process.closeWriteChannel()
        # Preserve an in-flight rotating-token renewal before terminating the helper.
        if not self.process.waitForFinished(30_500):
            self.process.terminate()
            if not self.process.waitForFinished(500):
                self.process.kill()
                self.process.waitForFinished(500)

