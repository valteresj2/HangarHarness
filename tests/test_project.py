"""The .claude/ harness surface a project (or a Lab variant of it) carries: instructions, sub-agents,
slash commands and Claude Code hooks. Offline."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HANGAR_HOME", tempfile.mkdtemp(prefix="hangar_test_home_"))

from hangar import config, project, prompts, tools as T  # noqa: E402
from hangar.agent import Agent  # noqa: E402
from hangar.session import Session  # noqa: E402

MODEL = "anthropic/claude-sonnet-5.5"


class ProjectSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hangar_p_")).resolve()
        c = self.tmp / ".claude"
        (c / "agents").mkdir(parents=True)
        (c / "commands" / "git").mkdir(parents=True)
        (self.tmp / "CLAUDE.md").write_text("regra da raiz", encoding="utf-8")
        (c / "CLAUDE.md").write_text("regra da pasta .claude", encoding="utf-8")
        (c / "agents" / "revisor.md").write_text(
            "---\nname: revisor\ndescription: Revisa diffs com rigor\n---\nVoce e um revisor exigente.", encoding="utf-8")
        (c / "commands" / "resumo.md").write_text(
            "---\ndescription: Resume um arquivo\nargument-hint: <arquivo>\n---\nResuma $ARGUMENTS em 3 linhas.", encoding="utf-8")
        (c / "commands" / "git" / "commit.md").write_text("Escreva a mensagem de commit.", encoding="utf-8")

    def session(self, **over) -> Session:
        s = Session({**config.load(self.tmp, {k: v for k, v in over.items() if k == "trust_project"}),
                     **{k: v for k, v in over.items() if k != "trust_project"}}, self.tmp)
        self.addCleanup(s.bus.close)
        return s

    def test_instructions_agents_and_commands(self):
        self.assertEqual([n for n, _ in project.instructions(self.tmp)], ["CLAUDE.md", ".claude/CLAUDE.md"])
        self.assertEqual(project.agents(self.tmp)["revisor"]["description"], "Revisa diffs com rigor")
        cmds = project.commands(self.tmp)
        self.assertEqual(sorted(cmds), ["git:commit", "resumo"])
        self.assertEqual(cmds["resumo"]["hint"], "<arquivo>")
        self.assertEqual(project.expand_command(self.tmp, "/resumo notas.md"), ("Resuma notas.md em 3 linhas.", "resumo"))
        self.assertEqual(project.expand_command(self.tmp, "/git:commit rapido")[0], "Escreva a mensagem de commit.\n\nrapido")
        self.assertEqual(project.expand_command(self.tmp, "/nao-existe x"), ("/nao-existe x", None))
        self.assertEqual(project.expand_command(self.tmp, "texto normal / com barra"), ("texto normal / com barra", None))

    def test_prompt_lists_subagents_and_the_task_tool_uses_them(self):
        s = self.session()
        main = Agent(s, model=MODEL, name="work")
        text = prompts.build(s, main)
        self.assertIn("regra da raiz", text)
        self.assertIn("regra da pasta .claude", text)
        self.assertIn("- revisor: Revisa diffs com rigor", text)
        sub = Agent(s, model=MODEL, role="sub", name="sub1", extra_system="Voce e um revisor exigente.")
        self.assertIn("Voce e um revisor exigente.", prompts.build(s, sub))
        with self.assertRaises(T.ToolError) as e:
            T.builtin()["task"].fn(T.Ctx(s, main), {"prompt": "x", "agent": "fantasma"})
        self.assertIn("revisor", str(e.exception))

    def test_allowed_tools_restricts_the_catalog(self):
        self.assertEqual([t.name for t in Agent(self.session(allowed_tools=["read", "grep"]), model=MODEL).tools], ["read", "grep"])
        self.assertEqual(Agent(self.session(allowed_tools=[]), model=MODEL).tools, [])

    def test_confine_keeps_file_tools_inside_the_working_directory(self):
        outside = Path(tempfile.mkdtemp(prefix="hangar_out_")).resolve() / "segredo.txt"
        outside.write_text("fora", encoding="utf-8")
        free = self.session()
        self.assertIn("fora", T.builtin()["read"].fn(T.Ctx(free, None), {"path": str(outside)}))
        s = self.session(confine=True)
        ctx = T.Ctx(s, None)
        for tool, args in (("read", {"path": str(outside)}), ("read", {"path": "../x"}), ("grep", {"pattern": "f", "path": str(outside.parent)}),
                           ("write", {"path": str(outside), "content": "x"})):
            with self.assertRaises(T.ToolError) as e:
                T.builtin()[tool].fn(ctx, args)
            self.assertIn("outside the working directory", str(e.exception))
        self.assertIn("regra da raiz", T.builtin()["read"].fn(ctx, {"path": "CLAUDE.md"}))
        self.assertEqual(outside.read_text(encoding="utf-8"), "fora")

    def test_claude_code_hooks_run_only_when_the_project_is_trusted(self):
        settings = {"hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python guard.py"}]}],
            "PostToolUse": [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "python lint.py"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "python stop.py"}]}]}}
        (self.tmp / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        (self.tmp / "guard.py").write_text(
            "import sys, json\nd = json.load(sys.stdin)\n"
            "if 'rm ' in d['tool_input']['command']:\n    sys.stderr.write('rm e proibido aqui'); sys.exit(2)\n", encoding="utf-8")
        (self.tmp / "lint.py").write_text(
            "import sys, json\nd = json.load(sys.stdin)\n"
            "sys.stderr.write('lint: ' + d['tool_name'] + ' ' + d['tool_input']['file_path'][-5:]); sys.exit(2)\n", encoding="utf-8")
        (self.tmp / "stop.py").write_text(
            "import sys, os\nif not os.path.exists('pronto.flag'):\n    sys.stderr.write('falta pronto.flag'); sys.exit(2)\n", encoding="utf-8")
        self.assertEqual(project.claude_hooks(self.tmp)["PreToolUse"][0]["matcher"], "Bash")
        plain = self.session()
        self.assertEqual(plain.hooks.pre_tool(None, "shell", {"command": "rm -r x"}), "")      # untrusted: project code is not run
        s = self.session(trust_project=True)
        self.assertIn("rm e proibido aqui", s.hooks.pre_tool(None, "shell", {"command": "rm -r x"}))
        self.assertEqual(s.hooks.pre_tool(None, "shell", {"command": "ls"}), "")
        self.assertEqual(s.hooks.pre_tool(None, "read", {"path": "a"}), "")                     # the matcher is Bash only
        self.assertIn("lint: Write", s.hooks.post_tool(None, "write", {"path": "a.txt", "content": "x"}, True, "ok"))
        self.assertIn("falta pronto.flag", s.hooks.pre_finish(None, "terminei"))
        (self.tmp / "pronto.flag").write_text("x")
        self.assertEqual(s.hooks.pre_finish(None, "terminei"), "")


if __name__ == "__main__":
    unittest.main()
