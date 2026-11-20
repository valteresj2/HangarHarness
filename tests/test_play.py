"""Playing a page: `hangar studio play`, the web-game skill and the "you never opened that page" gate.
Offline; the browser tests are skipped on a machine without Chrome/Edge."""
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import browser, config, skills, studio, tools as T  # noqa: E402
from hangar.session import Session  # noqa: E402

GAME = """<html><body style='margin:0;background:#102'><canvas id='c' width='640' height='360'></canvas><script>
const G = {x: 40, hits: 0, scene: 'title'};
const held = {};
addEventListener('keydown', e => { held[e.code] = true; if (e.code === 'Enter') G.scene = 'fight'; if (e.code === 'Numpad7') G.hits++; });
addEventListener('keyup', e => { held[e.code] = false; });
const ctx = document.getElementById('c').getContext('2d');
function frame() {
  if (G.scene === 'fight' && held.ArrowRight) G.x += 4;
  ctx.fillStyle = '#203050'; ctx.fillRect(0, 0, 640, 360);
  if (G.scene === 'fight') { ctx.fillStyle = '#e33'; ctx.fillRect(G.x, 120, 90, 200); ctx.fillStyle = '#fc0'; ctx.fillRect(G.x + 20, 80, 50, 50); }
  else { ctx.fillStyle = '#fff'; ctx.font = '40px sans-serif'; ctx.fillText('PRESS ENTER', 180, 180); }
  requestAnimationFrame(frame);
}
frame();
</script></body></html>"""


