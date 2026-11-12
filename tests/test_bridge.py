"""Integration test of `hangar bridge` against a scripted OpenAI-compatible server (no network, no API key)."""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FakeLLM:
    """Each request pops the next scripted reply: {"text": ...} or {"tool": name, "args": {...}} (+ "delay": seconds)."""

    def __init__(self):
        self.script: list[dict] = []
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append({"body": body, "auth": self.headers.get("Authorization")})
                step = outer.script.pop(0) if outer.script else {"text": "(script exhausted)"}
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()

                def sse(obj):
                    self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
                    self.wfile.flush()
                try:
                    if step.get("thinking"):
                        sse({"choices": [{"delta": {"reasoning": step["thinking"]}}]})
                    if "tool" in step:
                        sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"call_{len(outer.requests)}", "function": {
                            "name": step["tool"], "arguments": json.dumps(step["args"])}}]}}]})
                        finish = "tool_calls"
                    else:
                        for word in step["text"].split(" "):
                            if step.get("delay"):
                                time.sleep(step["delay"])
                            sse({"choices": [{"delta": {"content": word + " "}}]})
                        finish = "stop"
                    sse({"choices": [{"delta": {}, "finish_reason": finish}], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()


class Bridge:
    def __init__(self, home: Path, start: dict):
        env = {**os.environ, "HANGAR_HOME": str(home), "HANGAR_BRIDGE_KEY": "test-key", "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
        self.p = subprocess.Popen([sys.executable, "-u", "-m", "hangar", "bridge"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env, cwd=str(home))
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.all: list[dict] = []
        threading.Thread(target=self._read, daemon=True).start()
        self.send({"type": "start", **start})

    def _read(self):
        for line in self.p.stdout:
            try:
                self.events.put(json.loads(line.decode("utf-8")))
            except ValueError:
                self.events.put({"type": "GARBAGE", "raw": line[:200]})

    def send(self, obj: dict):
        self.p.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def until(self, kind: str, timeout: float = 30) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            try:
                ev = self.events.get(timeout=0.2)
            except queue.Empty:
                if self.p.poll() is not None:
                    raise AssertionError(f"bridge exited: {self.p.stderr.read().decode('utf-8', 'replace')[-600:]}")
                continue
            self.all.append(ev)
            if ev.get("type") == kind:
                return ev
        raise AssertionError(f"no '{kind}' event; saw {[e.get('type') for e in self.all][-15:]}")

    def close(self):
        if self.p.poll() is None:
            try:
                self.send({"type": "close"})
                self.p.wait(timeout=15)
            except Exception:
                self.p.kill()
        for stream in (self.p.stdin, self.p.stdout, self.p.stderr):
            try:
                stream.close()
            except OSError:
                pass


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="hangar_bridge_home_")).resolve()
        self.cwd = Path(tempfile.mkdtemp(prefix="hangar_bridge_cwd_")).resolve()
        self.llm = FakeLLM()
        self.addCleanup(self.llm.close)

    def start(self, **over) -> Bridge:
        # tier "strong": the scripted model gets no verification nudges, so each turn consumes exactly its script
        b = Bridge(self.home, {"cwd": str(self.cwd), "model": "fake/model", "base_url": self.llm.url, "permission": "ask",
                               "tier": "strong", **over})
        self.addCleanup(b.close)
        return b

    def test_permission_roundtrip_second_turn_and_resume(self):
        self.llm.script = [{"thinking": "preciso criar o arquivo", "tool": "write", "args": {"path": "nota.txt", "content": "ola"}},
                           {"text": "Arquivo criado."}, {"text": "Sim, lembro: nota.txt."}, {"text": "Retomado."}]
        b = self.start(system_append="REGRA DO APP: responda em portugues.")
        ready = b.until("ready")
        self.assertFalse(ready["resumed"])
        b.send({"type": "user", "text": "crie nota.txt com ola"})
        perm = b.until("permission")
        self.assertEqual((perm["tool"], perm["args"]["path"].endswith("nota.txt"), perm["can_always"]), ("write", True, True))
        self.assertFalse((self.cwd / "nota.txt").exists())                       # nothing happens before the answer
        b.send({"type": "permission_response", "qid": perm["qid"], "decision": "allow"})
        end = b.until("turn_end")
        self.assertEqual(end["status"], "success")
        self.assertEqual((self.cwd / "nota.txt").read_text(), "ola")
        self.assertAlmostEqual(end["cost"], 0.002)
        kinds = [e["type"] for e in b.all]
        for expected in ("thinking", "tool_start", "tool_end", "assistant", "llm_end"):
            self.assertIn(expected, kinds)
        self.assertNotIn("GARBAGE", kinds)                                       # stdout carries the protocol only
        self.assertEqual(self.llm.requests[0]["auth"], "Bearer test-key")       # the key came from the environment
        self.assertIn("REGRA DO APP", self.llm.requests[0]["body"]["messages"][0]["content"])
        b.send({"type": "user", "text": "lembra do arquivo?"})
        self.assertEqual(b.until("turn_end")["status"], "success")
        roles = [m["role"] for m in self.llm.requests[-1]["body"]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant", "user"])    # same conversation
        b.close()
        again = self.start(resume=ready["session"])
        self.assertTrue(again.until("ready")["resumed"])
        again.send({"type": "user", "text": "continue"})
        again.until("turn_end")
        self.assertGreaterEqual(len(self.llm.requests[-1]["body"]["messages"]), 8)              # history survived the restart

    def test_deny_and_allow_always(self):
        self.llm.script = [{"tool": "shell", "args": {"command": "echo um"}}, {"tool": "shell", "args": {"command": "echo dois"}},
                           {"tool": "shell", "args": {"command": "echo tres"}}, {"text": "fim"}]
        b = self.start()
        b.until("ready")
        b.send({"type": "user", "text": "rode"})
        p1 = b.until("permission")
        b.send({"type": "permission_response", "qid": p1["qid"], "decision": "deny", "message": "agora nao"})
        self.assertIn("agora nao", b.until("tool_end")["preview"])               # the model is told why
        p2 = b.until("permission")
        b.send({"type": "permission_response", "qid": p2["qid"], "decision": "allow_always"})
        self.assertEqual(b.until("turn_end")["status"], "success")              # third command ran without asking
        self.assertEqual(len([e for e in b.all if e["type"] == "permission"]), 2)

    def test_modes_edits_auto_and_plan(self):
        self.llm.script = [{"tool": "write", "args": {"path": "a.txt", "content": "x"}}, {"text": "ok"},
                           {"tool": "write", "args": {"path": "b.txt", "content": "y"}}, {"text": "plano"}]
        b = self.start(permission="edits")
        b.until("ready")
        b.send({"type": "user", "text": "escreva"})
        b.until("turn_end")
        self.assertTrue((self.cwd / "a.txt").exists())                           # edits inside the folder need no approval
        self.assertFalse([e for e in b.all if e["type"] == "permission"])
        b.send({"type": "set_options", "permission": "readonly"})
        b.until("options")
        b.send({"type": "user", "text": "escreva outro"})
        b.until("turn_end")
        self.assertFalse((self.cwd / "b.txt").exists())                          # plan mode: nothing is written
        self.assertIn("Plan mode", self.llm.requests[-1]["body"]["messages"][0]["content"])

    def test_interrupt_stops_the_stream(self):
        self.llm.script = [{"text": " ".join(["palavra"] * 200), "delay": 0.05}, {"text": "depois"}]
        b = self.start()
        b.until("ready")
        b.send({"type": "user", "text": "fale muito"})
        b.until("delta")
        t0 = time.time()
        b.send({"type": "interrupt"})
        self.assertEqual(b.until("turn_end")["status"], "interrupted")
        self.assertLess(time.time() - t0, 5)
        b.send({"type": "user", "text": "e agora?"})
        self.assertEqual(b.until("turn_end")["status"], "success")              # the conversation is still usable

    def test_question_goes_to_the_host(self):
        self.llm.script = [{"tool": "ask_user", "args": {"question": "Qual porta?", "options": ["80", "8080"]}}, {"text": "usarei 8080"}]
        b = self.start()
        b.until("ready")
        b.send({"type": "user", "text": "configure"})
        q = b.until("question")
        self.assertEqual((q["question"], q["options"]), ("Qual porta?", ["80", "8080"]))
        b.send({"type": "answer", "qid": q["qid"], "answer": "8080"})
        self.assertEqual(b.until("turn_end")["status"], "success")
        self.assertIn("8080", json.dumps(self.llm.requests[-1]["body"]["messages"]))

    def test_bad_start_is_reported(self):
        b = Bridge(self.home, {"cwd": str(self.cwd)})                            # no model
        self.addCleanup(b.close)
        self.assertIn("model", b.until("fatal")["message"])


if __name__ == "__main__":
    unittest.main()
