"""Does project memory pay? Two different tasks in the same small project.

  python bench/memory_bench.py --model auto --runs 3

  1. LEARN: task A (fix a bug) runs once with memory on, in a fresh copy of the project. Whatever the harness stores
     in `.hangar/memory` is what a real first session would leave behind.
  2. MEASURE: task B (add a feature elsewhere in the project) runs N times cold (`--no-memory`) and N times warm
     (the memory learned in step 1 copied into a fresh copy of the project).

The project is a small company codebase (about 60 files, most of them irrelevant to the tasks). It hides what an agent has to discover: tests are `qa/check_*.py` (plain `unittest` discovery finds nothing),
the way to run them is `python tools/verificar.py`, money is integer cents, and business rules live in
`config/negocio/regras.json`, read by `nucleo/config/regras.py`.
Success is decided by hidden deterministic checks, never by a model."""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "README.md": "# Loja\n\nSistema de gestão de uma loja: vendas, clientes, fiscal, logística, catálogo, financeiro e integrações.\n",
    "vendas/__init__.py": "",
    "nucleo/__init__.py": "",
    "nucleo/config/__init__.py": "",
    "vendas/precos.py": '''"""Preços. Todo valor monetário é um inteiro em centavos."""


def desconto(total_centavos, percentual):
    """Valor do desconto, em centavos, arredondado para o centavo mais próximo (meio centavo sobe)."""
    return int(total_centavos * percentual / 100)


def aplicar_desconto(total_centavos, percentual):
    return total_centavos - desconto(total_centavos, percentual)
''',
    "vendas/pedidos.py": '''"""Pedidos: itens são dicionários {"sku", "preco_centavos", "quantidade"}."""
from vendas.precos import aplicar_desconto


def subtotal(itens):
    return sum(i["preco_centavos"] * i["quantidade"] for i in itens)


def total_pedido(itens, cupom_percentual=0):
    return aplicar_desconto(subtotal(itens), cupom_percentual)
''',
    "vendas/estoque.py": '''"""Estoque: dicionário sku -> quantidade."""


def baixar(estoque, sku, quantidade):
    if estoque.get(sku, 0) < quantidade:
        raise ValueError(f"estoque insuficiente de {sku}")
    estoque[sku] -= quantidade
    return estoque
''',
    "nucleo/config/regras.py": '''"""Regras de negócio, lidas de config/negocio/regras.json."""
import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parents[2] / "config" / "negocio" / "regras.json"


def carregar():
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))
''',
    "config/negocio/regras.json": '{\n  "frete_gratis_acima_de_centavos": 15000,\n  "taxa_frete_centavos": 1890,\n  "cupom_maximo_percentual": 40\n}\n',
    "qa/check_precos.py": '''import unittest

from vendas.precos import aplicar_desconto, desconto


class Precos(unittest.TestCase):
    def test_desconto_simples(self):
        self.assertEqual(desconto(10000, 10), 1000)

    def test_aplicar(self):
        self.assertEqual(aplicar_desconto(10000, 25), 7500)
''',
    "qa/check_pedidos.py": '''import unittest

from vendas.pedidos import subtotal, total_pedido

ITENS = [{"sku": "a", "preco_centavos": 2500, "quantidade": 2}, {"sku": "b", "preco_centavos": 990, "quantidade": 1}]


class Pedidos(unittest.TestCase):
    def test_subtotal(self):
        self.assertEqual(subtotal(ITENS), 5990)

    def test_total_com_cupom(self):
        self.assertEqual(total_pedido(ITENS, 10), 5391)
''',
    "qa/check_estoque.py": '''import unittest

from vendas.estoque import baixar


class Estoque(unittest.TestCase):
    def test_baixa(self):
        self.assertEqual(baixar({"a": 3}, "a", 2), {"a": 1})

    def test_insuficiente(self):
        with self.assertRaises(ValueError):
            baixar({"a": 1}, "a", 2)
''',
    "tools/verificar.py": '''"""Roda a verificação do projeto: os testes ficam em qa/ e se chamam check_*.py."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
suite = unittest.defaultTestLoader.discover(str(RAIZ / "qa"), pattern="check_*.py")
resultado = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if resultado.wasSuccessful() and resultado.testsRun else 1)
''',
}

