"""run_workflow: a plan of sub-agents in one call. The model is faked; what is tested is the harness around it."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hangar import config, tools as T, workflow as W  # noqa: E402
from hangar.session import Session  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_w_")).resolve()
        for n in (1, 2, 3):
            (self.tmp / f"doc{n}.txt").write_text(f"valor {n}00", encoding="utf-8")
        self.asked: list[str] = []

    def session(self, answer, **cfg) -> Session:
        s = Session({**config.load(self.tmp), "workflows": True, "lessons": False, "memory": False, **cfg}, self.tmp, task="resumir os documentos")
        self.addCleanup(s.bus.close)

        def chat(model, messages, *a, **k):
            last = next(m["content"] for m in reversed(messages) if m["role"] == "user")
            last = last if isinstance(last, str) else " ".join(p.get("text", "") for p in last)
            self.asked.append(last)
            return SimpleNamespace(content=answer(last), usage={"prompt": 10, "completion": 5, "cost": 0.0}, ms=1, finish="stop",
                                   model=model, tool_calls=[], reasoning="")
        s.llm.chat = chat
        return s

    def parent(self, s):
        return SimpleNamespace(model=s.model, name="work")

    def test_it_is_opt_in_and_only_for_the_main_agent(self):
        s = self.session(lambda q: "ok")
        names = lambda role, toolset="all": [t.name for t in T.select(s, toolset, "standard", role)]  # noqa: E731
        self.assertIn("run_workflow", names("main"))
        self.assertNotIn("run_workflow", names("sub"))                                   # sub-agents are leaves
        self.assertNotIn("run_workflow", names("main", "readonly"))
        s.cfg["workflows"] = False
        self.assertNotIn("run_workflow", names("main"))

    def test_a_wrong_plan_costs_nothing(self):
        s = self.session(lambda q: "ok")
        bad = [
            [],
            [{"type": "map", "over": [1], "prompt": "sem o marcador"}],
            [{"type": "map", "prompt": "leia {item}"}],
            [{"type": "agent", "prompt": "resuma {later}"}, {"id": "later", "type": "shell", "command": "echo 1"}],
            [{"id": "a", "type": "shell", "command": "echo 1"}, {"id": "a", "type": "shell", "command": "echo 2"}],
            [{"type": "dance"}],
            [{"type": "map", "over": "glob:*.nothing", "prompt": "leia {item}"}],
            [{"type": "map", "over": list(range(41)), "prompt": "leia {item}"}],
        ]
        for plan in bad:
            with self.assertRaises(W.PlanError, msg=plan):
                W.run(s, self.parent(s), plan)
        with self.assertRaises(W.PlanError):
            W.run(s, self.parent(s), [{"type": "shell", "command": "echo 1"}], save="../fora.json")
        self.assertEqual((self.asked, W._state(s)["calls"]), ([], 0))
        ctx = SimpleNamespace(session=s, agent=self.parent(s))
        with self.assertRaises(T.ToolError):
            T.t_run_workflow(ctx, {"steps": "nope"})

    def test_map_then_shell_keeps_the_results_out_of_the_account(self):
        def answer(q):
            n = next(c for c in q if c.isdigit())
            return f'Li o arquivo.\n{{"valor": {n}00, "nota": "doc {n}"}}'
        s = self.session(answer)
        merge = self.tmp / "merge.py"
        merge.write_text("import json, sys\nrows = json.load(open(sys.argv[1], encoding='utf-8'))\n"
                         "print(sum(r['result']['valor'] for r in rows))\n", encoding="utf-8")
        plan = [{"id": "ler", "type": "map", "over": "glob:doc*.txt", "prompt": "Leia {item} e diga o valor.",
                 "fields": {"valor": "inteiro", "nota": "texto curto"}},
                {"id": "soma", "type": "shell", "command": f'"{sys.executable}" merge.py "{{ler.path}}"'}]
        out = W.run(s, self.parent(s), plan)
        self.assertIn("3 of 3 items done", out)
        self.assertIn("600", out)                                                         # the shell step read the map's output from its file
        self.assertEqual(len(self.asked), 3)
        self.assertTrue(all("exactly these keys" in q and "valor: inteiro" in q for q in self.asked))
        rows = json.loads((s.dir / "workflow" / "run1" / "ler.json").read_text(encoding="utf-8"))
        self.assertEqual([r["item"] for r in rows], ["doc1.txt", "doc2.txt", "doc3.txt"])
        self.assertEqual(rows[1]["result"], {"valor": 200, "nota": "doc 2"})
        W.run(s, self.parent(s), plan[:1], save="resumo.json")                            # the same asks again: served from the cache
        self.assertEqual((len(self.asked), W._state(s)["calls"]), (3, 3))
        self.assertEqual(json.loads((self.tmp / "resumo.json").read_text(encoding="utf-8"))["doc3.txt"]["valor"], 300)

    def test_failures_stay_local_and_the_budget_holds(self):
        def answer(q):
            if "doc2" in q or "exactly these keys: valor" in q:
                return "não sei responder em JSON"
            return '{"valor": 1}'
        s = self.session(answer, workflow_max_calls=4)
        plan = [{"id": "ler", "type": "map", "over": "glob:doc*.txt", "prompt": "Leia {item}.", "fields": {"valor": "inteiro"}},
                {"id": "sintese", "type": "agent", "prompt": "Resuma: {ler}"}]
        out = W.run(s, self.parent(s), plan)
        self.assertIn("2 of 3 items done, 1 FAILED", out)
        self.assertIn("doc2.txt", out)
        self.assertIn("sintese (agent)", out)                                             # one bad item does not sink the plan
        self.assertIn("4 of 4", out)
        more = W.run(s, self.parent(s), [{"type": "map", "over": ["a", "b"], "prompt": "Outra pergunta sobre {item}."}])
        self.assertIn("0 of 2 items done, 2 FAILED", more)                                # the session's allowance is spent
        self.assertIn("budget", more)

    def test_a_failing_shell_step_stops_the_plan(self):
        s = self.session(lambda q: "relatório")
        out = W.run(s, self.parent(s), [{"id": "gate", "type": "shell", "command": f'"{sys.executable}" -c "import sys; sys.exit(3)"'},
                                        {"id": "depois", "type": "agent", "prompt": "nunca roda"}])
        self.assertIn("exit 3", out)
        self.assertIn("stopped here", out)
        self.assertEqual(self.asked, [])


if __name__ == "__main__":
    unittest.main()
