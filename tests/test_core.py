"""Offline unit tests (no network): python -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import config, tools as T  # noqa: E402
from hangar.mcp import MCPManager  # noqa: E402
from hangar.session import Session  # noqa: E402
from hangar.toolcall import coerce_args, parse_text_calls, repair_json  # noqa: E402


class FakeAgent:
    name, model = "t", "x"


def make_session(tmp: Path, **kw) -> Session:
    return Session(config.load(tmp), tmp, **kw)


class ToolCallTests(unittest.TestCase):
    def test_repair(self):
        self.assertEqual(repair_json('{"a": 1,}')[0], {"a": 1})
        self.assertEqual(repair_json('"{\\"a\\": 1}"')[0], {"a": 1})          # double-encoded
        self.assertEqual(repair_json("```json\n{\"a\": [1, 2]}\n```")[0], {"a": [1, 2]})
        self.assertEqual(repair_json("{'a': True}")[0], {"a": True})           # python literal
        self.assertFalse(repair_json("not json at all")[1])

    def test_coerce(self):
        schema = T.builtin()["read"].parameters
        args, err = coerce_args("read", schema, {"file_path": "a.txt", "limit": "20", "junk": 1})
        self.assertIsNone(err)
        self.assertEqual(args, {"path": "a.txt", "limit": 20})
        _, err = coerce_args("read", schema, {})
        self.assertIn("Missing required", err)

    def test_text_protocol(self):
        text = 'Vou ler.\n<tool_call>\n{"name": "read", "arguments": {"path": "a.py"}}\n</tool_call>'
        clean, calls = parse_text_calls(text)
        self.assertEqual(clean, "Vou ler.")
        self.assertEqual(calls, [{"name": "read", "args": {"path": "a.py"}}])
        _, calls = parse_text_calls('<tool_call>{"name": "shell", "arguments": {"command": "ls"}')   # unclosed tag
        self.assertEqual(calls[0]["name"], "shell")
        _, calls = parse_text_calls('<function=glob>{"pattern": "*.py"}</function>')
        self.assertEqual(calls[0]["args"], {"pattern": "*.py"})
        self.assertEqual(parse_text_calls("just an answer with {braces}")[1], [])
        # hybrids seen in real runs of a model without native tool calling
        _, calls = parse_text_calls('<tool_call>\n{"function=glob", "arguments": {"pattern": "**/*"}}\n</tool_call>')
        self.assertEqual(calls, [{"name": "glob", "args": {"pattern": "**/*"}}])
        _, calls = parse_text_calls('<tool_call>\n{"function=glob>\n{"pattern": "*.json", "path": "."}\n</tool_call>')
        self.assertEqual(calls, [{"name": "glob", "args": {"pattern": "*.json", "path": "."}}])
        _, calls = parse_text_calls('<tool_call>\n{"function": "list_vaults"}\n</tool_call>')
        self.assertEqual(calls, [{"name": "list_vaults", "args": {}}])


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_t_")).resolve()
        self.s = make_session(self.tmp)
        self.ctx = T.Ctx(self.s, FakeAgent())
        self.b = T.builtin()

    def tearDown(self):
        self.s.bus.close()

    def test_a_failed_look_around_does_not_undo_a_passing_check(self):
        for cmd, probe in (("git status --short", True), ("git rev-parse --show-toplevel", True), ("pwd; ls -la; git diff --stat -- a.py", True),
                           ("cat a.py | head -3", True), ("git -C . log --oneline", True), ("python -m unittest -q", False),
                           ("git commit -m x", False), ("ls && pytest", False), ("echo x > a.py", False), ("", False)):
            self.assertEqual(T.is_probe(cmd), probe, cmd)
        sh = self.b["shell"].fn
        sh(self.ctx, {"command": "python -c \"print('testes ok')\""})
        self.assertEqual(self.s.last_exit, 0)
        self.assertIn("exit 128", sh(self.ctx, {"command": "git rev-parse --show-toplevel"}))     # not a repository
        self.assertEqual(self.s.last_exit, 0)                                               # the passing check still stands
        self.b["write"].fn(self.ctx, {"path": "a.py", "content": "x = 1\n"})
        sh(self.ctx, {"command": "git rev-parse --show-toplevel"})
        self.assertNotEqual(self.s.last_exit, 0)                                            # an edit since the check: nothing is verified now
        sh(self.ctx, {"command": "python -c \"print('ok')\""})
        sh(self.ctx, {"command": "python -c \"import sys; sys.exit(3)\""})
        self.assertEqual(self.s.last_exit, 3)                                               # a real command that fails still counts

    def test_write_read_edit(self):
        self.b["write"].fn(self.ctx, {"path": "a.py", "content": "def f():\n    return 1\n"})
        self.assertIn("1\tdef f():", self.b["read"].fn(self.ctx, {"path": "a.py"}))
        self.b["edit"].fn(self.ctx, {"path": "a.py", "old": "return 1", "new": "return 2"})
        self.b["edit"].fn(self.ctx, {"path": "a.py", "old": "def f():\nreturn 2", "new": "def f():\n    return 3"})   # fuzzy indent
        self.assertEqual((self.tmp / "a.py").read_text(), "def f():\n    return 3\n")
        with self.assertRaises(T.ToolError):
            self.b["edit"].fn(self.ctx, {"path": "a.py", "old": "nope", "new": "x"})
        self.assertEqual(self.s.files, {"a.py"})

    def test_write_outside_cwd_denied(self):
        with self.assertRaises(T.ToolError):
            self.b["write"].fn(self.ctx, {"path": str(Path.home() / "hangar_should_not_exist.txt"), "content": "x"})

    def test_shell_and_guards(self):
        self.assertIn("[exit 0]", self.b["shell"].fn(self.ctx, {"command": "echo ola"}))
        with self.assertRaises(T.ToolError):
            self.b["shell"].fn(self.ctx, {"command": "rm -rf /"})
        with self.assertRaises(T.ToolError):
            self.b["shell"].fn(self.ctx, {"command": "git push origin main --force"})
        for cmd in ("taskkill //F //IM python.exe >/dev/null 2>&1; sleep 1", "pkill -f kvd.py", "killall node",
                    "powershell -c Stop-Process -Name python -Force", "kill -9 -1"):
            with self.assertRaises(T.ToolError, msg=cmd):
                self.b["shell"].fn(self.ctx, {"command": cmd})
        self.assertIn("[exit", self.b["shell"].fn(self.ctx, {"command": "echo taskkill //PID 999999 would be fine"}))

    def test_grep_glob(self):
        (self.tmp / "x.txt").write_text("alpha\nbeta\n")
        self.assertIn("x.txt:2: beta", self.b["grep"].fn(self.ctx, {"pattern": "bet"}))
        self.assertIn("x.txt", self.b["glob"].fn(self.ctx, {"pattern": "*.txt"}))

    def test_output_cap_spills_to_disk(self):
        out = self.s.cap("x" * 50000, "shell")
        self.assertLess(len(out), 9000)
        self.assertEqual(len(list((self.s.dir / "spill").glob("*.txt"))), 1)

    def test_scripted_answers_and_events(self):
        s = make_session(self.tmp, answers=["azul"])
        self.assertEqual(s.ask("cor?"), "azul")
        self.assertIsNone(s.ask("outra?"))
        s.bus.close()
        types = [json.loads(l)["type"] for l in (s.dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(types, ["question", "answer", "question", "answer"])


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_r_")).resolve()
        self.s = make_session(self.tmp)
        self.ctx = T.Ctx(self.s, FakeAgent())
        self.b = T.builtin()

    def tearDown(self):
        self.s.finish("done")

    def test_backup_manifest_allows_undo(self):
        (self.tmp / "old.txt").write_text("original")
        self.b["write"].fn(self.ctx, {"path": "old.txt", "content": "changed"})
        self.b["edit"].fn(self.ctx, {"path": "old.txt", "old": "changed", "new": "changed twice"})
        self.b["write"].fn(self.ctx, {"path": "new.txt", "content": "x"})
        manifest = json.loads((self.s.dir / "backup" / "manifest.json").read_text())
        old_key, new_key = str(self.tmp / "old.txt"), str(self.tmp / "new.txt")
        self.assertIsNone(manifest[new_key])                                   # did not exist before
        self.assertEqual((self.s.dir / "backup" / manifest[old_key]).read_text(), "original")   # first version, kept once

    def test_background_process(self):
        out = self.b["shell"].fn(self.ctx, {"command": "echo started; sleep 30", "background": True})
        self.assertIn("bg1", out)
        self.assertIn("running", self.b["process"].fn(self.ctx, {"action": "list"}))
        self.assertIn("started", self.b["process"].fn(self.ctx, {"action": "output", "id": "bg1"}))
        self.b["process"].fn(self.ctx, {"action": "kill", "id": "bg1"})
        self.s.bg["bg1"]["p"].wait(timeout=10)
        self.assertIn("exited", self.b["process"].fn(self.ctx, {"action": "list"}))

    def test_notes_and_sticky_state_survive_a_new_session(self):
        self.b["note"].fn(self.ctx, {"text": "porta do servidor: 8123"})
        self.b["plan"].fn(self.ctx, {"items": [{"step": "subir servidor", "status": "done"}, "testar"]})
        self.assertIn("porta do servidor: 8123", self.s.sticky())
        self.assertIn("[pending] testar", self.s.sticky())
        again = Session(config.load(self.tmp), self.tmp, sid=self.s.id)          # resume of the same session id
        self.assertEqual(again.notes, ["porta do servidor: 8123"])
        self.assertEqual(again.meta["resumed"], 1)
        again.bus.close()

    def test_agent_transcript_roundtrip(self):
        from hangar.agent import Agent
        a = Agent(self.s, model="openai/gpt-6-luna", name="work")
        a.messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "tarefa X"},
                      {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "glob", "arguments": "{}"}}]},
                      {"role": "tool", "tool_call_id": "c1", "content": "a.py"}]
        a.save()
        b = Agent(self.s, model="openai/gpt-6-luna", name="work")
        self.assertTrue(b.load())
        self.assertEqual(b.messages, a.messages)

    def test_compaction_floor_and_hysteresis(self):
        from hangar.agent import Agent
        self.s.cfg["context_budget"] = 500                      # absurdly small on purpose
        a = Agent(self.s, model="openai/gpt-6-luna", name="work")
        a.messages = [{"role": "system", "content": "x" * 6000}, {"role": "user", "content": "t"}]
        a.ctx.maybe_compact()
        self.assertGreaterEqual(a.ctx.budget, 8000)             # floor = fixed prefix + working room
        self.assertGreaterEqual(a.ctx.next_summary, 0.85 * a.ctx.budget)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_h_")).resolve()

    def session(self, toml: str, **over) -> Session:
        (self.tmp / "hangar.toml").write_text(toml, encoding="utf-8")
        s = Session(config.load(self.tmp, over), self.tmp)
        self.addCleanup(s.bus.close)
        return s

    def test_deny_rule_and_post_message(self):
        s = self.session('[[hooks]]\nevent = "pre_tool"\ntool = "shell"\nmatch = "git\\\\s+commit"\naction = "deny"\nmessage = "commits sao manuais"\n'
                         '[[hooks]]\nevent = "post_tool"\ntool = "write|edit"\naction = "warn"\nmessage = "rode o linter"\n')
        self.assertIn("commits sao manuais", s.hooks.pre_tool(None, "shell", {"command": "git commit -m x"}))
        self.assertEqual(s.hooks.pre_tool(None, "shell", {"command": "git status"}), "")
        self.assertEqual(s.hooks.pre_tool(None, "read", {"path": "git commit"}), "")           # tool filter
        self.assertIn("rode o linter", s.hooks.post_tool(None, "write", {"path": "a.py"}, True, "ok"))
        self.assertEqual(s.hooks.post_tool(None, "read", {"path": "a.py"}, True, "ok"), "")

    def test_project_run_hooks_need_trust(self):
        toml = '[[hooks]]\nevent = "pre_finish"\naction = "run"\ncommand = "python -c \\"import sys; sys.exit(3)\\""\n'
        untrusted = self.session(toml)
        self.assertEqual(untrusted.hooks.pre_finish(None, "pronto"), "")                        # skipped: code from the repo is not run
        trusted = self.session(toml, trust_project=True)
        self.assertIn("exit 3", trusted.hooks.pre_finish(None, "pronto"))
        for _ in range(2):
            trusted.hooks.pre_finish(None, "pronto")
        self.assertEqual(trusted.hooks.pre_finish(None, "pronto"), "")                          # gives up after 3 pushes...
        self.assertTrue(trusted.incomplete)                                                     # ...and the run is NOT reported as done

    def test_a_repo_cannot_trust_itself(self):
        s = self.session('trust_project = true\n[[hooks]]\nevent = "pre_finish"\naction = "run"\ncommand = "exit 1"\n')
        self.assertFalse(s.hooks.trusted)
        self.assertEqual(s.hooks.rules, [])

    def test_python_plugin(self):
        d = self.tmp / ".hangar" / "plugins"
        d.mkdir(parents=True)
        (d / "policy.py").write_text('def pre_tool(ctx, name, args):\n    if name == "write" and str(args.get("path", "")).endswith(".env"):\n'
                                     '        return "nunca escreva segredos"\n\ndef post_tool(ctx, name, args, ok, output):\n'
                                     '    return "veja o estilo do projeto" if name == "edit" else None\n\ndef broken(ctx):\n    raise RuntimeError\n')
        s = self.session("", trust_project=True)
        self.assertIn("nunca escreva segredos", s.hooks.pre_tool(None, "write", {"path": ".env", "content": "x"}))
        self.assertEqual(s.hooks.pre_tool(None, "write", {"path": "a.txt", "content": "x"}), "")
        self.assertIn("veja o estilo", s.hooks.post_tool(None, "edit", {"path": "a.py"}, True, ""))
        self.assertEqual(self.session("").hooks.plugins, [])                                    # same folder, not trusted: plugin not loaded


class LessonTests(unittest.TestCase):
    def setUp(self):
        from hangar import lessons
        self.lessons = lessons
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_l_")).resolve()
        for f in lessons.DIR.glob("*.json") if lessons.DIR.is_dir() else []:
            f.unlink()

    def new_session(self, reply: str, **cfg):
        s = Session({**config.load(self.tmp), **cfg}, self.tmp, task="fazer o servidor subir na porta certa")
        self.addCleanup(s.bus.close)
        s.llm.chat = lambda *a, **k: SimpleNamespace(content=reply, usage={"prompt": 10, "completion": 5, "cost": 0.0}, ms=1, finish="stop", model="")
        return s

    def friction(self, s, approved=False):
        for i in range(3):
            s.bus.emit("tool_start", id=f"c{i}", name="shell", args={"command": "python server.py"})
            s.bus.emit("tool_end", id=f"c{i}", name="shell", ok=False, preview="Error: address already in use")
        if approved:
            s.bus.emit("verdict", verdict="approve", feedback="")

    REPLY = ('[{"scope": "general", "title": "Porta ocupada no Windows", "situation": "ao subir servidor de teste", '
             '"lesson": "Escolha uma porta livre com socket.bind(0) em vez de fixar 8000.", "evidence": "3 falhas address already in use"}]')

    def test_only_verified_sessions_with_friction_teach(self):
        s = self.new_session(self.REPLY)
        self.friction(s)
        self.assertEqual(self.lessons.reflect(s, {"status": "done", "final": "ok"}), [])          # outcome not verified
        s.last_exit, s.edits_since_run = 0, False
        self.assertEqual(self.lessons.reflect(s, {"status": "incomplete", "final": ""}), [])      # not done
        calm = self.new_session(self.REPLY)
        calm.last_exit = 0
        self.assertEqual(self.lessons.reflect(calm, {"status": "done", "final": "ok"}), [])       # nothing went wrong: nothing to learn
        got = self.lessons.reflect(s, {"status": "done", "final": "ok"})
        self.assertEqual([l["title"] for l in got], ["Porta ocupada no Windows"])
        self.assertEqual(got[0]["session"], s.id)                                                 # provenance

    def test_reuse_dedupe_expiry_and_opt_out(self):
        s = self.new_session(self.REPLY)
        self.friction(s, approved=True)
        self.assertEqual(len(self.lessons.reflect(s, {"status": "done", "final": "ok"})), 1)
        self.assertEqual(self.lessons.reflect(s, {"status": "done", "final": "ok"}), [])          # same lesson again: merged, not duplicated
        stored = self.lessons.load()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["confirmations"], 2)
        nxt = self.new_session("[]")
        block = self.lessons.prompt_block(nxt, "subir o servidor de teste numa porta livre")
        self.assertIn("socket.bind(0)", block)
        self.assertEqual(self.lessons.prompt_block(nxt, "traduzir um poema para o frances"), "")  # unrelated task: no hint
        self.assertEqual(self.lessons.load(max_age_days=0), [])                                   # expired lessons are ignored
        empty = self.new_session("nao sei")
        self.friction(empty, approved=True)
        self.assertEqual(self.lessons.reflect(empty, {"status": "done", "final": "ok"}), [])      # unparseable reflection stores nothing
        off = self.new_session(self.REPLY, lessons=False)
        self.friction(off, approved=True)
        self.assertEqual(self.lessons.reflect(off, {"status": "done", "final": "ok"}), [])


PNG_1x1 = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
           b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82")


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_s_")).resolve()

    def test_pptx_package_is_well_formed(self):
        import zipfile
        from xml.dom import minidom
        from hangar import pptx
        (self.tmp / "pic.png").write_bytes(PNG_1x1)
        self.assertEqual(pptx.image_size(self.tmp / "pic.png"), (1, 1))
        spec = {"title": "Teste & <cia>", "slides": [
            {"layout": "title", "title": "Título com acento & símbolo <ok>", "subtitle": "sub", "image": "pic.png"},
            {"layout": "kpis", "title": "KPIs", "kpis": [{"label": "A", "value": "1", "delta": "-2%"}, {"label": "B", "value": "2", "delta": "+3%"}], "takeaway": "t"},
            {"layout": "bullets", "title": "B", "bullets": ["um", "dois"], "image": "pic.png"},
            {"layout": "image", "title": "I", "image": "pic.png", "caption": "c"},
            {"layout": "two_col", "title": "T", "left": {"heading": "L", "bullets": ["a"]}, "right": {"heading": "R", "bullets": ["b"]}},
            {"layout": "section", "title": "S"}, {"layout": "quote", "text": "q", "by": "x"}, {"layout": "closing", "title": "fim"}]}
        r = pptx.build(spec, self.tmp / "d.pptx", base=self.tmp)
        self.assertEqual((r["slides"], r["images"]), (8, 1))                     # the same picture is stored once
        with zipfile.ZipFile(self.tmp / "d.pptx") as z:
            names = z.namelist()
            self.assertEqual(names[0], "[Content_Types].xml")
            self.assertIsNone(z.testzip())
            for n in names:
                if n.endswith((".xml", ".rels")):
                    minidom.parseString(z.read(n))                                # every part parses (escaping is right)
            self.assertIn("Título com acento &amp; símbolo &lt;ok&gt;", z.read("ppt/slides/slide1.xml").decode("utf-8"))
            self.assertEqual(len([n for n in names if n.startswith("ppt/slides/slide")]), 8)
        with self.assertRaises(FileNotFoundError):
            pptx.build({"slides": [{"layout": "image", "image": "nao_existe.png"}]}, self.tmp / "x.pptx", base=self.tmp)
        with self.assertRaises(ValueError):
            pptx.build({"slides": []}, self.tmp / "x.pptx", base=self.tmp)

    def test_builtin_skills_ship_with_the_harness(self):
        from hangar import skills
        found = skills.discover(self.tmp)
        for name in ("data-analysis", "dashboard", "presentation", "image-generation", "motion-video"):
            self.assertIn(name, found)
            self.assertTrue(found[name]["description"])
        (self.tmp / ".hangar" / "skills" / "dashboard").mkdir(parents=True)
        (self.tmp / ".hangar" / "skills" / "dashboard" / "SKILL.md").write_text("---\nname: dashboard\ndescription: do projeto\n---\nx", encoding="utf-8")
        self.assertEqual(skills.discover(self.tmp)["dashboard"]["description"], "do projeto")      # a project skill overrides the built-in

    def test_studio_spend_is_added_to_the_session_bill(self):
        s = make_session(self.tmp)
        (s.dir / "studio_usage.jsonl").write_text(json.dumps({"kind": "image", "model": "img/model", "cost": 0.07}) + "\n", encoding="utf-8")
        summary = s.finish("done")
        self.assertAlmostEqual(summary["cost"], 0.07)
        self.assertEqual(summary["by_model"]["img/model"]["calls"], 1)

    def test_shell_can_reach_the_studio_commands_from_any_folder(self):
        s = make_session(self.tmp)
        out = T.builtin()["shell"].fn(T.Ctx(s, FakeAgent()), {"command": "python -m hangar studio --help"})
        s.bus.close()
        self.assertIn("screenshot", out)
        self.assertIn("[exit 0]", out)

    def test_browser_screenshot_and_frame_accurate_seek(self):
        from hangar import browser
        if not browser.find_browser():
            self.skipTest("no Chrome/Edge on this machine")
        page = self.tmp / "a.html"
        page.write_text("<html><body style='margin:0'><div id='b' style='height:40px;background:#f00;animation:g 4s linear forwards'></div>"
                        "<style>@keyframes g{from{width:0}to{width:400px}}</style>"
                        "<script>window.hangarFrame = t => { document.title = 't=' + t; }; console.error('boom');</script></body></html>", encoding="utf-8")
        with browser.Browser(800, 400) as b:
            b.goto(str(page))
            b.eval(browser.SEEK % 2.0)
            self.assertEqual(b.eval("document.title"), "t=2")
            self.assertAlmostEqual(b.eval("document.getElementById('b').getBoundingClientRect().width"), 200, delta=2)   # CSS animation seeked to 50%
            self.assertEqual(b.screenshot()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertTrue(any("boom" in e for e in b.errors))                  # console errors are reported back to the agent


class MCPTests(unittest.TestCase):
    def test_stdio_roundtrip(self):
        tmp = Path(tempfile.mkdtemp(prefix="hangar_mcp_"))
        (tmp / ".mcp.json").write_text(json.dumps({"mcpServers": {"vault": {
            "command": sys.executable, "args": [str(ROOT / "tests" / "mcp_vault_server.py")]}}}))
        m = MCPManager(tmp)
        m.load()
        try:
            self.assertEqual([t["name"] for _, t in m.all_tools()], ["get_secret", "list_vaults"])
            self.assertEqual(m.call("mcp__vault__get_secret", {"vault": "alfa"}), "HNGR-7Q4X-ALFA-2291")
            self.assertTrue(m.call("get_secret", {"vault": "zzz"}).startswith("Error"))
            self.assertEqual(m.search("secret")[0][1]["name"], "get_secret")
        finally:
            m.stop()


if __name__ == "__main__":
    unittest.main()