OTHERS = {
    "clientes": ["cadastro", "enderecos", "fidelidade", "segmentos", "contatos"],
    "fiscal": ["notas", "impostos", "cfop", "sped", "certificados"],
    "logistica": ["rotas", "transportadoras", "rastreio", "embalagens", "prazos"],
    "catalogo": ["produtos", "categorias", "imagens", "busca", "variantes"],
    "financeiro": ["contas", "boletos", "conciliacao", "fluxo_caixa", "cobranca"],
    "integracoes": ["marketplace", "erp", "gateway", "webhooks", "planilhas"],
    "relatorios": ["vendas_mes", "ranking", "margem", "exportar", "painel"],
    "notificacoes": ["email", "sms", "modelos", "fila", "preferencias"],
}
for _pkg, _mods in OTHERS.items():
    FILES[f"{_pkg}/__init__.py"] = ""
    for _m in _mods:
        FILES[f"{_pkg}/{_m}.py"] = (f'"""{_pkg.capitalize()}: {_m.replace("_", " ")}."""\n\n\n'
                                    f"def listar_{_m}(registros):\n    return sorted(registros, key=lambda r: r.get(\"id\", 0))\n\n\n"
                                    f"def buscar_{_m}(registros, id_):\n    return next((r for r in registros if r.get(\"id\") == id_), None)\n\n\n"
                                    f"def resumo_{_m}(registros):\n    return {{\"total\": len(registros), \"modulo\": \"{_pkg}.{_m}\"}}\n")
    FILES[f"qa/check_{_pkg}.py"] = (f"import unittest\n\nfrom {_pkg}.{_mods[0]} import buscar_{_mods[0]}, resumo_{_mods[0]}\n\n\n"
                                    f"class {_pkg.capitalize()}(unittest.TestCase):\n    def test_buscar(self):\n"
                                    f"        self.assertEqual(buscar_{_mods[0]}([{{\"id\": 2}}], 2), {{\"id\": 2}})\n\n"
                                    f"    def test_resumo(self):\n        self.assertEqual(resumo_{_mods[0]}([])[\"total\"], 0)\n")
FILES["config/app.json"] = '{\n  "nome": "loja",\n  "fuso": "America/Sao_Paulo",\n  "idioma": "pt-BR"\n}\n'
FILES["config/integracoes/gateway.json"] = '{\n  "timeout_s": 20,\n  "tentativas": 3\n}\n'
FILES["docs/arquitetura.md"] = "# Arquitetura\n\nUm pacote por área da loja. Código compartilhado fica em `nucleo/`.\n"

TASK_A = ("O desconto de 15% sobre R$ 199,90 está saindo com um centavo a menos do que deveria. Corrija o cálculo do desconto "
          "e confirme que a verificação do projeto continua passando.")
TASK_B = ("Adicione frete aos pedidos: crie `total_com_frete(itens, cupom_percentual=0)` no módulo de pedidos. Pedidos cujo total "
          "(já com o cupom) fica abaixo do limite de frete grátis pagam a taxa de frete; a partir do limite, o frete é grátis. "
          "Use as regras já configuradas no projeto, não invente valores. Acrescente testes e confirme que a verificação do projeto passa.")


def project(d: Path) -> Path:
    for rel, text in FILES.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return d


def _py(d: Path, code: str) -> tuple[bool, str]:
    p = subprocess.run([sys.executable, "-c", code], cwd=str(d), capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-300:]


def _suite(d: Path) -> tuple[bool, str]:
    p = subprocess.run([sys.executable, "tools/verificar.py"], cwd=str(d), capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-200:]


def check_a(d: Path) -> tuple[bool, str]:
    ok, out = _py(d, "from vendas.precos import desconto, aplicar_desconto\n"
                     "assert desconto(19990, 15) == 2999, desconto(19990, 15)\nassert desconto(10000, 10) == 1000\n"
                     "assert desconto(333, 50) == 167, desconto(333, 50)\nassert aplicar_desconto(19990, 15) == 16991\n"
                     "assert isinstance(desconto(19990, 15), int)\nprint('ok')")
    if not ok:
        return False, out
    return _suite(d)


