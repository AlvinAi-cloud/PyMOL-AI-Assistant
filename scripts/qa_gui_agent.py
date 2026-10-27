"""Run via PyMOL -r in an explicitly isolated test profile; no live AI account."""
import base64
import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pymol.Qt import QtCore, QtWidgets
from pmg_qt import pymol_qt_gui
from pymol_ai_assistant.config import profile_dir, write_json

OUTPUT = Path(os.environ["PYMOL_AI_QA_OUTPUT"]).resolve()
assert profile_dir() == OUTPUT / "profile", "An isolated QA profile is required"
OUTPUT.mkdir(parents=True, exist_ok=True)
requests = []
state = {"turn": 0}


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content = body["messages"][1]["content"]
        if isinstance(content, list):
            image = content[1]["image_url"]["url"]
            decoded = base64.b64decode(image.split(",", 1)[1])
            assert len(decoded) > 5000
            (OUTPUT / ("window-inspection.jpg" if len(requests) == 1 else "viewport-inspection.jpg")).write_bytes(decoded)
            content = content[0]["text"]
        elif len(requests) in {1, 2}:
            raise AssertionError("Inspection image did not reach provider")
        requests.append(json.loads(content))
        if len(requests) == 1:
            actions = [{"operation":"inspect_view","target":"window"}, {"operation":"get_sequence","selection":"example_1hpv and chain A"}]
            message = "I will inspect the window and read the loaded chain A sequence."
        elif len(requests) == 2:
            execution = json.loads(requests[-1]["toolResults"][-1]["execution"])
            fasta = execution["results"][1]["result"]["fasta"]
            assert fasta.startswith(">") and "PQITLW" in fasta
            actions = [{"operation":"inspect_view","target":"viewport"}]
            message = "Now I will examine the molecular viewport."
        elif len(requests) == 3:
            command = "color teal, example_1hpv; set cartoon_transparency, 0.15; count_atoms example_1hpv\npng %s, width=800, height=600, ray=1" % (OUTPUT / "command-export.png")
            actions = [{"operation": "command", "command": command}]
            message = "I will prepare the view and export it using PyMOL commands."
        elif len(requests) == 5:
            actions = [{"operation": "restore_checkpoint"}]
            message = "I will restore the scene from before my previous changes."
        else:
            actions = []
            message = "Completed using the actual command results."
        text = json.dumps({"message": message, "actions": actions})
        encoded = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()


def fail():
    write_json(OUTPUT / "result.json", {"ok": False, "error": traceback.format_exc()})
    pymol_qt_gui.window.close()


def colors(cmd):
    result = []
    cmd.iterate("example_1hpv", "result.append(color)", space={"result": result})
    return result


def finished():
    QtCore.QTimer.singleShot(300, inspect_turn)


def inspect_turn():
    try:
        window = pymol_qt_gui.window
        dock = window.ai_assistant
        if state["turn"] == 0:
            assert not dock.agent.active
            assert len(requests) == 4
            assert requests[1]["toolResults"][0]["ok"]
            assert window.cmd.count_atoms("example_1hpv") == 1631
            assert (OUTPUT / "command-export.png").stat().st_size > 5000
            assert colors(window.cmd) != state["colors"]
            assert dock.width() == 238
            assert not hasattr(dock, "include_sequence")
            assert not hasattr(dock, "status")
            labels = [b.text() for b in dock.findChildren(QtWidgets.QPushButton)]
            assert "Context…" not in labels and "Export PNG…" not in labels
            assert not hasattr(dock, "apply_button") and not hasattr(dock, "undo_button")
            assert dock.chat.geometry().bottom() < dock.input.geometry().top()
            from pymol_ai_assistant.vision import capture_view
            from pymol.Qt import QtGui
            captured, _ = capture_view(window, "window")
            QtGui.QImage.fromData(base64.b64decode(captured.split(",", 1)[1])).save(str(OUTPUT / "automatic-control.png"))
            QtWidgets.QApplication.instance().windowIcon().pixmap(256, 256).save(str(OUTPUT / "app-icon.png"))
            render_widget = QtWidgets.QWidget()
            window.render_dialog(render_widget)
            form = render_widget._pymol_render_form
            form.button_lock.setChecked(False)
            form.input_width.setValue(400)
            form.input_height.setValue(300)
            form.button_draw.click()
            assert form.stack.currentIndex() == 1
            form.button_back.click()
            form.button_ray.click()
            assert form.stack.currentIndex() == 1
            render_widget.grab().save(str(OUTPUT / "draw-ray-dialog.png"))
            render_widget.close()
            import PyQt5.uic
            assert callable(PyQt5.uic.loadUi)
            state["turn"] = 1
            dock.input.setPlainText("Undo your last changes.")
            dock.send()
        else:
            assert len(requests) == 6
            assert colors(window.cmd) == state["colors"]
            assert requests[5]["toolResults"][0]["ok"]
            write_json(OUTPUT / "result.json", {
                "ok": True, "modelCalls": len(requests), "automaticTurns": 2,
                "manualReview": False, "sceneRestoredByChat": True,
                "panelWidth": dock.width(), "applicationIcon": not QtWidgets.QApplication.instance().windowIcon().isNull(),
                "consoleFeedback": requests[3]["toolResults"][-1],
                "windowAndViewportImagesDelivered": True, "sequenceExtractedOnDemand": True,
                "drawAndRayButtons": True, "pyqtUiLoader": True,
                "renderer": list(dock.cmd.get_renderer()),
                "inputHeight": dock.input.height(), "conversationHeight": dock.chat.height(),
            })
            pymol_qt_gui.window.close()
    except Exception:
        fail()


def configured(value, error):
    try:
        assert not error, error
        dock = pymol_qt_gui.window.ai_assistant
        dock.restored(value, None)
        dock.example()
        state["colors"] = colors(dock.cmd)
        dock.agent.finished.connect(finished)
        dock.input.setPlainText("Prepare a teal view and export it to %s." % (OUTPUT / "command-export.png"))
        dock.send()
    except Exception:
        fail()


def ready():
    try:
        window = pymol_qt_gui.window
        if not hasattr(window, "ai_assistant") or window.ai_assistant.bridge.process.state() != QtCore.QProcess.Running:
            QtCore.QTimer.singleShot(250, ready)
            return
        window.ai_assistant.bridge.request("connect", configured,
            connection={"provider": "compatible", "endpoint": "http://127.0.0.1:%d" % server.server_port, "apiKey": ""},
            model="synthetic-model", remember=False)
    except Exception:
        fail()


def timeout():
    if not (OUTPUT / "result.json").exists():
        write_json(OUTPUT / "result.json", {"ok": False, "error": "GUI agent QA timed out", "requests": len(requests)})
        pymol_qt_gui.window.close()


QtCore.QTimer.singleShot(700, ready)
QtCore.QTimer.singleShot(45000, timeout)