def play(*argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = studio.main(["play", *argv])
    return code, out.getvalue()


class PixelTests(unittest.TestCase):
    def test_key_names_people_type_become_dom_codes(self):
        self.assertEqual([browser.keycode(k) for k in ("a", "7", "left", "enter", "numpad7", "ArrowUp", "esc", "f3")],
                         ["KeyA", "Digit7", "ArrowLeft", "Enter", "Numpad7", "ArrowUp", "Escape", "F3"])
        self.assertEqual(browser.keyinfo("Numpad7"), ("7", 103, "7"))
        self.assertEqual(browser.keyinfo("ArrowLeft")[1], 37)
        with self.assertRaises(browser.BrowserError):
            browser.keyinfo("Banana")

    def test_png_thumbnail_is_decoded_and_judged_without_a_model(self):
        def png(w, h, pixel):
            raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
            def chunk(kind, body):
                return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
            return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
        w, h, flat = browser.png_rgb(png(8, 4, lambda x, y: (10, 20, 30)))
        self.assertEqual((w, h, flat[:3], len(flat)), (8, 4, bytes((10, 20, 30)), 96))
        self.assertGreater(browser.look(flat)["flat"], 0.99)                               # one colour: a blank screen
        _, _, busy = browser.png_rgb(png(8, 4, lambda x, y: (x * 30, y * 60, 200)))
        self.assertGreater(browser.look(busy)["colours"], 8)
        self.assertEqual(browser.differ(flat, flat), 0.0)
        self.assertGreater(browser.differ(flat, busy), 0.9)


class PlayTests(unittest.TestCase):
    def setUp(self):
        if not browser.find_browser():
            self.skipTest("no Chrome/Edge on this machine")
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_play_")).resolve()
        self.page = self.tmp / "index.html"
        self.page.write_text(GAME, encoding="utf-8")

    def test_keys_reach_the_page_and_shots_and_state_are_reported(self):
        code, out = play(str(self.page), str(self.tmp / "shots"), "--width", "640", "--height", "360", "--do",
                         "shot title; press Enter; wait 100; shot fight; hold ArrowRight 400; press Numpad7; shot moved; "
                         "expect G.x > 60 && G.hits === 1; eval G.scene")
        self.assertEqual(code, 0, out)
        self.assertIn('"fight"', out)
        self.assertIn("no console errors", out)
        for name in ("title", "fight", "moved"):
            self.assertEqual((self.tmp / "shots" / f"{name}.png").read_bytes()[:4], b"\x89PNG")

    def test_dead_keys_blank_screens_and_broken_rules_fail_the_run(self):
        code, out = play(str(self.page), str(self.tmp / "s"), "--width", "640", "--height", "360", "--do",
                         "press Enter; wait 100; shot a; press KeyQ; shot b")              # a key the game ignores
        self.assertEqual(code, 1)
        self.assertIn("IDENTICAL to 'a'", out)
        code, out = play(str(self.page), str(self.tmp / "s"), "--do", "expect G.hits > 3")
        self.assertEqual(code, 1)
        self.assertIn("EXPECT FAILED", out)
        blank = self.tmp / "blank.html"
        blank.write_text("<html><body style='background:#000'><script>undefinedFunction()</script></body></html>", encoding="utf-8")
        code, out = play(str(blank), str(self.tmp / "s"), "--do", "shot x")
        self.assertEqual(code, 1)
        self.assertIn("BLANK", out)
        self.assertIn("undefinedFunction", out)                                            # the console error that explains it
        self.assertEqual(play(str(self.page), str(self.tmp / "s"), "--do", "dance wildly")[0], 2)


class PageGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_pg_")).resolve()
        self.s = Session(config.load(self.tmp), self.tmp)

    def tearDown(self):
        self.s.finish("done")

    def test_the_game_skill_ships_and_names_play_as_its_check(self):
        found = skills.discover(self.tmp)
        self.assertEqual(found["web-game"]["gate"], "studio play")
        self.assertLessEqual(len(found["web-game"]["description"]), 160)                   # the index line is not cut mid-word

    def test_a_task_that_is_a_game_is_pointed_at_the_skill(self):
        found = skills.discover(self.tmp)
        self.assertIn("`web-game`", skills.suggest(found, "Construa um jogo de luta 2D para navegador"))
        self.assertIn("`web-game`", skills.suggest(found, "build a small platformer GAME"))
        self.assertEqual(skills.suggest(found, "corrija o bug do relatório de vendas"), "")
        self.assertEqual(skills.suggest(found, "explain game-theory payoffs in this csv"), "")      # part of another word
        self.assertEqual(skills.suggest(found, "faça um jogo", loaded={"web-game"}), "")            # already loaded: say nothing

    def test_a_changed_page_nobody_opened_sends_the_agent_back_once(self):
        from hangar.agent import Agent
        from hangar.llm import Reply
        if not browser.find_browser():
            self.skipTest("no Chrome/Edge on this machine")
        self.s.cfg["tiers"]["forte/x"] = "strong"
        self.s.cfg.setdefault("model_info", {})["forte/x"] = {"tools": True}
        seen, n = [], {"i": 0}

        def chat(model, messages, **k):
            seen.append(json.dumps(messages[-1], ensure_ascii=False, default=str))
            n["i"] += 1
            r = Reply(content="", finish="tool_calls", usage={"prompt": 5, "completion": 5, "cost": 0.0}, model=model)
            if n["i"] == 1:
                r.tool_calls = [{"id": "c1", "name": "write", "arguments": json.dumps({"path": "index.html", "content": "<html><body>oi</body></html>"})}]
                return r
            if n["i"] == 3:                                                                # sent back: now it opens the page
                r.tool_calls = [{"id": "c3", "name": "shell", "arguments": json.dumps({"command": "python -m hangar studio check index.html"})}]
                return r
            return Reply(content=f"pronto {n['i']}", finish="stop", usage={"prompt": 5, "completion": 5, "cost": 0.0}, model=model)
        self.s.llm.chat = chat
        self.assertEqual(Agent(self.s, model="forte/x", name="w").run("faça a página"), "pronto 4")
        self.assertEqual(sum("never opened it in a browser" in m for m in seen), 1)        # asked once, and a strong model too
        self.assertEqual(self.s.page_unseen, "")

    def scripted(self, replies):
        """A strong model that answers with `replies` in order: a dict is one tool call, a string a final answer."""
        from hangar.agent import Agent
        from hangar.llm import Reply
        self.s.cfg["tiers"]["forte/x"] = "strong"
        self.s.cfg.setdefault("model_info", {})["forte/x"] = {"tools": True}
        seen, n = [], {"i": 0}

        def chat(model, messages, **k):
            seen.append(json.dumps(messages[-1], ensure_ascii=False, default=str))
            step = replies[min(n["i"], len(replies) - 1)]
            n["i"] += 1
            if isinstance(step, str):
                return Reply(content=step, finish="stop", usage={"prompt": 5, "completion": 5, "cost": 0.0}, model=model)
            r = Reply(content="", finish="tool_calls", usage={"prompt": 5, "completion": 5, "cost": 0.0}, model=model)
            r.tool_calls = [{"id": f"c{n['i']}", "name": step["tool"], "arguments": json.dumps(step["args"])}]
            return r
        self.s.llm.chat = chat
        return Agent(self.s, model="forte/x", name="w"), seen

    def test_a_program_written_and_never_run_sends_the_agent_back_once(self):
        agent, seen = self.scripted([{"tool": "write", "args": {"path": "conta.py", "content": "print(2 + 2)\n"}}, "pronto",
                                     {"tool": "shell", "args": {"command": "python conta.py"}}, "rodei: 4"])
        self.assertEqual(agent.run("crie conta.py"), "rodei: 4")
        self.assertEqual(sum("no command in this session ever executed" in m for m in seen), 1)
        self.assertEqual(self.s.code_new, set())
        agent, seen = self.scripted([{"tool": "write", "args": {"path": "util.py", "content": "def f():\n    return 1\n"}},
                                     {"tool": "shell", "args": {"command": "python -m pytest -q"}}, "feito"])
        agent.run("crie util.py com teste")                                                # a test suite counts as running it
        self.assertFalse(any("ever executed" in m for m in seen))
        self.assertEqual(T.ran_code({"util.py", "outro.py"}, "python -m pkg.util --help"), {"util.py"})
        self.assertEqual(T.ran_code({"util.py"}, "ls -la"), set())

    def test_an_answer_that_admits_unchecked_work_is_sent_back_once(self):
        from hangar.agent import unverified
        self.assertEqual(unverified("Tudo testado: 8 testes passam.\nCorrigi o bug."), [])
        self.assertEqual(len(unverified("- Não joguei a luta com o teclado.\n- The Windows path was not tested.\n- ok")), 2)
        agent, seen = self.scripted(["Fiz a mudança, mas não testei o caso de borda.", "Testei agora: o caso de borda passa."])
        self.assertEqual(agent.run("ajuste o cálculo"), "Testei agora: o caso de borda passa.")
        self.assertEqual(sum("your own answer says part of the work was not checked" in m for m in seen), 1)
        agent, seen = self.scripted(["Não testei no macOS: não há um aqui.", "Não testei no macOS: não há um aqui."])
        self.assertIn("macOS", agent.run("porte para macOS"))                              # still unverifiable: accepted the second time
        self.assertEqual(sum("was not checked" in m for m in seen), 1)

    def test_every_builtin_skill_can_be_pointed_at_by_the_task(self):
        found = skills.discover(self.tmp)
        for task, name in (("monte um dashboard de vendas", "dashboard"), ("faça uma apresentação para a diretoria", "presentation"),
                           ("faça a análise de dados do csv", "data-analysis"), ("gere uma imagem de capa", "image-generation"),
                           ("crie um vídeo animado de 10 s", "motion-video")):
            self.assertIn(f"`{name}`", skills.suggest(found, task), task)
        self.assertEqual(skills.suggest(found, "corrija o teste que falha em parser.py"), "")

    def test_scripts_of_a_page_count_as_the_page(self):
        (self.tmp / "js").mkdir()
        self.s.touched(self.tmp / "js" / "main.js")
        self.assertEqual(self.s.page_unseen, "")                                           # no page in this session: a script alone is not one
        self.s.touched(self.tmp / "index.html")
        T.builtin()["shell"].fn(T.Ctx(self.s, type("A", (), {"name": "t", "model": "x"})()), {"command": "python -m hangar studio --help"})
        self.assertEqual(self.s.page_unseen, "")
        self.s.touched(self.tmp / "js" / "main.js")
        self.assertEqual(self.s.page_unseen, "index.html")


if __name__ == "__main__":
    unittest.main()