def check_b(d: Path) -> tuple[bool, str]:
    ok, out = _py(d, "import json, pathlib\nfrom vendas.pedidos import total_com_frete\n"
                     "i = lambda preco, q=1: [{'sku': 'x', 'preco_centavos': preco, 'quantidade': q}]\n"
                     "assert total_com_frete(i(5000)) == 6890, total_com_frete(i(5000))\n"
                     "assert total_com_frete(i(15000)) == 15000, total_com_frete(i(15000))\n"
                     "assert total_com_frete(i(14999)) == 16889\n"
                     "assert total_com_frete(i(16000), 10) == 16290, total_com_frete(i(16000), 10)\n"          # 14400 after the coupon: pays
                     "p = pathlib.Path('config/negocio/regras.json'); r = json.loads(p.read_text(encoding='utf-8'))\n"
                     "r['taxa_frete_centavos'] = 500; r['frete_gratis_acima_de_centavos'] = 9000\n"
                     "p.write_text(json.dumps(r), encoding='utf-8')\n"
                     "import importlib, vendas.pedidos, nucleo.config.regras\n"
                     "importlib.reload(nucleo.config.regras); importlib.reload(vendas.pedidos)\n"
                     "assert vendas.pedidos.total_com_frete(i(5000)) == 5500, 'the rules file is not being read'\n"
                     "assert vendas.pedidos.total_com_frete(i(9000)) == 9000\nprint('ok')")
    (d / "config" / "negocio" / "regras.json").write_text(FILES["config/negocio/regras.json"], encoding="utf-8", newline="\n")
    if not ok:
        return False, out
    return _suite(d)


def run(model: str, task: str, d: Path, memory: bool) -> dict:
    cmd = [sys.executable, "-m", "hangar", "run", task, "--cwd", str(d), "-m", model, "--json", "--no-interactive", "--no-lessons", "--max-cost", "1.0"]
    if not memory:
        cmd.append("--no-memory")
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace")
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"status": "crash", "cost": 0, "llm_calls": 0, "tool_calls": 0, "prompt": 0, "duration_s": 0, "by_role": [], "error": p.stderr[-300:]}


def facts(d: Path) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from hangar import memory
    return [f"{f['name']} ({f['kind']}, {f.get('source')}): {f['fact']}" + (f" — `{f['command']}`" if f["command"] else "") for f in memory.load(d)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="auto")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    base = Path(tempfile.mkdtemp(prefix="hangar_membench_"))
    rows = []

    learn = project(base / "learn" / "loja")
    r = run(a.model, TASK_A, learn, memory=True)
    ok, detail = check_a(learn)
    learned = facts(learn)
    rows.append({"phase": "learn", "task": "A", "memory": True, "ok": ok, "detail": detail, **{k: r.get(k) for k in ("status", "cost", "llm_calls", "tool_calls", "prompt", "duration_s", "by_role")}})
    print(f"LEARN  task A  {'OK  ' if ok else 'FAIL'} ${r.get('cost', 0):.5f}  {r.get('llm_calls')} llm · {r.get('tool_calls')} tools   memory: {len(learned)} facts")
    for f in learned:
        print("   ·", f)
    if not learned:
        print("nothing was learned: the measurement would compare cold with cold.")

    for i in range(a.runs):
        for warm in (False, True):
            d = project(base / f"{'warm' if warm else 'cold'}{i}" / "loja")
            if warm and (learn / ".hangar" / "memory").is_dir():
                shutil.copytree(learn / ".hangar" / "memory", d / ".hangar" / "memory")
            r = run(a.model, TASK_B, d, memory=warm)
            ok, detail = check_b(d)
            rows.append({"phase": "measure", "task": "B", "memory": warm, "ok": ok, "detail": detail,
                         **{k: r.get(k) for k in ("status", "cost", "llm_calls", "tool_calls", "prompt", "duration_s", "by_role")}})
            print(f"{'WARM' if warm else 'COLD'}   task B  {'OK  ' if ok else 'FAIL'} ${r.get('cost', 0):.5f}  {r.get('llm_calls')} llm · {r.get('tool_calls')} tools · "
                  f"{r.get('prompt')} tokens in · {r.get('duration_s')}s   {'' if ok else detail[:90]}", flush=True)

    def med(warm: bool, key: str) -> float:
        v = [x[key] or 0 for x in rows if x["phase"] == "measure" and x["memory"] is warm]
        return statistics.median(v) if v else 0

    print("\n            solved   cost (median)   llm calls   tool calls   tokens in")
    for warm in (False, True):
        mine = [x for x in rows if x["phase"] == "measure" and x["memory"] is warm]
        print(f"{'with memory' if warm else 'no memory  '}  {sum(x['ok'] for x in mine)}/{len(mine)}      ${med(warm, 'cost'):.5f}        "
              f"{med(warm, 'llm_calls'):g}          {med(warm, 'tool_calls'):g}           {med(warm, 'prompt'):g}")
    out = ROOT / "bench" / "results"
    out.mkdir(exist_ok=True)
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-memory.json"
    (out / name).write_text(json.dumps({"harness": "hangar-memory", "model": a.model, "learned": learned, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsaved bench/results/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
