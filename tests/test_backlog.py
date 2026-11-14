"""Project backlog: a task is done only when the harness itself sees its acceptance command pass, and nothing
done before may break. Offline: the sessions are stand-ins that edit files the way an agent would."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import backlog, config, runner  # noqa: E402

CHECK = "import pathlib, sys\nsys.exit(0 if pathlib.Path('{name}.txt').is_file() else 3)\n"


def task(tid, deps=(), accept=None):
    return {"id": tid, "title": f"Fazer {tid}", "brief": f"Crie {tid}.txt", "accept": accept or f"python check_{tid}.py", "deps": list(deps)}


class BacklogTests(unittest.TestCase):
    def setUp(self):
        self.cwd = Path(tempfile.mkdtemp(prefix="hangar_backlog_")).resolve()
        for name in ("a", "b", "c"):
            (self.cwd / f"check_{name}.py").write_text(CHECK.format(name=name), encoding="utf-8")
        self.cfg = config.load(self.cwd)
        self.sessions: list = []                       # (kind, prompt or feedback)
        self.script: list = []                         # what each session does to the project, in order
        real = runner.run_task, runner.resume_task
        runner.run_task, runner.resume_task = self.fake_run, self.fake_resume
        self.addCleanup(lambda: setattr(runner, "run_task", real[0]) or setattr(runner, "resume_task", real[1]))

    def act(self, kind, text, sid):
        self.sessions.append((kind, text))
        step = self.script.pop(0) if self.script else {}
        for name in step.get("make", []):
            (self.cwd / f"{name}.txt").write_text("x", encoding="utf-8")
        for name in step.get("drop", []):
            (self.cwd / f"{name}.txt").unlink()
        return {"session": sid, "status": step.get("status", "done"), "cost": step.get("cost", 0.01), "final": "feito"}

    def fake_run(self, cfg, prompt, cwd, **kw):
        return self.act("run", prompt, f"s{sum(k == 'run' for k, _ in self.sessions) + 1}")

    def fake_resume(self, cfg, sid, extra="", **kw):
        return self.act("resume", extra, sid)

    def store(self, *tasks):
        backlog.save(self.cwd, {"goal": "Montar a loja", "tasks": backlog.clean(list(tasks))})

    def status(self):
        return {t["id"]: t["status"] for t in backlog.load(self.cwd)["tasks"]}

    def run_all(self, **kw):
        return backlog.run(self.cfg, self.cwd, log=lambda line: None, **kw)

    def test_a_backlog_must_be_runnable_and_safe_before_it_is_stored(self):
        self.assertEqual(backlog.validate(backlog.clean([task("a"), task("b", ["a"])])), [])
        for tasks, why in (([task("a"), task("a")], "duplicate id"),
                           ([task("a", ["zz"])], "unknown task 'zz'"),
                           ([task("a", ["b"]), task("b", ["a"])], "cycle"),
                           ([{**task("a"), "accept": ""}], "needs an acceptance command"),
                           ([task("a", accept="rm -rf /")], "destructive-command rule"),
                           ([task("a", accept="taskkill /F /IM python.exe")], "destructive-command rule"),
                           ([{**task("a"), "brief": ""}], "needs a title and a brief"),
                           ([], "no tasks")):
            self.assertTrue(any(why in e for e in backlog.validate(backlog.clean(tasks))), (why, backlog.validate(backlog.clean(tasks))))
        reply = 'Aqui está:\n```json\n[{"id": "Base do Projeto", "title": "Base", "brief": "Crie a base", "accept": "python check_a.py", "deps": []},' \
                ' {"id": "b", "title": "B", "brief": "Faça b", "accept": "python check_b.py", "deps": ["Base do Projeto"], "status": "done"}]\n```'
        tasks = backlog.parse(reply)
        self.assertEqual([(t["id"], t["deps"], t["status"]) for t in tasks], [("base-do-projeto", [], "pending"), ("b", ["base-do-projeto"], "pending")])

        real = backlog._propose
        self.addCleanup(lambda: setattr(backlog, "_propose", real))
        backlog._propose = lambda *a: ('[{"id": "a", "title": "A", "brief": "x", "accept": "sudo make install"}]', {"status": "done", "cost": 0.02, "session": "p1"})
        res = backlog.plan(self.cfg, self.cwd, "Montar a loja")
        self.assertEqual((res["ok"], backlog.load(self.cwd), res["cost"]), (False, None, 0.04))   # asked twice; a bad plan is never written
        same = reply.replace("python check_b.py", "python check_a.py")                     # one command for every task: the second proves nothing
        asked: list = []
        backlog._propose = lambda cfg, cwd, goal, *a: (asked.append(goal) or (same if len(asked) == 1 else reply), {"status": "done", "cost": 0.02, "session": "p1"})
        self.assertTrue(backlog.plan(self.cfg, self.cwd, "Montar a loja")["ok"])
        self.assertIn("b: same acceptance command as 'base-do-projeto'", asked[1])          # the planner is told why and fixes it
        self.assertEqual([t["accept"] for t in backlog.load(self.cwd)["tasks"]], ["python check_a.py", "python check_b.py"])
        backlog.path(self.cwd).unlink()
        backlog._propose = lambda *a: (reply, {"status": "done", "cost": 0.02, "session": "p1"})
        self.assertTrue(backlog.plan(self.cfg, self.cwd, "Montar a loja")["ok"])
        data = backlog.load(self.cwd)
        self.assertEqual((data["goal"], data["plan_cost"], len(data["tasks"])), ("Montar a loja", 0.02, 2))

    def test_only_the_harness_running_the_command_makes_a_task_done(self):
        self.store(task("a"), task("b", ["a"]), task("c", ["b"]))
        self.script = [{"make": ["a"]},                 # a: accepted at the first check
                       {},                              # b: the agent says "feito" and did nothing
                       {"make": ["b"]},                 # b: fixed after the harness sent the failure back
                       {"make": ["c"], "drop": ["a"]},  # c: works, but breaks what a had built
                       {"make": ["a"]}]                 # c: repaired
        res = self.run_all()
        self.assertEqual((res["stop"], res["ran"], res["done"], res["failed"]), ("all done", ["a", "b", "c"], 3, []))
        self.assertEqual([k for k, _ in self.sessions], ["run", "run", "resume", "run", "resume"])
        first, second = self.sessions[0][1], self.sessions[1][1]
        self.assertIn("YOUR TASK (a): Fazer a", first)
        self.assertIn("python check_a.py", first)
        self.assertNotIn("Already done", first)
        self.assertIn("Already done by earlier sessions:\n- a: Fazer a", second)             # the next session knows what exists
        self.assertIn("`python check_b.py` failed", self.sessions[2][1])
        self.assertIn("[exit 3]", self.sessions[2][1])
        self.assertIn("`python check_a.py` passed before your work and now fails (task a: Fazer a)", self.sessions[4][1])
        tasks = {t["id"]: t for t in backlog.load(self.cwd)["tasks"]}
        self.assertEqual([(t["attempts"], t["cost"], t["sessions"]) for t in tasks.values()],
                         [(1, 0.01, ["s1"]), (2, 0.01, ["s2"]), (2, 0.01, ["s3"])])          # a resumed session reports its running total
        self.assertEqual(res["cost"], 0.03)
        self.assertEqual(self.run_all()["stop"], "all done")                                 # nothing left: no session starts
        self.assertEqual(len(self.sessions), 5)
        (self.cwd / "b.txt").unlink()                                                        # someone breaks b later, by hand
        self.assertEqual([(t["id"], ok) for t, ok, _ in backlog.audit(self.cfg, self.cwd)], [("a", True), ("b", False), ("c", True)])

    def test_a_task_that_never_passes_fails_and_holds_back_what_depends_on_it(self):
        self.store(task("a"), task("b", ["a"]), task("c"))
        self.script = [{}, {}, {}, {"make": ["c"]}]      # a never gets built; c is independent
        res = self.run_all()
        self.assertEqual(self.status(), {"a": "failed", "b": "pending", "c": "done"})
        self.assertEqual((res["stop"], res["failed"], res["blocked"], res["ran"]), ("nothing ready", ["a"], ["b"], ["a", "c"]))
        self.assertEqual([k for k, _ in self.sessions], ["run", "resume", "resume", "run"])   # three checks, then on to what can still move
        self.assertIn("[exit 3]", backlog.load(self.cwd)["tasks"][0]["output"])              # why it failed stays on disk

    def test_limits_stop_the_run_and_the_next_run_picks_up_where_it_stopped(self):
        self.store(task("a"), task("b", ["a"]), task("c", ["b"]))
        self.script = [{"make": ["a"]}]
        self.assertEqual(self.run_all(max_tasks=1)["stop"], "task limit")
        self.assertEqual(self.status(), {"a": "done", "b": "pending", "c": "pending"})
        self.script = [{"make": ["b"], "cost": 0.5}]
        res = self.run_all(budget=0.3)                                                       # b spends past the budget: c does not start
        self.assertEqual((res["stop"], res["ran"], res["cost"]), ("budget", ["b"], 0.5))
        self.script = [{"status": "error"}]
        res = self.run_all()
        self.assertEqual((res["stop"], self.status()["c"]), ("session error", "pending"))    # a session that could not run decides nothing
        self.assertEqual(backlog.load(self.cwd)["tasks"][2]["attempts"], 0)
        (self.cwd / "c.txt").write_text("x", encoding="utf-8")                               # the check already passes before any work
        self.script = [{}]
        self.run_all()
        c = backlog.load(self.cwd)["tasks"][2]
        self.assertEqual((c["status"], c["weak"]), ("done", True))                           # accepted, and flagged as a weak check
        self.assertEqual(json.loads(backlog.path(self.cwd).read_text(encoding="utf-8"))["goal"], "Montar a loja")


if __name__ == "__main__":
    unittest.main()
