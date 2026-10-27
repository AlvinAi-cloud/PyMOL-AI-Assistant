"""Real Qt → Rust → HTTP roundtrip, using a localhost-only synthetic provider."""
import os
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pymol.Qt import QtCore
from pymol_ai_assistant.bridge import AiBridge
from pymol_ai_assistant.tools import parse_reply, response_text


class BridgeTest(unittest.TestCase):
    def test_model_discovery_inference_and_restore_without_real_account(self):
        requests = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def answer(self, body):
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            def do_GET(self):
                self.answer({"data": [{"id": "synthetic-model"}]})
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                reply = json.dumps({"message": "A local test proposal.", "actions": [{"operation": "color", "selection": "all", "color": "marine"}]})
                self.answer({"choices": [{"finish_reason": "stop", "message": {"content": reply}}]})
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        application = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
        helper = Path(__file__).resolve().parents[1] / ("ai/pymol-ai-assistant.exe" if os.name == "nt" else "ai/pymol-ai-assistant")
        with tempfile.TemporaryDirectory() as directory:
            bridge = AiBridge(executable=helper, profile=Path(directory))
            loop = QtCore.QEventLoop()
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            bridge.ready.connect(loop.quit)
            bridge.start()
            timer.start(5000)
            loop.exec()
            self.assertEqual(bridge.process.state(), QtCore.QProcess.Running)
            def request(action, **arguments):
                responses = []
                wait = QtCore.QEventLoop()
                timeout = QtCore.QTimer()
                timeout.setSingleShot(True)
                timeout.timeout.connect(wait.quit)
                def result(value, error):
                    responses.append((value, error))
                    wait.quit()
                bridge.request(action, result, **arguments)
                timeout.start(7000)
                wait.exec()
                self.assertTrue(responses, "AI helper timed out")
                value, error = responses[0]
                self.assertIsNone(error)
                self.assertNotIn("synthetic-private-key", json.dumps(value))
                return value
            connection = {"provider": "compatible", "endpoint": "http://127.0.0.1:%d" % server.server_port, "apiKey": "synthetic-private-key"}
            models = request("models", connection=connection)
            self.assertEqual(models["models"][0]["id"], "synthetic-model")
            request("connect", connection=connection, model="synthetic-model", remember=True)
            envelope = request("request", model="synthetic-model", system="Synthetic unit test.", prompt="No user data is included.")
            message, actions = parse_reply(response_text(envelope))
            self.assertEqual(actions[0]["operation"], "color")
            self.assertTrue(message)
            bridge.shutdown()
            bridge = AiBridge(executable=helper, profile=Path(directory))
            loop = QtCore.QEventLoop()
            bridge.ready.connect(loop.quit)
            QtCore.QTimer.singleShot(5000, loop.quit)
            bridge.start()
            loop.exec()
            restored = request("restore")
            self.assertEqual(restored["connection"]["model"], "synthetic-model")
            request("forget")
            bridge.shutdown()
            self.assertIn("No user data", requests[0]["messages"][1]["content"])
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    unittest.main()
