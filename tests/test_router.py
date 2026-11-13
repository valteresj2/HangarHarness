"""The model team (`model = "auto"`): who does which job, and how sub-agents get a cheaper or a stronger model. Offline."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import config, router, tools as T  # noqa: E402
from hangar.agent import Agent  # noqa: E402
from hangar.session import Session  # noqa: E402


def entry(price: float, tools: bool = True, modalities=("text",)) -> dict:
    return {"context": 200000, "price_in": price, "price_out": price * 5, "modalities": list(modalities), "tools": tools, "name": "x"}


CATALOG = {
    "openai/gpt-6-luna": entry(0.1), "anthropic/claude-haiku-5.5": entry(0.1), "openai/gpt-6.1-terra": entry(1.0),
    "anthropic/claude-sonnet-5.5": entry(2.0), "meta/muse-ember": entry(0.1, modalities=("text", "image", "audio", "video")),
    "deepseek/deepseek-v4.1-flash-1017": entry(0.2),
}


def roster(**roles) -> dict:
    """A roster in the shape router.load() returns, with one evidence row for the first model of each role."""
    base = {"worker": ["openai/gpt-6-luna", "anthropic/claude-haiku-5.5", "deepseek/deepseek-v4.1-flash-1017", "openai/gpt-6.1-terra"],
            "light": ["openai/gpt-6-luna", "anthropic/claude-haiku-5.5", "meta/muse-ember"],
            "deep": ["openai/gpt-6.1-terra", "anthropic/claude-sonnet-5.5"], "planner": ["openai/gpt-6.1-terra", "anthropic/claude-sonnet-5.5"],
            "verifier": ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna", "openai/gpt-6.1-terra"],
            "escalation": ["anthropic/claude-sonnet-5.5", "openai/gpt-6.1-terra"],
            "helper": ["openai/gpt-6-luna", "anthropic/claude-haiku-5.5"], "perception": ["meta/muse-ember"], **roles}
    return {"roles": base, "generated": "2026-11-13", "source": "test",
            "evidence": {r: {v[0]: {"model": v[0], "solved": 20, "runs": 20, "cost_per_solved": 0.0015}} for r, v in base.items()}}


R = roster()


class StubCatalog:
    def __init__(self, known: dict):
        self.known = known

    def _load(self) -> dict:
        return self.known


class RouterTests(unittest.TestCase):
    def cfg(self, **over) -> dict:
        return {**config.load(Path(tempfile.mkdtemp())), **over}

    def test_the_default_team_pays_for_strength_only_where_it_matters(self):
        t = router.team(self.cfg(), StubCatalog(CATALOG), R)
        self.assertEqual(t, {"worker": "openai/gpt-6-luna", "light": "openai/gpt-6-luna", "deep": "openai/gpt-6.1-terra",
                             "planner": "openai/gpt-6.1-terra", "verifier": "anthropic/claude-haiku-5.5",
                             "escalation": "anthropic/claude-sonnet-5.5", "helper": "openai/gpt-6-luna", "perception": "meta/muse-ember"})
        self.assertNotEqual(t["verifier"].split("/")[0], t["worker"].split("/")[0])        # the reviewer is from another vendor
        self.assertEqual([r["role"] for r in router.describe(t, R)], list(router.ROLES))

    def test_missing_models_fall_through_the_roster_and_overrides_win(self):
        without = {k: v for k, v in CATALOG.items() if k not in ("openai/gpt-6-luna", "openai/gpt-6.1-terra")}
        t = router.team(self.cfg(), StubCatalog(without), R)
        self.assertEqual((t["worker"], t["deep"], t["planner"]), ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5.5"))
        self.assertEqual(t["verifier"], "anthropic/claude-haiku-5.5")                       # nothing from another vendor is left
        no_tools = {**CATALOG, "openai/gpt-6-luna": entry(0.1, tools=False)}
        self.assertEqual(router.team(self.cfg(), StubCatalog(no_tools), R)["worker"], "anthropic/claude-haiku-5.5")
        t = router.team(self.cfg(team={"worker": "anthropic/claude-sonnet-5.5", "deep": ["nao/existe", "anthropic/claude-sonnet-5.5"]}), StubCatalog(CATALOG), R)
        self.assertEqual((t["worker"], t["deep"]), ("anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5.5"))
        self.assertEqual(t["verifier"], "openai/gpt-6-luna")                               # still another vendor than the (new) worker
        self.assertEqual(router.team(self.cfg(), StubCatalog({}), R)["worker"], "openai/gpt-6-luna")   # offline: the roster as written

    def test_a_private_provider_uses_its_own_model_for_every_role(self):
        cfg = self.cfg(default_provider="ollama", model="qwen3")
        self.assertEqual(set(router.team(cfg, StubCatalog({})).values()), {"qwen3"})
        cfg = self.cfg(default_provider="ollama", model="auto", team={"worker": "qwen3", "deep": "qwen3-big"})
        t = router.team(cfg, StubCatalog({}))
        self.assertEqual((t["worker"], t["deep"], t["light"]), ("qwen3", "qwen3-big", "qwen3"))
        with self.assertRaises(ValueError):
            router.team(self.cfg(default_provider="ollama", model="auto"), StubCatalog({}))

    def test_apply_fills_the_roles_the_user_left_open(self):
        cfg = self.cfg(planner_model="minha/planejadora")
        t = router.apply(cfg, StubCatalog(CATALOG), R)
        self.assertEqual((cfg["planner_model"], t["planner"]), ("minha/planejadora", "minha/planejadora"))     # an explicit choice is kept
        self.assertEqual((cfg["verifier_model"], cfg["escalation_model"], cfg["helper_model"], cfg["perception_model"]),
                         ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "openai/gpt-6-luna", "meta/muse-ember"))
        cfg = self.cfg(team={"worker": "anthropic/claude-sonnet-5.5"})
        router.apply(cfg, StubCatalog(CATALOG), R)
        self.assertEqual(cfg["escalation_model"], "")                                      # nothing stronger than the worker itself

    def test_the_roster_comes_from_benchmark_results(self):
        sys.path.insert(0, str(ROOT / "bench"))
        import roster as gen
        d = Path(tempfile.mkdtemp(prefix="hangar_roster_"))

        def rows(model, cost, fail=(), tasks=None, label=None, workflow="loop"):
            names = tasks or [t for tier in gen.TIERS.values() for t in tier]
            return [{"harness": "hangar", "label": label or model, "model": model, "workflow": workflow, "task": t, "ok": t not in fail, "cost": cost} for t in names]

        (d / "a.json").write_text(json.dumps(rows("barato/x", 0.001, fail=("tinylang",)) + rows("forte/y", 0.02) + rows("medio/z", 0.005)
                                             + rows("quebra/w", 0.0001, fail=("bugfix",)) + rows("sentidos/p", 0.002, tasks=gen.TIERS["core"] + gen.TIERS["media"])
                                             + rows("variante/v", 0.00001, label="variante/v [verify]", workflow="verify")), encoding="utf-8")
        (d / "b.json").write_text((d / "a.json").read_text(encoding="utf-8"), encoding="utf-8")          # two runs of everything
        data = gen.collect([str(d / "a.json"), str(d / "b.json")])
        self.assertNotIn("variante/v", data)                                               # only plain loop runs count
        roles = gen.build(data, 2, {"sentidos/p": ["text", "image", "audio", "video"], "barato/x": ["text", "image"]})
        order = {r: [x["model"] for x in v] for r, v in roles.items()}
        self.assertEqual(order["worker"], ["barato/x", "medio/z", "forte/y"])               # cheapest that cleared core, media and hard
        self.assertEqual(order["deep"], ["medio/z", "forte/y"])                             # the cheap one failed the hardest task
        self.assertEqual(order["deep"], order["escalation"])
        self.assertEqual(order["light"][0], "barato/x")
        self.assertNotIn("quebra/w", order["light"])                                        # one failure in a needed tier keeps a model out
        self.assertEqual(order["perception"], ["sentidos/p"])                               # must take image, audio and video itself
        self.assertEqual((roles["worker"][0]["solved"], roles["worker"][0]["runs"], roles["worker"][0]["cost_per_solved"]), (20, 20, 0.001))
        self.assertEqual(gen.build(gen.collect([str(d / "a.json")]), 2, {})["worker"], [])  # one run per task is not evidence yet

        doc = {"generated": "2026-11-13", "roles": roles}
        (d / "mine.json").write_text(json.dumps(doc), encoding="utf-8")
        (d / "broken.json").write_text(json.dumps({"roles": {"worker": roles["worker"]}}), encoding="utf-8")
        mine = router.load([d / "nao-existe.json", d / "broken.json", d / "mine.json"])        # the first complete file wins
        self.assertEqual((mine["roles"]["worker"][0], mine["source"]), ("barato/x", str(d / "mine.json")))
        self.assertEqual(router.load([d / "broken.json"])["source"], "builtin")
        t = router.team(self.cfg(), StubCatalog({}), mine)
        self.assertEqual((t["worker"], t["deep"], t["verifier"]), ("barato/x", "medio/z", "medio/z"))    # reviewer from another vendor
        row = router.describe(t, mine)[0]
        self.assertEqual(row["evidence"], "20/20 execuções resolvidas · US$ 0.0010 por tarefa resolvida")

        shipped = router.load([router.SHIPPED])                                            # the file we ship is complete and current
        self.assertEqual(shipped["source"], str(router.SHIPPED))
        self.assertEqual(set(shipped["roles"]), set(router.ROLES))
        self.assertTrue(all(shipped["evidence"][r][shipped["roles"][r][0]]["runs"] >= 2 for r in router.ROLES))

    def test_the_bill_says_which_role_spent_what(self):
        cwd = Path(tempfile.mkdtemp(prefix="hangar_bill_")).resolve()
        s = Session(config.load(cwd), cwd, model="base")
        self.addCleanup(s.bus.close)

        class Reply:
            ms, finish = 5, "stop"

            def __init__(self, cost):
                self.usage = {"cost": cost, "prompt": 100, "completion": 10, "cached": 40}

        main = Agent(s, model="base", name="work")
        self.assertEqual(main.cost_role, "worker")
        s.add_usage(Reply(0.002), "base", "work", main.cost_role)
        before = {k: dict(v) for k, v in s.by_role.items()}
        main.escalated = True
        s.add_usage(Reply(0.03), "forte", "work", main.cost_role)
        sub = Agent(s, model="barato", role="sub", name="sub1")
        self.assertEqual(sub.cost_role, "sub")
        sub.level = "light"
        s.add_usage(Reply(0.0004), "barato", "sub1", sub.cost_role)
        s.add_usage(Reply(0.001), "rev", "review1", Agent(s, model="rev", role="verifier", name="review1").cost_role)
        s.add_usage(Reply(0.0001), "aux", "compactor")
        s.add_usage(Reply(0.0002), "olhos", "perception")
        self.assertEqual([(r["role"], r["cost"], r["calls"], r["models"]) for r in s.roles()], [
            ("escalation", 0.03, 1, ["forte"]), ("worker", 0.002, 1, ["base"]), ("verifier", 0.001, 1, ["rev"]),
            ("light", 0.0004, 1, ["barato"]), ("perception", 0.0002, 1, ["olhos"]), ("helper", 0.0001, 1, ["aux"])])
        self.assertEqual([r["role"] for r in s.roles(before)], ["escalation", "verifier", "light", "perception", "helper"])   # only what came after
        self.assertAlmostEqual(sum(r["cost"] for r in s.roles()), s.totals["cost"])                 # the roles add up to the bill
        self.assertEqual(json.loads((s.dir / "meta.json").read_text(encoding="utf-8"))["by_role"]["worker"]["calls"], 1)

    def test_a_session_on_auto_routes_its_sub_agents_by_level(self):
        cwd = Path(tempfile.mkdtemp(prefix="hangar_team_")).resolve()
        (cwd / "hangar.toml").write_text('default_provider = "local"\nmodel = "base"\n[providers.local]\nbase_url = "http://127.0.0.1:9/v1"\napi_key_env = ""\n'
                                         '[team]\nlight = "barato"\ndeep = "forte"\nescalation = "forte"\n', encoding="utf-8")
        s = Session(config.load(cwd), cwd, model="auto")
        self.addCleanup(s.bus.close)
        self.assertEqual((s.model, s.team["light"], s.team["deep"], s.cfg["escalation_model"]), ("base", "barato", "forte", "forte"))
        main = Agent(s, model=s.model, name="work")
        seen, made = [], []
        s.bus.subscribe(lambda ev: seen.append(ev) if ev["type"] == "subagent" else None)

        class FakeSub:
            def __init__(self, session, model, **kw):
                made.append(model)

            def run(self, prompt):
                return "relatorio"

        import hangar.agent as agent_mod
        real, agent_mod.Agent = agent_mod.Agent, FakeSub
        try:
            task = T.builtin()["task"].fn
            for level in ("light", "deep", "standard", None, "inventado"):
                self.assertEqual(task(T.Ctx(s, main), {"prompt": "x", **({"level": level} if level else {})}), "relatorio")
        finally:
            agent_mod.Agent = real
        self.assertEqual(made, ["barato", "forte", "base", "base", "base"])
        self.assertEqual([(e["agent"], e["model"], e["level"]) for e in seen][:2], [("sub1", "barato", "light"), ("sub2", "forte", "deep")])
        self.assertIn("level", T.builtin()["task"].parameters["properties"])

        fixed = Session(config.load(cwd), cwd, model="base")                               # an explicit model: no team, no routing
        self.addCleanup(fixed.bus.close)
        self.assertIsNone(fixed.team)
        made.clear()
        agent_mod.Agent = FakeSub
        try:
            T.builtin()["task"].fn(T.Ctx(fixed, Agent(fixed, model="base", name="work")), {"prompt": "x", "level": "deep"})
        finally:
            agent_mod.Agent = real
        self.assertEqual(made, ["base"])


if __name__ == "__main__":
    unittest.main()
