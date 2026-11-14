"""Project memory: facts are only stored with a check the harness can make, they stay honest without model calls,
and the next session starts already knowing them. Offline."""
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

from hangar import config, memory, prompts, tools as T  # noqa: E402
from hangar.agent import Agent  # noqa: E402
from hangar.session import Session  # noqa: E402

PASS = 'python -c "import sys; sys.exit(0)"'            # stands in for a test command; one-off rules are tested apart
FAIL = 'python -c "import sys; sys.exit(3)"'


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.cwd = Path(tempfile.mkdtemp(prefix="hangar_mem_")).resolve()
        (self.cwd / "qa").mkdir()
        (self.cwd / "qa" / "check_loja.py").write_text("import unittest\n", encoding="utf-8")
        (self.cwd / "run_checks.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    def session(self, reply: str = "[]", **cfg) -> Session:
        s = Session({**config.load(self.cwd), **cfg}, self.cwd, task="corrigir o desconto")
        self.addCleanup(s.bus.close)
        s.llm.chat = lambda *a, **k: (self.calls.append(a[1]) or SimpleNamespace(
            content=reply, usage={"prompt": 10, "completion": 5, "cost": 0.0001}, ms=1, finish="stop", model=""))
        self.calls: list = []
        return s

    def ctx(self, s: Session) -> T.Ctx:
        return T.Ctx(s, Agent(s, model=s.model, name="work"))

    def test_a_fact_is_only_stored_with_a_check_the_harness_can_make(self):
        s = self.session()
        ctx, tools = self.ctx(s), T.builtin()
        remember, shell = tools["remember"].fn, tools["shell"].fn
        fact = {"name": "Test Command", "kind": "command", "fact": "Os testes rodam com run_checks.py", "command": "python run_checks.py"}
        with self.assertRaises(T.ToolError) as e:                                          # never ran here: not proven
            remember(ctx, fact)
        self.assertIn("has not exited 0", str(e.exception))
        shell(ctx, {"command": "python   run_checks.py"})                                 # whitespace does not matter
        self.assertEqual(remember(ctx, fact), "Remembered `test-command`.")
        for bad, why in (({**fact, "name": "x2", "command": 'python -c "print(1)"'}, "one-off"),
                         ({"name": "layout", "kind": "layout", "fact": "Os testes ficam em qa/"}, "give `paths`"),
                         ({"name": "layout", "kind": "layout", "fact": "Os testes ficam em qa/", "paths": ["nao/existe"]}, "do not exist"),
                         ({"name": "fora", "kind": "layout", "fact": "config fora", "paths": ["../.."]}, "do not exist"),
                         ({"name": "chave", "kind": "gotcha", "fact": "use api_key=sk-abcdefghijklmnopqrstuv", "paths": ["qa"]}, "secret"),
                         ({"name": "tipo", "kind": "ideia", "fact": "x", "paths": ["qa"]}, "`kind` must be"),
                         ({"name": "outro", "kind": "command", "fact": "igual", "command": "python run_checks.py"}, "already in memory")):
            with self.assertRaises(T.ToolError) as e:
                remember(ctx, bad)
            self.assertIn(why, str(e.exception), bad)
        self.assertEqual(remember(ctx, {"name": "tests-layout", "kind": "layout", "fact": "Os testes ficam em qa/, arquivos check_*.py",
                                        "paths": ["qa", "qa/check_loja.py"], "detail": "Um arquivo por módulo."}), "Remembered `tests-layout`.")

        files = sorted(p.name for p in memory.folder(self.cwd).iterdir())
        self.assertEqual(files, ["MEMORY.md", "test-command.md", "tests-layout.md"])          # plain files, one per fact, plus the index
        index = (memory.folder(self.cwd) / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("- [test-command](test-command.md) (command) — Os testes rodam com run_checks.py", index)
        text = (memory.folder(self.cwd) / "tests-layout.md").read_text(encoding="utf-8")
        self.assertIn('paths: ["qa", "qa/check_loja.py"]', text)
        self.assertIn(f'session: "{s.id}"', text)                                          # provenance
        self.assertTrue(text.rstrip().endswith("Um arquivo por módulo."))
        self.assertEqual(s.memory_saved, ["test-command", "tests-layout"])

    def test_the_next_session_starts_knowing_and_only_the_main_agent_can_write(self):
        first = self.session()
        T.builtin()["shell"].fn(self.ctx(first), {"command": "python run_checks.py"})
        memory.save(first, {"name": "test-command", "kind": "command", "fact": "Rode os testes assim", "command": "python run_checks.py"}, "agent")
        self.assertEqual(first.memory_block, "")                                           # the prompt of a running session never changes
        s = self.session()
        self.assertIn("- test-command (command): Rode os testes assim — `python run_checks.py`", s.memory_block)
        main = Agent(s, model=s.model, name="work")
        system = prompts.build(s, main)
        self.assertIn("# Project memory (verified in this project by earlier sessions: rely on it instead of rediscovering", system)
        self.assertIn("save it with the remember tool", system)
        self.assertIn("remember", main.toolmap)
        for role, toolset in (("sub", "all"), ("verifier", "verify"), ("planner", "readonly")):
            other = Agent(s, model=s.model, role=role, toolset=toolset, name=role)
            self.assertNotIn("remember", other.toolmap, role)
            self.assertIn("test-command (command)", prompts.build(s, other), role)          # everyone reads it
            self.assertNotIn("save it with the remember tool", prompts.build(s, other), role)
        off = self.session(memory=False)                                                   # --no-memory: neither read nor written
        agent = Agent(off, model=off.model, name="work")
        self.assertEqual((off.memory_block, "remember" in agent.toolmap, "Project memory" in prompts.build(off, agent)), ("", False, False))
        ro = self.session(permission="readonly")
        self.assertNotIn("remember", Agent(ro, model=ro.model, name="work").toolmap)        # plan mode writes nothing

    def test_facts_stay_honest_without_model_calls(self):
        first = self.session()
        shell = T.builtin()["shell"].fn
        shell(self.ctx(first), {"command": "python run_checks.py"})
        memory.save(first, {"name": "test-command", "kind": "command", "fact": "Rode os testes assim", "command": "python run_checks.py"}, "agent")
        memory.save(first, {"name": "tests-layout", "kind": "layout", "fact": "Testes em qa/", "paths": ["qa/check_loja.py"]}, "agent")

        s, seen = self.session(), []
        s.bus.subscribe(lambda ev: seen.append(ev) if ev["type"] == "memory" else None)
        shell(self.ctx(s), {"command": "python run_checks.py"})                            # it ran again and passed
        fact = next(f for f in memory.load(self.cwd) if f["name"] == "test-command")
        self.assertEqual((fact["confirmations"], fact["failures"], fact["_stale"]), (1, 0, ""))      # same day: already counted
        (self.cwd / "run_checks.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        shell(self.ctx(s), {"command": "python run_checks.py"})
        self.assertEqual(next(f for f in memory.load(self.cwd) if f["name"] == "test-command")["failures"], 1)
        self.assertIn("test-command", memory.block(self.cwd))                              # one failure can be the work in progress
        shell(self.ctx(s), {"command": "python run_checks.py"})
        self.assertEqual(seen[-1]["stale"], ["test-command"])
        self.assertNotIn("test-command", memory.block(self.cwd))                           # two in a row: out of the index
        self.assertIn("stale: its command failed", (memory.folder(self.cwd) / "MEMORY.md").read_text(encoding="utf-8"))
        (self.cwd / "run_checks.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        shell(self.ctx(s), {"command": "python run_checks.py"})                            # fixed: it is back, and confirmed once more
        fact = next(f for f in memory.load(self.cwd) if f["name"] == "test-command")
        self.assertEqual((fact["failures"], fact["confirmations"], fact["_stale"]), (0, 2, ""))

        (self.cwd / "qa" / "check_loja.py").unlink()                                       # the file a fact pointed at is gone
        self.assertNotIn("tests-layout", memory.block(self.cwd))
        self.assertEqual(next(f for f in memory.load(self.cwd) if f["name"] == "tests-layout")["_stale"], "missing: qa/check_loja.py")

        hand = memory.folder(self.cwd) / "moeda.md"                                        # written by a person, loosely
        hand.write_text("---\nname: Moeda\nkind: convention\nfact: Valores em centavos inteiros\n---\n\nNunca float.\n", encoding="utf-8")
        self.assertIn("- moeda (convention): Valores em centavos inteiros", memory.block(self.cwd))
        self.assertEqual(memory.forget(self.cwd, "moeda"), 1)
        self.assertEqual(memory.forget(self.cwd), 2)
        self.assertEqual((memory.load(self.cwd), memory.block(self.cwd)), ([], ""))

    def test_the_end_of_session_pass_runs_only_when_it_pays_and_goes_through_the_same_gate(self):
        reply = json.dumps([
            {"name": "test-command", "kind": "command", "fact": "Os testes rodam com run_checks.py", "command": "python run_checks.py"},
            {"name": "inventado", "kind": "command", "fact": "Build", "command": "make build"},                 # never ran: refused
            {"name": "tests-layout", "kind": "layout", "fact": "Testes em qa/", "paths": ["qa"]}])
        s = self.session(reply)
        shell = T.builtin()["shell"].fn
        self.assertEqual(memory.distill(s, {"status": "done"}), [])                        # nothing ran, nothing explored
        shell(self.ctx(s), {"command": "git status"})                                      # a look-around is not a project command
        self.assertEqual((memory.distill(s, {"status": "done"}), self.calls), ([], []))
        shell(self.ctx(s), {"command": "python run_checks.py"})
        s.files_seen.add("qa/check_loja.py")
        self.assertEqual(memory.distill(s, {"status": "error"}), [])                       # the session did not finish
        s.edits_since_run = True
        self.assertEqual((memory.distill(s, {"status": "done"}), self.calls), ([], []))   # edited after the last run: not verified
        s.edits_since_run = False
        self.assertEqual(memory.distill(s, {"status": "done"}), ["test-command", "tests-layout"])
        self.assertEqual(len(self.calls), 1)
        asked = self.calls[0][1]["content"]
        self.assertIn("- python run_checks.py", asked)
        self.assertNotIn("git status", asked)
        self.assertEqual([f["name"] for f in memory.load(self.cwd)], ["test-command", "tests-layout"])
        self.assertEqual(next(f for f in memory.load(self.cwd) if f["name"] == "test-command")["source"], "distilled")
        self.assertEqual(s.by_role["helper"]["calls"], 1)                                  # it shows on the bill

        self.assertIn("- qa/check_loja.py  # import unittest", asked)                      # the first line of each file seen

        again = self.session(reply)                                                        # next session: same command, known ground
        shell(self.ctx(again), {"command": "python run_checks.py"})
        again.files_seen.update({"qa/check_loja.py", "qa/outro.py", "run_checks.py", "README.md"})   # qa/ is covered by a fact
        self.assertEqual((memory.distill(again, {"status": "done"}), self.calls), ([], []))   # nothing new: no tokens spent
        again.files_seen.update({"src/a.py", "src/b.py"})                                  # three files outside what memory covers
        memory.distill(again, {"status": "done"})
        self.assertEqual(len(self.calls), 1)
        rich = self.session(reply)                                                         # a memory that is already rich: only a new command counts
        rich.files_seen.update({"x/a.py", "x/b.py", "x/c.py", "x/d.py"})
        shell(self.ctx(rich), {"command": "python run_checks.py"})
        real, memory.RICH = memory.RICH, 2
        try:
            self.assertEqual((memory.distill(rich, {"status": "done"}), self.calls), ([], []))
        finally:
            memory.RICH = real
        busy = self.session(reply)                                                         # the agent saved a fact itself: no second pass
        shell(self.ctx(busy), {"command": PASS})
        busy.memory_saved.append("algo")
        self.assertEqual((memory.distill(busy, {"status": "done"}), self.calls), ([], []))
        off = self.session(reply, memory=False)
        shell(self.ctx(off), {"command": "python run_checks.py"})
        self.assertEqual((memory.distill(off, {"status": "done"}), self.calls), ([], []))

    def test_the_memory_is_capped_and_the_least_confirmed_go_first(self):
        s = self.session()
        for i in range(memory.CAP + 3):
            (self.cwd / f"m{i}.txt").write_text("x", encoding="utf-8")
            self.assertTrue(memory.save(s, {"name": f"fato-{i:02d}", "kind": "layout", "fact": f"arquivo {i}", "paths": [f"m{i}.txt"]}, "agent")[0])
            if i == 0:                                                                     # saved again later: confirmed twice
                self.assertTrue(memory.save(s, {"name": "fato-00", "kind": "layout", "fact": "arquivo zero", "paths": ["m0.txt"]}, "agent")[0])
        names = [f["name"] for f in memory.load(self.cwd)]
        self.assertEqual(len(names), memory.CAP)
        self.assertIn("fato-00", names)
        self.assertNotIn("fato-01", names)
        self.assertLessEqual(len(memory.block(self.cwd)), memory.INDEX_CHARS + 300)


if __name__ == "__main__":
    unittest.main()
