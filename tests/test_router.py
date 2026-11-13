"""The model team (`model = "auto"`): who does which job, and how sub-agents get a cheaper or a stronger model. Offline."""
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


class StubCatalog:
    def __init__(self, known: dict):
        self.known = known

    def _load(self) -> dict:
        return self.known


class RouterTests(unittest.TestCase):
    def cfg(self, **over) -> dict:
        return {**config.load(Path(tempfile.mkdtemp())), **over}

    def test_the_default_team_pays_for_strength_only_where_it_matters(self):
        t = router.team(self.cfg(), StubCatalog(CATALOG))
        self.assertEqual(t, {"worker": "openai/gpt-6-luna", "light": "openai/gpt-6-luna", "deep": "openai/gpt-6.1-terra",
                             "planner": "openai/gpt-6.1-terra", "verifier": "anthropic/claude-haiku-5.5",
                             "escalation": "anthropic/claude-sonnet-5.5", "helper": "openai/gpt-6-luna", "perception": "meta/muse-ember"})
        self.assertNotEqual(t["verifier"].split("/")[0], t["worker"].split("/")[0])        # the reviewer is from another vendor
        self.assertEqual([r["role"] for r in router.describe(t)], list(router.ROLES))

    def test_missing_models_fall_through_the_roster_and_overrides_win(self):
        without = {k: v for k, v in CATALOG.items() if k not in ("openai/gpt-6-luna", "openai/gpt-6.1-terra")}
        t = router.team(self.cfg(), StubCatalog(without))
        self.assertEqual((t["worker"], t["deep"], t["planner"]), ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5.5"))
        self.assertEqual(t["verifier"], "anthropic/claude-haiku-5.5")                       # nothing from another vendor is left
        no_tools = {**CATALOG, "openai/gpt-6-luna": entry(0.1, tools=False)}
        self.assertEqual(router.team(self.cfg(), StubCatalog(no_tools))["worker"], "anthropic/claude-haiku-5.5")
        t = router.team(self.cfg(team={"worker": "anthropic/claude-sonnet-5.5", "deep": ["nao/existe", "anthropic/claude-sonnet-5.5"]}), StubCatalog(CATALOG))
        self.assertEqual((t["worker"], t["deep"]), ("anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5.5"))
        self.assertEqual(t["verifier"], "openai/gpt-6-luna")                               # still another vendor than the (new) worker
        self.assertEqual(router.team(self.cfg(), StubCatalog({}))["worker"], "openai/gpt-6-luna")   # offline: the roster as written

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
        t = router.apply(cfg, StubCatalog(CATALOG))
        self.assertEqual((cfg["planner_model"], t["planner"]), ("minha/planejadora", "minha/planejadora"))     # an explicit choice is kept
        self.assertEqual((cfg["verifier_model"], cfg["escalation_model"], cfg["helper_model"], cfg["perception_model"]),
                         ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "openai/gpt-6-luna", "meta/muse-ember"))
        cfg = self.cfg(team={"worker": "anthropic/claude-sonnet-5.5"})
        router.apply(cfg, StubCatalog(CATALOG))
        self.assertEqual(cfg["escalation_model"], "")                                      # nothing stronger than the worker itself

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
