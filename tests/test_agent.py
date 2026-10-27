"""Automatic real AI-helper/native-command feedback loop with a local mock model."""
import os
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymol2
from pymol.Qt import QtCore

from pymol_ai_assistant.agent import AssistantAgent
from pymol_ai_assistant.bridge import AiBridge
from pymol_ai_assistant.tools import MolecularTools


class AgentTest(unittest.TestCase):
    def test_executes_continues_corrects_errors_and_restores_without_manual_review(self):
        actions = [
            [{"operation": "command", "command": "fragment gly, ai_demo"}],
            [{"operation": "command", "command": "color red, ai_demo; count_atoms ai_demo"}],
            [],
            [{"operation": "command", "command": "delete ai_demo"}],
            [],
            [{"operation": "restore_checkpoint"}],
            [],
            [{"operation": "command", "command": "color not_a_real_color, ai_demo"}],
            [{"operation": "command", "command": "color cyan, ai_demo"}],
            [],
        ]
        prompts = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                prompts.append(json.loads(request["messages"][1]["content"]))
                current = actions[len(prompts) - 1] if len(prompts) <= len(actions) else []
                reply = json.dumps({"message": "Working." if current else "Completed using the actual PyMOL results.", "actions": current})
                encoded = json.dumps({"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
        with tempfile.TemporaryDirectory() as directory, pymol2.PyMOL() as engine:
            root = Path(directory)
            helper = Path(__file__).resolve().parents[1] / ("ai/pymol-ai-assistant.exe" if os.name == "nt" else "ai/pymol-ai-assistant")
            bridge = AiBridge(executable=helper, profile=root / "ai")
            loop = QtCore.QEventLoop()
            bridge.ready.connect(loop.quit)
            QtCore.QTimer.singleShot(5000, loop.quit)
            bridge.start()
            loop.exec()
            configured = []
            bridge.request("connect", lambda value, error: (configured.append(error), loop.quit()),
                           connection={"provider": "compatible", "endpoint": "http://127.0.0.1:%d" % server.server_port, "apiKey": ""},
                           model="synthetic-model", remember=False)
            QtCore.QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertEqual(configured, [None])
            history = []
            tools = MolecularTools(engine.cmd, root / "scene")
            agent = AssistantAgent(bridge, tools, lambda: history)
            agent.message.connect(lambda role, text: history.append({"role": role, "text": text}))
            def turn(text):
                history.append({"role": "You", "text": text})
                wait = QtCore.QEventLoop()
                timeout = QtCore.QTimer()
                timeout.setSingleShot(True)
                timeout.timeout.connect(wait.quit)
                agent.finished.connect(wait.quit)
                agent.start("synthetic-model")
                timeout.start(12000)
                wait.exec()
                agent.finished.disconnect(wait.quit)
                self.assertFalse(agent.active, "Agent did not finish")
            turn("Create a glycine and color it red.")
            self.assertEqual(engine.cmd.count_atoms("ai_demo"), 7)
            self.assertEqual(len(list((root / "scene/checkpoints").glob("*.pse"))), 1)
            self.assertTrue(prompts[1]["toolResults"][0]["ok"])
            self.assertEqual(prompts[2]["scene"]["objects"][0]["atoms"], 7)
            turn("Delete the glycine.")
            self.assertEqual(engine.cmd.count_atoms("all"), 0)
            turn("Undo your last change.")
            self.assertEqual(engine.cmd.count_atoms("ai_demo"), 7)
            turn("Make the glycine cyan.")
            colors = []
            engine.cmd.iterate("ai_demo", "colors.append(color)", space={"colors": colors})
            self.assertEqual(set(colors), {engine.cmd.get_color_index("cyan")})
            self.assertFalse(prompts[8]["toolResults"][0]["ok"])
            self.assertIn('"sceneRestored": true', prompts[8]["toolResults"][0]["execution"])
            self.assertEqual(len(prompts), 10)
            bridge.shutdown()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    unittest.main()
