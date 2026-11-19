"""The web app (`hangar ui`): its HTTP API against a scripted model, and the page itself in a headless browser
(chat, permission card, attachments, screen/microphone recording with fake devices, every side panel).
No network and no API key. The browser part is skipped when the machine has no Chrome/Edge."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import browser as B  # noqa: E402
from hangar import server  # noqa: E402
from tests.test_bridge import FakeLLM  # noqa: E402


class Client:
    def __init__(self, base: str, token: str):
        self.base, self.token = base, token

    def call(self, path: str, body=None, raw: bytes | None = None, token: str | None = None):
        headers = {"X-Hangar-Token": self.token if token is None else token}
        data = None
        if raw is not None:
            data = raw
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def json(self, path: str, body=None, **kw):
        code, data = self.call(path, body, **kw)
        return code, json.loads(data or b"{}")


class UiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = FakeLLM()
        cls.srv, cls.app = server.make_server(0, bridge_extra={"base_url": cls.llm.url, "tier": "strong", "model": "fake/model"})
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.c = Client(cls.base, cls.app.token)

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.llm.close()

    def work(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="hangar_ui_work_")).resolve()

    def events(self, sid: str) -> list[dict]:
        p = self.app.store.log_path(sid)
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []

    def until(self, sid: str, pred, timeout: float = 40) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            for ev in self.events(sid):
                if pred(ev):
                    return ev
            time.sleep(0.1)
        raise AssertionError(f"event not seen; log has {[e.get('type') for e in self.events(sid)][-12:]}")

    def offline_project(self) -> Path:
        """A work folder whose own config sends `hangar run` (a separate process) to the scripted model."""
        cwd = self.work()
        (cwd / "hangar.toml").write_text(
            'default_provider = "fake"\nmodel = "fake/model"\nlessons = false\n'
            f'[providers.fake]\nbase_url = "{self.llm.url}"\napi_key_env = ""\n'
            '[tiers]\n"fake/model" = "strong"\n', encoding="utf-8")
        return cwd

    def run_events(self, sid: str) -> list[dict]:
        p = server.SESSIONS / sid / "events.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []

    def until_run(self, sid: str, pred, timeout: float = 60) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            for ev in self.run_events(sid):
                if pred(ev):
                    return ev
            time.sleep(0.15)
        raise AssertionError(f"run event not seen; log has {[e.get('type') for e in self.run_events(sid)][-14:]}")

    def new(self, cwd: Path, **over) -> str:
        code, s = self.c.json("/api/sessions", {"cwd": str(cwd), **over})
        self.assertEqual(code, 200, s)
        self.assertEqual((s["model"], s["effort"]), ("auto", over.get("effort", "low")))      # the harness picks the models; its own default effort
        return s["id"]


class ApiTests(UiBase):
    def test_everything_needs_the_token_and_a_local_host(self):
        self.assertEqual(self.c.call("/api/state", token="")[0], 403)
        self.assertEqual(self.c.call("/api/state", token="errado")[0], 403)
        self.assertEqual(self.c.call("/api/sessions", {"cwd": "."}, token="x")[0], 403)
        code, page = self.c.call("/", token="")
        self.assertEqual(code, 200)
        self.assertIn(self.app.token.encode(), page)                             # the page itself carries the token
        req = urllib.request.Request(self.base + "/", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(e.exception.code, 403)                                  # DNS rebinding: not a local host name
        for path in ("/ui.js", "/ui.css", "/flow.js"):
            self.assertEqual(self.c.call(path, token="")[0], 200)

    def test_chat_turn_with_permission_then_second_turn(self):
        cwd = self.work()
        sid = self.new(cwd)
        self.llm.script = [{"thinking": "vou criar", "tool": "write", "args": {"path": "pagina.html", "content": "<h1>Oi</h1>"}},
                           {"text": "Pronto: pagina.html criado."}, {"text": "Sim, lembro."}]
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/send", {"text": "Crie uma landing page para o lançamento do produto"})[0], 200)
        perm = self.until(sid, lambda e: e["type"] == "permission")
        self.assertEqual(perm["tool"], "write")
        self.assertFalse((cwd / "pagina.html").exists())
        _, st = self.c.json("/api/state")
        row = next(s for s in st["sessions"] if s["id"] == sid)
        self.assertEqual((row["status"], row["busy"], row["title"]), ("waiting", True, "Crie uma landing page para o lançamento do produto"))
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/respond", {"qid": perm["qid"], "decision": "allow"})[0], 200)
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/respond", {"qid": perm["qid"], "decision": "allow"})[0], 409)   # only once
        end = self.until(sid, lambda e: e["type"] == "turn_end")
        self.assertEqual(end["status"], "success")
        self.assertEqual((cwd / "pagina.html").read_text(), "<h1>Oi</h1>")
        kinds = [e["type"] for e in self.events(sid)]
        for k in ("user", "thinking", "tool_start", "permission", "permission_result", "tool_end", "assistant", "turn_end"):
            self.assertIn(k, kinds)
        self.assertNotIn("ready", kinds)
        self.c.json(f"/api/sessions/{sid}/send", {"text": "lembra?"})
        self.until(sid, lambda e: e["type"] == "assistant" and e.get("text", "").startswith("Sim"))
        roles = [m["role"] for m in self.llm.requests[-1]["body"]["messages"]]
        self.assertEqual(roles.count("user"), 2)                                 # the same conversation
        _, st = self.c.json("/api/state")
        row = next(s for s in st["sessions"] if s["id"] == sid)
        self.assertTrue(row["hangarSessionId"])
        self.assertGreater(row["cost"], 0)
        # SSE replays the log (the token rides in the query: EventSource cannot set headers)
        req = urllib.request.Request(f"{self.base}/api/sessions/{sid}/events?token={self.app.token}")
        with urllib.request.urlopen(req, timeout=10) as r:
            first = r.readline().decode()
        self.assertTrue(first.startswith("data: ") and '"type": "user"' in first)
        _, hits = self.c.json("/api/search?q=landing")
        self.assertEqual([h["id"] for h in hits], [sid])

    def test_modes_question_interrupt_rename_archive_delete(self):
        cwd = self.work()
        sid = self.new(cwd, permission="edits")
        self.llm.script = [{"tool": "write", "args": {"path": "a.txt", "content": "x"}},
                           {"tool": "ask_user", "args": {"question": "Qual porta?", "options": ["80", "8080"]}}, {"text": "usarei 8080"}]
        self.c.json(f"/api/sessions/{sid}/send", {"text": "configure"})
        q = self.until(sid, lambda e: e["type"] == "question")
        self.assertTrue((cwd / "a.txt").exists())                                # "Aceitar edições": no card for the write
        self.assertFalse([e for e in self.events(sid) if e["type"] == "permission"])
        self.c.json(f"/api/sessions/{sid}/respond", {"qid": q["qid"], "answer": "8080"})
        self.until(sid, lambda e: e["type"] == "turn_end")
        self.assertIn("8080", json.dumps(self.llm.requests[-1]["body"]["messages"]))

        self.llm.script = [{"text": " ".join(["palavra"] * 300), "delay": 0.05}]
        self.c.json(f"/api/sessions/{sid}/send", {"text": "fale muito"})
        self.until(sid, lambda e: e["type"] == "delta" and "palavra" in e.get("text", ""))
        self.c.json(f"/api/sessions/{sid}/interrupt", {})
        n = len([e for e in self.events(sid) if e["type"] == "turn_end"])
        end = self.until(sid, lambda e: e["type"] == "turn_end" and e["status"] == "interrupted", 15)
        self.assertEqual((end["status"], n >= 1), ("interrupted", True))

        code, s = self.c.json(f"/api/sessions/{sid}/update", {"title": "Renomeada", "pinned": True, "permission": "readonly", "effort": "low", "workflows": True})
        self.assertEqual((s["title"], s["pinned"], s["permission"], s["effort"], s["workflows"]), ("Renomeada", True, "readonly", "low", True))
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/stop_agent", {"agent": "wf1"})[0], 200)     # one sub-agent, not the turn
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/stop_agent", {"agent": "../x"})[0], 400)
        self.llm.script = [{"tool": "write", "args": {"path": "b.txt", "content": "y"}}, {"text": "só planejei"}]
        self.c.json(f"/api/sessions/{sid}/send", {"text": "escreva b"})
        self.until(sid, lambda e: e["type"] == "assistant" and "planejei" in e.get("text", ""))
        self.assertFalse((cwd / "b.txt").exists())                               # plan mode reached the running bridge
        self.c.json(f"/api/sessions/{sid}/update", {"archived": True})
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/delete", {})[0], 200)
        self.assertEqual(self.c.json(f"/api/sessions/{sid}/send", {"text": "x"})[0], 404)
        self.assertFalse(self.app.store.log_path(sid).exists())

    def test_files_uploads_git_terminal_and_harness(self):
        cwd = self.work()
        (cwd / "src").mkdir()
        (cwd / "src" / "app.py").write_bytes(b"print('oi')\n")
        (cwd / "pagina.html").write_text("<h1>Oi</h1>", encoding="utf-8")
        sid = self.new(cwd)
        P = f"/api/sessions/{sid}"
        _, tree = self.c.json(f"{P}/tree?path=")
        self.assertEqual([(t["name"], t["dir"]) for t in tree], [("src", True), ("pagina.html", False)])
        self.assertEqual(self.c.json(f"{P}/find?q=app")[1][0]["path"], "src/app.py")
        _, f = self.c.json(f"{P}/file?path=src/app.py")
        self.assertEqual((f["text"], f["kind"]), ("print('oi')\n", "text"))
        code, raw = self.c.call(f"{P}/raw?path=pagina.html")
        self.assertEqual((code, raw), (200, b"<h1>Oi</h1>"))
        outside = Path(tempfile.mkdtemp()) / "segredo.txt"
        outside.write_text("fora")
        for path in ("../x", str(outside), "..\\..\\x"):                          # nothing outside the session's folder
            self.assertEqual(self.c.call(f"{P}/file?path={urllib.request.quote(path)}")[0], 403, path)
            self.assertEqual(self.c.call(f"{P}/raw?path={urllib.request.quote(path)}")[0], 403, path)

        from hangar import memory                                                       # project memory shows in the harness panel
        (cwd / "run_checks.py").write_text("print('ok')\n", encoding="utf-8")
        fake = type("S", (), {"cwd": cwd, "id": "s1", "ok_commands": {"python run_checks.py": 1.0}, "memory_saved": [],
                              "bus": type("B", (), {"emit": staticmethod(lambda *a, **k: None)})()})()
        self.assertTrue(memory.save(fake, {"name": "test-command", "kind": "command", "fact": "Rode os testes assim", "command": "python run_checks.py"}, "agent")[0])
        mem = self.c.json(f"{P}/harness")[1]["memory"]
        self.assertEqual([(m["name"], m["kind"], m["command"], m["stale"]) for m in mem], [("test-command", "command", "python run_checks.py", "")])
        self.assertEqual(self.c.json(f"{P}/forget", {"name": "test-command"})[1], {"removed": 1})
        self.assertEqual(self.c.json(f"{P}/harness")[1]["memory"], [])
        code, up = self.c.json(f"{P}/upload?name=nota%20fiscal.txt", raw=b"conteudo do anexo")
        self.assertEqual((code, up["name"], up["size"], up["kind"]), (200, "nota fiscal.txt", 17, "text"))
        self.assertEqual(Path(up["path"]).read_bytes(), b"conteudo do anexo")
        self.assertEqual(self.c.json(f"{P}/file?path={urllib.request.quote(up['path'])}")[1]["text"], "conteudo do anexo")
        self.assertEqual(self.c.call(f"{P}/upload?name=..%2F..%2Fevil.txt", raw=b"x")[0], 200)
        self.assertFalse((cwd.parent / "evil.txt").exists())
        self.llm.script = [{"text": "li o anexo"}]
        self.c.json(f"{P}/send", {"text": "veja", "attachments": [up["path"]]})
        user = self.until(sid, lambda e: e["type"] == "user")
        self.assertEqual(user["attachments"][0]["name"], "nota fiscal.txt")
        self.until(sid, lambda e: e["type"] == "turn_end")
        self.assertIn("attached file", json.dumps(self.llm.requests[-1]["body"]["messages"]))

        self.assertEqual(self.c.json(f"{P}/git")[1], {"repo": False, "files": []})
        git = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, capture_output=True)  # noqa: E731
        if git("init").returncode == 0:
            git("add", "."), git("commit", "-m", "base")
            (cwd / "src" / "app.py").write_bytes(b"print('ola')\n")
            (cwd / "novo.txt").write_bytes(b"novo\n")
            _, g = self.c.json(f"{P}/git")
            by = {f["path"]: f for f in g["files"]}
            self.assertEqual((g["repo"], by["src/app.py"]["status"], by["novo.txt"]["status"]), (True, "M", "?"))
            self.assertIn("+print('ola')", by["src/app.py"]["diff"])
            self.assertEqual(by["novo.txt"]["diff"], "+novo")

        code, out = self.c.call(f"{P}/terminal", {"command": "echo ola-terminal"})
        lines = [json.loads(l) for l in out.decode().splitlines()]
        self.assertEqual((lines[0]["type"], lines[-1]), ("start", {"type": "exit", "code": 0}))
        self.assertIn("ola-terminal", "".join(l.get("text", "") for l in lines))

        self.assertEqual(self.c.json(f"{P}/save", {"path": ".claude/commands/revisar.md", "text": "---\ndescription: Revisa\n---\nRevise $ARGUMENTS"})[0], 200)
        self.assertEqual(self.c.json(f"{P}/save", {"path": "HANGAR.md", "text": "regra"})[0], 200)
        for bad in ("src/app.py", "../HANGAR.md", ".claude/../x.md", "C:/x/CLAUDE.md"):
            self.assertEqual(self.c.json(f"{P}/save", {"path": bad, "text": "x"})[0], 403, bad)
        _, hz = self.c.json(f"{P}/harness")
        self.assertEqual(hz["files"], [".claude/commands/revisar.md", "HANGAR.md"])
        self.assertEqual(hz["commands"], [{"name": "revisar", "description": "Revisa", "hint": ""}])
        self.assertEqual(self.c.json(f"{P}/commands")[1][0]["name"], "revisar")
        _, d = self.c.json("/api/dirs?path=" + urllib.request.quote(str(cwd)))
        self.assertIn("src", d["dirs"])


class WorkflowTests(UiBase):
    def test_a_verify_run_goes_through_the_reviewer_and_back(self):
        cwd = self.offline_project()
        self.llm.script = [{"tool": "write", "args": {"path": "soma.py", "content": "def soma(a, b):\n    return a - b\n"}}, {"text": "Feito."},
                           {"text": 'Li o arquivo.\n{"verdict": "revise", "feedback": "soma subtrai em vez de somar"}'},
                           {"tool": "write", "args": {"path": "soma.py", "content": "def soma(a, b):\n    return a + b\n"}}, {"text": "Corrigido."},
                           {"text": '{"verdict": "approve", "feedback": ""}'}]
        self.assertEqual(self.c.json("/api/run", {"task": "x", "cwd": str(cwd), "workflow": "inventado"})[0], 400)
        self.assertEqual(self.c.json("/api/run", {"task": "", "cwd": str(cwd), "workflow": "verify"})[0], 400)
        code, r = self.c.json("/api/run", {"task": "crie soma.py", "cwd": str(cwd), "workflow": "verify", "permission": "auto", "effort": "low"})
        self.assertEqual(code, 200, r)
        sid = r["session"]
        end = self.until_run(sid, lambda e: e["type"] == "session_end")
        self.assertEqual(end["status"], "done")
        evs = self.run_events(sid)
        self.assertEqual([e["verdict"] for e in evs if e["type"] == "verdict"], ["revise", "approve"])
        team = {m["role"]: m["model"] for m in next(e for e in evs if e["type"] == "team")["team"]}     # no model was sent: the run is on "auto"
        self.assertEqual({m for r, m in team.items() if r != "perception"}, {"fake/model"})
        self.assertEqual(self.c.json("/api/team?cwd=" + urllib.request.quote(str(cwd)))[1]["team"][0], {
            "role": "worker", "model": "fake/model", "evidence": "",                   # a private provider: nothing was benchmarked
            "why": "faz a tarefa: o mais barato que resolveu todas as tarefas do dia a dia, de mídia e difíceis"})
        end = next(e for e in evs if e["type"] == "session_end")
        self.assertEqual({r["role"] for r in end["by_role"]}, {"worker", "verifier"})          # the bill says who spent it
        self.assertEqual(sum(r["calls"] for r in end["by_role"]), end["llm_calls"])
        self.assertEqual([(e["node"], e["visit"]) for e in evs if e["type"] == "node_start"], [("work", 1), ("review", 1), ("work", 2), ("review", 2)])
        self.assertEqual((cwd / "soma.py").read_text(encoding="utf-8").splitlines()[1].strip(), "return a + b")
        self.assertIn("soma subtrai", json.dumps(self.llm.requests[-2]["body"]["messages"]))      # the reviewer's feedback reached the worker
        _, st = self.c.json("/api/state")
        row = next(c for c in st["cli"] if c["id"] == sid)
        self.assertEqual((row["workflow"], row["task"]), ("verify", "crie soma.py"))
        req = urllib.request.Request(f"{self.base}/api/events?session={sid}&token={self.app.token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertIn('"type": "team"', resp.readline().decode())


@unittest.skipUnless(B.find_browser(), "no Chrome/Edge for the browser test")
class PageTests(UiBase):
    def setUp(self):
        self.b = B.Browser(1500, 950, extra_args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                                  "--auto-select-desktop-capture-source=Entire screen", "--auto-accept-this-tab-capture",
                                                  "--enable-usermedia-screen-capturing"])
        self.addCleanup(self.b.close)

    def wait(self, expr: str, timeout: float = 30, what: str = ""):
        end = time.time() + timeout
        while time.time() < end:
            v = self.b.eval(expr)
            if v:
                return v
            time.sleep(0.15)
        raise AssertionError(f"timed out: {what or expr}; console errors: {self.b.errors[-3:]}")

    def click(self, selector: str):
        self.wait(f"!!document.querySelector({json.dumps(selector)})", what=selector)
        self.b.eval(f"document.querySelector({json.dumps(selector)}).click()")

    def text(self, selector: str) -> str:
        return self.b.eval(f"(document.querySelector({json.dumps(selector)}) || {{}}).innerText || ''")

    def test_the_whole_app_in_the_browser(self):
        cwd = self.work()
        (cwd / "leiame.md").write_text("# Projeto\n", encoding="utf-8")
        (cwd / ".claude" / "commands").mkdir(parents=True)
        (cwd / ".claude" / "commands" / "resumo.md").write_text("---\ndescription: Resume\n---\nResuma $ARGUMENTS.", encoding="utf-8")
        b = self.b
        b.goto(self.base + "/", settle_ms=400)
        self.wait("!!document.querySelector('[data-testid=new-cwd]')", what="new session view")
        set_value = "(s, v) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }"
        b.eval(f"({set_value})('[data-testid=new-cwd]', {json.dumps(str(cwd))})")
        self.assertFalse(b.eval("!!document.querySelector('[data-testid=new-model]') || !!document.querySelector('.composer .model')"))   # no model picker
        self.assertIn("o Hangar escolhe", self.text("[data-testid=team-box]"))
        self.click("[data-testid=create-session]")
        self.wait("!!document.querySelector('[data-testid=prompt]')", what="composer")
        self.assertEqual(self.text("[data-testid=team-btn]"), "Modelos: automático")
        self.assertEqual(self.text("[data-testid=status-model]"), "modelos automáticos")

        # --- a turn with a permission card
        self.llm.script = [{"thinking": "vou criar", "tool": "write", "args": {"path": "landing.html", "content": "<!doctype html>\n<h1>Lançamento 2026</h1>"}},
                           {"text": "Pronto: **landing.html** foi criado."}]
        b.eval(f"({set_value})('[data-testid=prompt]', 'Crie uma landing page para o lançamento do produto')")
        self.click("[data-testid=send]")
        self.wait("!!document.querySelector('[data-testid=permission]')", what="permission card")
        self.assertFalse((cwd / "landing.html").exists())
        self.assertIn("Crie uma landing page", self.text("[data-testid=user-msg]"))
        self.assertIn("Crie uma landing page", self.text("[data-testid=title]"))          # the title came from the prompt
        self.assertEqual(b.eval("[...document.querySelectorAll('[data-testid=permission] kbd')].map(k => k.textContent).join('')"), "ASN")
        b.eval("dispatchEvent(new KeyboardEvent('keydown', {key: 'a', bubbles: true}))")              # the permission is answered from the keyboard
        self.wait("!!document.querySelector('[data-testid=turn-end]')", what="end of turn")
        self.assertEqual((cwd / "landing.html").read_text(encoding="utf-8").splitlines()[1], "<h1>Lançamento 2026</h1>")
        self.assertIn("landing.html foi criado", self.text("[data-testid=assistant-msg]"))
        b.eval("dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))")  # the command palette
        self.wait("document.querySelectorAll('[data-testid=palette-item]').length > 8", what="command palette")
        b.eval("(i => { i.value = 'permiss automat'; i.dispatchEvent(new Event('input')); })(document.querySelector('[data-testid=palette-input]'))")
        self.assertEqual(b.eval("[...document.querySelectorAll('[data-testid=palette-item]')].map(x => x.firstChild.textContent).join('|')"), "Permissões: Automático")
        b.eval("document.querySelector('[data-testid=palette-item]').click()")
        self.wait("document.querySelector('[data-testid=perm]').value === 'auto' && !document.querySelector('[data-testid=palette]')", what="permission set from the palette")
        b.eval("(async () => { await fetch('/api/sessions/' + window.__hangar.cur.id + '/update', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Hangar-Token': window.HANGAR_TOKEN}, body: JSON.stringify({permission: 'ask'})}); })()")
        self.assertEqual(b.eval("document.querySelector('[data-testid=assistant-msg] strong').textContent"), "landing.html")   # markdown
        self.assertIn("Permitido", self.text("[data-testid=perm-result]"))
        self.assertEqual(b.eval("document.querySelector('[data-testid=tool]').dataset.status"), "ok")
        self.assertIn("+2", self.text("[data-testid=tool] .diff .stat"))
        self.assertFalse(b.eval("!!document.querySelector('[data-testid=working]')"))
        self.assertEqual(self.text("[data-testid=status-model]"), "fake/model")             # the model that actually answered
        self.click("[data-testid=team-btn]")
        self.wait("!!document.querySelector('.modal table.team')", what="team table")
        self.assertEqual(b.eval("document.querySelectorAll('.modal table.team tr').length"), 8)
        self.assertIn("revisor independente", self.text(".modal table.team"))
        b.eval("document.querySelector('.modal .mfoot button').click()")

        # --- side panels
        self.click("[data-testid=tab-files]")
        self.wait("!!document.querySelector('[data-testid=file-row][data-path=\"landing.html\"]')", what="file in the tree")
        self.click('[data-testid=file-row][data-path="landing.html"]')
        self.wait("(document.querySelector('[data-testid=file-code]') || {}).innerText?.includes('Lançamento 2026')", what="file content")
        self.click("[data-testid=tab-artifacts]")
        self.wait("!!document.querySelector('[data-testid=artifact-frame]')", what="artifact frame")
        self.assertIn("/raw?path=landing.html", b.eval("document.querySelector('[data-testid=artifact-frame]').src"))
        self.click("[data-testid=tab-flow]")
        self.wait("document.querySelectorAll('#flowhost .fnode').length >= 5", what="graph nodes")
        kinds = b.eval("[...document.querySelectorAll('#flowhost .fnode')].map(g => [...g.classList].find(c => c.startsWith('k-')))")
        self.assertEqual(kinds, ["k-head", "k-user", "k-tool", "k-ask", "k-final"])
        self.assertIn("1 chamada de tool", self.text("#flowhost .flowinfo"))
        # the canvas answers the mouse: wheel zooms at the pointer, drag moves it, double click fits
        view = "(() => { const m = document.querySelector('#flowhost g.vp').transform.baseVal.consolidate().matrix; return [m.a, m.e, m.f].map(v => Math.round(v * 100) / 100); })()"
        fire = '''(type, x, y, extra) => { const box = document.querySelector('#flowhost .flowscroll'), r = box.getBoundingClientRect();
            const C = type === 'wheel' ? WheelEvent : type.startsWith('pointer') ? PointerEvent : MouseEvent;
            const at = document.elementFromPoint(r.left + x, r.top + y);
            (box.contains(at) ? at : box).dispatchEvent(new C(type, {bubbles: true, cancelable: true, clientX: r.left + x, clientY: r.top + y, button: 0, pointerId: 7, ...extra})); }'''
        k0, x0, y0 = b.eval(view)
        b.eval(f"({fire})('wheel', 100, 100, {{deltaY: -300}})")
        k1, x1, y1 = b.eval(view)
        self.assertGreater(k1, k0 * 1.4)
        self.assertAlmostEqual((100 - x1) / k1, (100 - x0) / k0, delta=1.5)                  # the point under the pointer did not move
        self.assertFalse(b.eval("document.querySelector('#flowFollow').checked"))            # the user took the camera
        b.eval(f"({fire})('wheel', 100, 100, {{deltaY: 900}})")
        self.assertLess(b.eval(view)[0], k1)
        k2, x2, y2 = b.eval(view)
        b.eval(f"(() => {{ const f = {fire}; f('pointerdown', 20, 300, {{}}); f('pointermove', 80, 340, {{}}); f('pointerup', 80, 340, {{}}); }})()")
        self.assertEqual(b.eval(view), [k2, round(x2 + 60, 2), round(y2 + 40, 2)])
        b.eval("document.querySelector('#flowhost button[data-z=\"1\"]').click()")
        self.assertGreater(b.eval(view)[0], k2)
        b.eval(f"({fire})('dblclick', 5, 5, {{}})")
        kf, xf, yf = b.eval(view)
        self.assertLessEqual(kf, 1)
        self.assertTrue(b.eval(f"(() => {{ const r = document.querySelector('#flowhost .flowscroll').getBoundingClientRect(), n = [...document.querySelectorAll('#flowhost .fnode')]"
                               ".map(g => g.getBoundingClientRect()); return n.every(q => q.left >= r.left - 1 && q.right <= r.right + 1 && q.top >= r.top - 1 && q.bottom <= r.bottom + 1); })()"))
        b.eval("(() => { const g = document.querySelector('#flowhost .fnode.k-tool'), q = g.getBoundingClientRect(); g.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: q.left + 5, clientY: q.top + 5})); })()")
        self.wait("!document.querySelector('.flowdetail').hidden", what="node detail after a click")
        self.click("[data-testid=tab-terminal]")
        self.wait("!!document.querySelector('[data-testid=term-in]')")
        b.eval("(() => { const i = document.querySelector('[data-testid=term-in]'); i.value = 'echo ola-do-terminal'; "
               "i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })()")
        self.wait("document.querySelector('[data-testid=term-out]').innerText.includes('saiu com código 0')", what="terminal output")
        self.assertIn("ola-do-terminal", self.text("[data-testid=term-out]"))
        self.click("[data-testid=tab-changes]")
        self.wait("document.querySelector('[data-testid=panel-changes]').innerText.includes('git')", what="changes panel")
        self.click("[data-testid=tab-harness]")
        self.wait("document.querySelector('[data-testid=panel-harness]').innerText.includes('/resumo')", what="harness panel")
        self.click("[data-testid=harness-file]")
        self.wait("!!document.querySelector('[data-testid=harness-editor]')")
        b.eval("document.querySelector('[data-testid=harness-editor]').value = '---\\ndescription: Resume bem\\n---\\nResuma $ARGUMENTS.'")
        self.click("[data-testid=harness-save]")
        self.wait(f"{json.dumps(str(cwd / '.claude' / 'commands' / 'resumo.md'))} && document.getElementById('toast').textContent === 'Salvo.'", what="save")
        self.assertIn("Resume bem", (cwd / ".claude" / "commands" / "resumo.md").read_text(encoding="utf-8"))
        self.click("[data-testid=tab-browser]")
        b.eval(f"(() => {{ const i = document.querySelector('[data-testid=browser-url]'); i.value = {json.dumps(self.llm.url)}; "
               "i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })()")
        self.wait("!!document.querySelector('[data-testid=browser-frame]')", what="browser frame")

        # --- slash command menu, attachment, recordings
        b.eval(f"({set_value})('[data-testid=prompt]', '/res')")
        self.wait("(document.querySelector('[data-testid=suggest]') || {}).innerText?.includes('/resumo')", what="slash menu")
        b.eval("document.querySelector('[data-testid=prompt]').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))")
        self.assertEqual(b.eval("document.querySelector('[data-testid=prompt]').value"), "/resumo ")
        b.eval(f"({set_value})('[data-testid=prompt]', '')")

        node = b.cmd("Runtime.evaluate", {"expression": "document.querySelector('[data-testid=file-input]')"})["result"]["objectId"]
        b.cmd("DOM.setFileInputFiles", {"files": [str(cwd / "leiame.md")], "objectId": node})
        self.wait("document.querySelectorAll('[data-testid=att-chip]:not(.busy)').length === 1", what="uploaded attachment")
        self.assertEqual(b.eval("document.querySelector('[data-testid=att-chip]').dataset.kind"), "text")

        b.eval("window.__hangarRecord = mode => document.querySelector('[data-testid=record]').click()")
        self.click("[data-testid=record]")
        b.eval("[...document.querySelectorAll('.menu button')].find(x => x.textContent.includes('só o microfone')).click()")
        self.wait("!!document.querySelector('[data-testid=recbar]')", what="microphone recording bar")
        self.wait("document.querySelector('[data-testid=rec-time]').textContent >= '00:02'", what="2 s of audio")
        self.click("[data-testid=rec-stop]")
        self.wait("document.querySelectorAll('[data-testid=att-chip]:not(.busy)').length === 2", what="audio attached")
        self.click("[data-testid=record]")
        b.eval("[...document.querySelectorAll('.menu button')].find(x => x.textContent.includes('tela e o microfone')).click()")
        self.wait("!!document.querySelector('[data-testid=recbar]')", timeout=20, what="screen recording bar")
        self.assertIn("tela", self.text("[data-testid=recbar]"))
        self.wait("document.querySelector('[data-testid=rec-time]').textContent >= '00:02'", what="2 s of video")
        self.click("[data-testid=rec-stop]")
        self.wait("document.querySelectorAll('[data-testid=att-chip]:not(.busy)').length === 3", what="video attached")
        kinds = b.eval("[...document.querySelectorAll('[data-testid=att-chip]')].map(c => c.dataset.kind)")
        self.assertEqual(kinds, ["text", "video", "video"])                       # .webm is a video container for both
        ups = sorted((self.app.store.dir / "uploads").glob("*/*"))
        webms = [p for p in ups if p.suffix == ".webm"]
        self.assertEqual(len(webms), 2)
        for p in webms:
            self.assertGreater(p.stat().st_size, 1500, p.name)
            self.assertEqual(p.read_bytes()[:4], b"\x1a\x45\xdf\xa3")              # a real WebM (EBML) file

        # only the text file goes with the message here: describing media needs a perception model
        b.eval("[...document.querySelectorAll('[data-testid=att-chip]')].slice(1).reverse().forEach(c => c.querySelector('button').click())")
        self.llm.script = [{"text": "Li o leiame."}]
        b.eval(f"({set_value})('[data-testid=prompt]', 'leia o anexo')")
        self.click("[data-testid=send]")
        self.wait("document.querySelectorAll('[data-testid=turn-end]').length === 2", what="second turn")
        self.assertIn("leiame.md", b.eval("[...document.querySelectorAll('[data-testid=user-msg]')].pop().innerText"))
        self.assertIn("attached file", json.dumps(self.llm.requests[-1]["body"]["messages"]))

        # --- sidebar: the session is listed, searchable, and survives a reload
        self.assertIn("Crie uma landing page", self.text("[data-testid=session-row].on"))
        b.goto(self.base + "/?session=" + b.eval("window.__hangar.cur.id"), settle_ms=400)
        self.wait("document.querySelectorAll('[data-testid=turn-end]').length === 2", what="history after reload")
        self.assertEqual(b.eval("document.querySelectorAll('[data-testid=user-msg]').length"), 2)
        self.assertEqual([e for e in b.errors if "favicon" not in str(e) and "/v1" not in str(e)], [])   # /v1: the fake model's URL in the browser panel
        self.click("[data-testid=tab-files]")
        self.click('[data-testid=file-row][data-path="landing.html"]')
        self.wait("!!document.querySelector('[data-testid=file-code]')", what="file after reload")
        (ROOT / "bench" / "logs").mkdir(parents=True, exist_ok=True)
        (ROOT / "bench" / "logs" / "ui-test.png").write_bytes(b.screenshot())


    def test_a_pev_task_from_the_new_session_view(self):
        cwd = self.offline_project()
        b = self.b
        b.goto(self.base + "/", settle_ms=400)
        self.wait("!!document.querySelector('[data-testid=new-workflow]')", what="workflow select")
        set_value = "(s, v) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }"
        self.assertEqual(self.text("[data-testid=create-session]"), "Criar sessão")
        b.eval(f"({set_value})('[data-testid=new-workflow]', 'pev')")
        self.assertFalse(b.eval("!!document.querySelector('[data-testid=new-planner]')"))    # planner and reviewer come from the team
        self.assertIn("planeja", self.text("[data-testid=wf-hint]"))
        self.assertEqual(self.text("[data-testid=create-session]"), "Iniciar tarefa")
        b.eval(f"({set_value})('[data-testid=new-cwd]', {json.dumps(str(cwd))})")
        b.eval(f"({set_value})('[data-testid=new-perm]', 'auto')")
        self.click("[data-testid=create-session]")                                        # no task yet: nothing starts
        self.wait("document.getElementById('toast').textContent.includes('Descreva a tarefa')", what="empty task warning")
        self.llm.script = [{"text": "1. Criar ola.txt com a palavra ola.\nACCEPTANCE: o arquivo existe."},
                           {"tool": "write", "args": {"path": "ola.txt", "content": "ola"}}, {"text": "Criei ola.txt."},
                           {"text": '{"verdict": "approve", "feedback": ""}'}]
        b.eval(f"({set_value})('[data-testid=new-prompt]', 'crie ola.txt')")
        self.click("[data-testid=create-session]")
        self.wait("document.querySelectorAll('[data-testid=stage]').length === 3", timeout=60, what="three stages in the chat")
        self.assertEqual(b.eval("[...document.querySelectorAll('[data-testid=stage]')].map(s => s.textContent)"),
                         ["Planejamento", "Execução", "Revisão independente"])
        self.wait("!!document.querySelector('[data-testid=verdict]')", timeout=60, what="verdict line")
        self.assertIn("aprovado", self.text("[data-testid=verdict]"))
        self.assertEqual((cwd / "ola.txt").read_text(), "ola")
        self.assertIn("ACCEPTANCE", self.text("[data-testid=chat]"))                    # the planner's plan is shown
        self.assertIn("executor model · planejador model · revisor model", self.text("[data-testid=team-line]"))
        bill = self.text("[data-testid=role-costs]")                                    # who spent what, at the end of the run
        self.assertTrue(all(w in bill for w in ("executor", "planejador", "revisor")), bill)
        # the graph opened by itself, with one lane per stage
        self.wait("document.querySelectorAll('#flowhost .fnode.k-head').length === 3", what="three lanes")
        heads = b.eval("[...document.querySelectorAll('#flowhost .fnode.k-head .t1')].map(t => t.textContent)")
        self.assertEqual(heads, ["plan", "execute", "review"])
        lanes = b.eval("[...document.querySelectorAll('#flowhost .fnode')].map(g => [g.querySelector('.t1').textContent, Math.round(g.transform.baseVal[0].matrix.e)])")
        x = dict(lanes)
        self.assertEqual(x["revisor: aprova"], x["review"])                              # the verdict sits in the reviewer's lane
        self.assertNotIn('"verdict"', self.text("[data-testid=chat]"))                  # said once, as "Revisor: aprovado."
        self.assertEqual(self.text("[data-testid=chat]").count("Criei ola.txt."), 1)
        self.wait("document.getElementById('clistop').hidden", timeout=30, what="stop button gone when the run ends")
        self.assertIn("Planejar, executar e revisar", self.text(".composer"))
        self.wait("!document.querySelector('[data-testid=working]')", timeout=30, what="run finished")
        self.assertEqual([e for e in b.errors if "favicon" not in str(e)], [])
        (ROOT / "bench" / "logs" / "ui-workflow.png").write_bytes(b.screenshot())


if __name__ == "__main__":
    unittest.main()
