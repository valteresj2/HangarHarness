"""Hard benchmark tasks: multi-file, multi-step, need running processes and careful verification.
  kvstore   build an HTTP key-value server from a spec (persistence across kill, TTL, optimistic locking, concurrency)
  pipeline  find and fix 9 bugs spread over 4 modules of a report pipeline (checked on hidden data, byte-exact)
  refactor  change a function's API and update 10 call sites written in 10 different styles
Run `python bench/tasks_hard.py` to self-test the fixtures (reference passes; each injected bug is detectable)."""
from __future__ import annotations

import json
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PY = sys.executable


def _run(cmd: list, cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


# ================================================================== 1. kvstore
KV_SPEC = """# kvd — servidor chave-valor

Implemente `kvd.py` usando apenas a biblioteca padrão do Python.

Uso: `python kvd.py --port PORTA --data ARQUIVO`  (escuta em 127.0.0.1:PORTA; todas as respostas são JSON)

| Rota | Comportamento |
|---|---|
| `GET /health` | 200 `{"status": "ok"}` |
| `PUT /kv/<chave>` | corpo `{"value": <qualquer JSON>, "ttl": <segundos, opcional>}` → 200 `{"key": ..., "version": n}`. A versão começa em 1 e sobe 1 a cada escrita na chave. |
| `PUT` com header `If-Match: <versão>` | só grava se a versão atual da chave for exatamente essa; senão 412 `{"error": "version_mismatch", "version": <atual>}` |
| `GET /kv/<chave>` | 200 `{"key", "value", "version"}`; 404 `{"error": "not_found"}` se não existe ou expirou |
| `DELETE /kv/<chave>` | 200 `{"deleted": true}`; 404 `{"error": "not_found"}` se não existe |
| `GET /keys?prefix=<p>` | 200 `{"keys": [...]}` em ordem alfabética, só chaves não expiradas que começam com o prefixo |
| `POST /incr/<chave>` | corpo `{"by": n}` (padrão 1). Soma a um valor inteiro; se a chave não existe, parte de 0. 200 `{"key", "value", "version"}`. Se o valor existente não é inteiro: 409 `{"error": "not_integer"}` |
| `GET /stats` | 200 `{"keys": <não expiradas>, "puts": <PUTs aceitos desde que ESTE processo iniciou>}` (incr não conta como PUT) |

Regras:
- Corpo inválido (JSON malformado, ou PUT sem o campo `value`) → 400 `{"error": "bad_request"}`.
- Uma chave com `ttl` some depois de `ttl` segundos (GET dá 404 e ela não aparece em /keys nem em /stats).
- Persistência: tudo o que foi confirmado com 200 (valores, versões, expirações) precisa sobreviver a matar o processo
  abruptamente e subir de novo com o mesmo `--data`.
- Concorrência: 50 `POST /incr` simultâneos na mesma chave precisam resultar em exatamente 50.

Suba o servidor e teste de verdade as rotas antes de terminar."""


def setup_kvstore(d: Path) -> dict:
    (d / "SPEC.md").write_text(KV_SPEC, encoding="utf-8")
    return {"prompt": "Implemente o servidor descrito em SPEC.md. Leia a especificação inteira, implemente `kvd.py`, suba o servidor "
                      "e teste as rotas (inclusive persistência após matar o processo e concorrência) antes de dar por concluído."}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check_kvstore(d: Path):
    if not (d / "kvd.py").is_file():
        return False, "kvd.py missing"
    port, data = _free_port(), Path(tempfile.mkdtemp(prefix="kvcheck_")) / "kv.db"

    def start():
        return subprocess.Popen([PY, "kvd.py", "--port", str(port), "--data", str(data)], cwd=str(d),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def req(method, path, body=None, headers=None, raw=None):
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=payload, method=method,
                                   headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                code, text = resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            code, text = e.code, e.read().decode("utf-8", "replace")
        except Exception:
            return 0, {}
        try:
            return code, json.loads(text)
        except ValueError:
            return code, {}

    def wait():
        for _ in range(60):
            if req("GET", "/health")[0] == 200:
                return True
            time.sleep(0.15)
        return False

    fails: list[str] = []

    def ck(name, cond):
        if not cond:
            fails.append(name)

    p = start()
    try:
        if not wait():
            return False, "server did not answer /health"
        ck("health", req("GET", "/health") == (200, {"status": "ok"}))
        c, j = req("PUT", "/kv/a", {"value": {"x": [1, 2]}})
        ck("put v1", c == 200 and j.get("version") == 1 and j.get("key") == "a")
        ck("get json value", req("GET", "/kv/a")[1].get("value") == {"x": [1, 2]})
        c, j = req("PUT", "/kv/a", {"value": "v2"})
        ck("put v2", c == 200 and j.get("version") == 2)
        ck("get 404", req("GET", "/kv/nope") == (404, {"error": "not_found"}))
        c, j = req("PUT", "/kv/a", {"value": "v3"}, {"If-Match": "1"})
        ck("if-match mismatch", c == 412 and j.get("error") == "version_mismatch" and j.get("version") == 2)
        c, j = req("PUT", "/kv/a", {"value": "v3"}, {"If-Match": "2"})
        ck("if-match ok", c == 200 and j.get("version") == 3)
        ck("bad json", req("PUT", "/kv/b", raw=b"{nope") == (400, {"error": "bad_request"}))
        ck("missing value", req("PUT", "/kv/b", {"ttl": 3}) == (400, {"error": "bad_request"}))
        for k in ("user:1", "user:2", "order:9"):
            req("PUT", f"/kv/{k}", {"value": k})
        ck("prefix", req("GET", "/keys?prefix=user:")[1].get("keys") == ["user:1", "user:2"])
        c, j = req("POST", "/incr/n", {"by": 5})
        ck("incr create", c == 200 and j.get("value") == 5 and j.get("version") == 1)
        ck("incr default", req("POST", "/incr/n", {})[1].get("value") == 6)
        ck("incr not integer", req("POST", "/incr/a", {}) == (409, {"error": "not_integer"}))
        threads = [threading.Thread(target=req, args=("POST", "/incr/c", {})) for _ in range(50)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        ck("concurrency 50", req("GET", "/kv/c")[1].get("value") == 50)
        req("PUT", "/kv/tmp", {"value": 1, "ttl": 1})
        ck("ttl alive", req("GET", "/kv/tmp")[0] == 200)
        time.sleep(1.5)
        ck("ttl expired", req("GET", "/kv/tmp")[0] == 404)
        ck("ttl not listed", "tmp" not in req("GET", "/keys?prefix=")[1].get("keys", ["tmp"]))
        ck("delete", req("DELETE", "/kv/user:2") == (200, {"deleted": True}))
        ck("delete 404", req("DELETE", "/kv/user:2") == (404, {"error": "not_found"}))
        ck("stats", req("GET", "/stats") == (200, {"keys": 5, "puts": 7}))
        req("PUT", "/kv/keep", {"value": "z", "ttl": 3600})
        p.kill()
        p.wait(timeout=10)
        p = start()
        if not wait():
            return False, "server did not come back after kill; before that failed: " + (", ".join(fails) or "nothing")
        c, j = req("GET", "/kv/a")
        ck("persist value+version", c == 200 and j.get("value") == "v3" and j.get("version") == 3)
        ck("persist incr", req("GET", "/kv/n")[1].get("value") == 6 and req("GET", "/kv/c")[1].get("value") == 50)
        ck("persist delete", req("GET", "/kv/user:2")[0] == 404 and req("GET", "/kv/user:1")[0] == 200)
        ck("persist ttl", req("GET", "/kv/tmp")[0] == 404 and req("GET", "/kv/keep")[1].get("value") == "z")
        ck("stats reset", req("GET", "/stats")[1].get("puts") == 0)
        ck("version continues", req("PUT", "/kv/a", {"value": "v4"})[1].get("version") == 4)
    finally:
        try:
            p.kill()
        except OSError:
            pass
    return not fails, "ok (27 checks)" if not fails else f"{len(fails)} failed: " + ", ".join(fails)[:160]


# ================================================================= 2. pipeline
PIPE = {
    "salesrep/__init__.py": "",
    "salesrep/parser.py": '''"""Leitura do CSV de vendas (separador ;)."""
import csv


def parse_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for rec in csv.DictReader(f, delimiter=";"):
            if not (rec.get("order_id") or "").strip():
                continue
            rows.append({k.strip(): (v or "").strip() for k, v in rec.items()})
    return rows
''',
    "salesrep/normalize.py": '''"""Limpeza: datas, valores, duplicados e cancelados."""
from datetime import datetime

FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


def parse_date(text):
    for fmt in FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data invalida: {text}")


def parse_money(text):
    t = text.replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return round(float(t), 2)


def normalize(rows):
    out, seen = [], set()
    for r in rows:
        if r["order_id"] in seen:
            continue
        seen.add(r["order_id"])
        if r["status"].lower() == "cancelled":
            continue
        qty = int(r["qty"])
        out.append({
            "order_id": r["order_id"],
            "date": parse_date(r["date"]),
            "region": r["region"].strip().title(),
            "product": r["product"],
            "qty": qty,
            "total": round(qty * parse_money(r["unit_price"]), 2),
        })
    return out
''',
    "salesrep/aggregate.py": '''"""Agregacoes do relatorio."""
from collections import defaultdict


def by_region(orders):
    acc = defaultdict(lambda: {"orders": 0, "units": 0, "revenue": 0.0})
    for o in orders:
        a = acc[o["region"]]
        a["orders"] += 1
        a["units"] += o["qty"]
        a["revenue"] += o["total"]
    return {k: {**v, "revenue": round(v["revenue"], 2)} for k, v in acc.items()}


def by_month(orders):
    acc = defaultdict(float)
    for o in orders:
        acc[o["date"].strftime("%Y-%m")] += o["total"]
    return {k: round(v, 2) for k, v in sorted(acc.items())}


def top_products(orders, n=3):
    acc = defaultdict(int)
    for o in orders:
        acc[o["product"]] += o["qty"]
    return sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def average_ticket(orders):
    return round(sum(o["total"] for o in orders) / len(orders), 2) if orders else 0.0
''',
    "salesrep/render.py": '''"""Formatacao do relatorio em texto."""


def money(v):
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def render(regions, months, top, ticket):
    lines = ["RELATORIO DE VENDAS", "", "Por regiao:"]
    for name in sorted(regions, key=lambda r: (-regions[r]["revenue"], r)):
        r = regions[name]
        lines.append(f"  {name:<14} pedidos={r['orders']:>3} unidades={r['units']:>4} receita={money(r['revenue'])}")
    lines += ["", "Por mes:"]
    for m, v in months.items():
        lines.append(f"  {m} {money(v)}")
    lines += ["", "Top produtos:"]
    for i, (p, q) in enumerate(top, 1):
        lines.append(f"  {i}. {p} ({q})")
    lines += ["", f"Ticket medio: {money(ticket)}"]
    return "\\n".join(lines) + "\\n"
''',
    "salesrep/cli.py": '''"""python -m salesrep.cli <arquivo.csv>"""
import sys

from .aggregate import average_ticket, by_month, by_region, top_products
from .normalize import normalize
from .parser import parse_rows
from .render import render


def main(argv=None):
    argv = argv or sys.argv[1:]
    orders = normalize(parse_rows(argv[0]))
    sys.stdout.write(render(by_region(orders), by_month(orders), top_products(orders), average_ticket(orders)))


if __name__ == "__main__":
    main()
''',
}

# (file, correct snippet, buggy snippet) — each applied alone must change the report on the hidden data
BUGS = [
    ("salesrep/parser.py", "                continue\n            rows.append", "                break\n            rows.append"),
    ("salesrep/normalize.py", '("%Y-%m-%d", "%d/%m/%Y")', '("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")'),
    ("salesrep/normalize.py", '    if "," in t:\n        t = t.replace(".", "").replace(",", ".")', '    t = t.replace(".", "").replace(",", ".")'),
    ("salesrep/normalize.py", "            continue\n        seen.add(r[\"order_id\"])\n", "            pass\n        seen.add(r[\"order_id\"])\n"),
    ("salesrep/normalize.py", 'r["status"].lower() == "cancelled"', 'r["status"] == "cancelled"'),
    ("salesrep/aggregate.py", 'a["units"] += o["qty"]', 'a["units"] += 1'),
    ("salesrep/aggregate.py", "key=lambda kv: (-kv[1], kv[0]))[:n]", "key=lambda kv: -kv[1])[:n]"),
    ("salesrep/render.py", 's.replace(",", "X").replace(".", ",").replace("X", ".")', 's.replace(",", ".").replace(".", ",")'),
    ("salesrep/render.py", "(-regions[r][\"revenue\"], r)", "(regions[r][\"revenue\"], r)"),
]

PIPE_README = """# salesrep

Gera o relatório de vendas a partir de um CSV separado por `;`: `python -m salesrep.cli data/sales.csv`

Regras de negócio (o relatório correto para `data/sales.csv` está em `expected/report.txt`):
- Linhas sem `order_id` (linhas em branco no meio do arquivo) são ignoradas; o arquivo continua sendo lido até o fim.
- `order_id` repetido: vale só a primeira ocorrência.
- Pedidos com status `cancelled` em qualquer combinação de maiúsculas/minúsculas ficam de fora.
- Datas vêm como `AAAA-MM-DD` ou `DD/MM/AAAA` (dia primeiro, sempre).
- Preços vêm como `R$ 1.234,50`, `12,50` (vírgula decimal, ponto de milhar) ou `12.50` (ponto decimal, quando não há vírgula).
- Região: sem espaços nas pontas e com iniciais maiúsculas. Ordenadas por receita decrescente; empate por nome.
- `unidades` é a soma das quantidades; `pedidos` é a contagem de pedidos.
- Top 3 produtos por unidades vendidas; empate em ordem alfabética.
- Valores no formato brasileiro: `R$ 1.234,56`.
"""


def _make_sales(path: Path, seed: int, n: int) -> None:
    rnd = random.Random(seed)
    regions = ["sul", " Norte", "SUDESTE", "nordeste ", "Centro-oeste"]
    products = ["Parafuso", "Arruela", "Porca", "Rebite", "Bucha", "Anel"]
    statuses = ["paid", "shipped", "paid", "paid", "cancelled", "Cancelled", "CANCELLED"]
    lines = ["order_id;date;region;product;qty;unit_price;status"]
    for i in range(1, n + 1):
        day, month = rnd.randint(1, 28), rnd.randint(1, 4)
        date = f"2026-{month:02d}-{day:02d}" if rnd.random() < 0.5 else f"{day:02d}/{month:02d}/2026"
        price = rnd.choice([12.5, 7.25, 1234.5, 99.9, 3.1, 2500.0, 48.0])
        style = rnd.randrange(3)
        if style == 0:
            ptxt = "R$ " + f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        elif style == 1:
            ptxt = f"{price:.2f}".replace(".", ",")
        else:
            ptxt = f"{price:.2f}"
        lines.append(f"P{i:04d};{date};{rnd.choice(regions)};{rnd.choice(products)};{rnd.choice([1, 2, 2, 3, 5])};{ptxt};{rnd.choice(statuses)}")
        if i % 17 == 0:                                    # duplicate id with a different quantity: first one wins
            lines.append(f"P{i:04d};{date};{rnd.choice(regions)};{rnd.choice(products)};9;{ptxt};paid")
        if i == n // 3:
            lines.append(";;;;;;")                         # blank row in the middle of the file
    # a guaranteed tie between two products so the alphabetical tie-break matters
    lines += [f"T{k:03d};2026-02-10;sul;{p};900;1,00;paid" for k, p in enumerate(["Zinco", "Cobre"])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pipeline(d: Path, bugs: list) -> None:
    src = dict(PIPE)
    for f, good, bad in bugs:
        assert good in src[f], (f, good)
        src[f] = src[f].replace(good, bad, 1)
    for rel, text in src.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")


def _reference_report(csv: Path) -> str:
    ref = Path(tempfile.mkdtemp(prefix="piperef_"))
    _write_pipeline(ref, [])
    out = _run([PY, "-m", "salesrep.cli", str(csv)], ref).stdout
    shutil.rmtree(ref, ignore_errors=True)
    return out


def setup_pipeline(d: Path) -> dict:
    _write_pipeline(d, BUGS)
    (d / "data").mkdir()
    (d / "expected").mkdir()
    _make_sales(d / "data" / "sales.csv", 11, 120)
    (d / "expected" / "report.txt").write_text(_reference_report(d / "data" / "sales.csv"), encoding="utf-8", newline="\n")
    (d / "README.md").write_text(PIPE_README, encoding="utf-8")
    return {"prompt": "O relatório gerado por `python -m salesrep.cli data/sales.csv` está errado (às vezes nem roda): ele deveria ser "
                      "idêntico a `expected/report.txt`. Há vários bugs, em módulos diferentes do pacote `salesrep`. Leia o README.md "
                      "(regras de negócio), encontre e corrija TODOS — a correção será conferida com outro arquivo de dados, então "
                      "corrija a lógica, não o caso de exemplo. Não altere `data/` nem `expected/`."}


def check_pipeline(d: Path):
    hidden = Path(tempfile.mkdtemp(prefix="pipehid_")) / "hidden.csv"
    _make_sales(hidden, 977, 260)
    p = _run([PY, "-m", "salesrep.cli", str(hidden)], d)
    if p.returncode != 0:
        return False, "crash: " + (p.stderr.strip().splitlines() or ["?"])[-1][:120]
    want, got = _reference_report(hidden).splitlines(), p.stdout.splitlines()
    if got == want:
        return True, "ok (hidden data, byte-exact)"
    diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
    return False, f"{diff} of {len(want)} report lines differ on hidden data"


# ================================================================= 3. refactor
NOTIFY = '''"""Envio de notificacoes (em memoria)."""

SENT = []


def send(to, subject, body, cc=None, priority="normal"):
    SENT.append({"to": to, "subject": subject, "body": body, "cc": cc or [], "priority": priority})
'''

SERVICES = {
    "svc_01.py": 'import notify\n\n\ndef run(ctx):\n    notify.send(ctx["user"], "Bem-vindo", "Ola " + ctx["name"])\n',
    "svc_02.py": 'from notify import send\n\n\ndef run(ctx):\n    send(to=ctx["user"], subject="Fatura", body=f"Valor {ctx[\'amount\']}", priority="high")\n',
    "svc_03.py": 'import notify as n\n\n\ndef run(ctx):\n    n.send(\n        ctx["user"],\n        "Aprovacao",\n        "Pedido aprovado",\n        cc=[ctx["boss"]],\n    )\n',
    "svc_04.py": 'import notify\n\n\ndef run(ctx):\n    for member in ctx["team"]:\n        notify.send(member, "Reuniao", "As 10h", [ctx["boss"]])\n',
    "svc_05.py": 'import notify\n\n\ndef run(ctx):\n    args = (ctx["user"], "Alerta", "Disco cheio")\n    notify.send(*args, priority="urgent")\n',
    "svc_06.py": 'import notify\n\n\ndef run(ctx):\n    kw = {"to": ctx["user"], "subject": "Resumo", "body": "Semana " + str(ctx["week"])}\n    if ctx.get("boss"):\n        kw["cc"] = [ctx["boss"]]\n    notify.send(**kw)\n',
    "svc_07.py": 'import notify\n\n\ndef _mail(to, text):\n    return notify.send(to, "Aviso", text, None, "low")\n\n\ndef run(ctx):\n    _mail(ctx["user"], "Manutencao sabado")\n    _mail(ctx["boss"], "Manutencao sabado")\n',
    "svc_08.py": 'import notify\n\n\ndef run(ctx):\n    send = notify.send\n    if ctx.get("expired"):\n        send(ctx["user"], subject="Senha", body="Troque sua senha", priority="high")\n    else:\n        send(ctx["user"], "OK", "Tudo certo")\n',
    "svc_09.py": 'import notify\n\n\nclass Reporter:\n    def __init__(self, to, cc):\n        self.to, self.cc = to, cc\n\n    def emit(self, number, body):\n        notify.send(self.to, f"Relatorio {number}", body, cc=self.cc)\n\n\ndef run(ctx):\n    r = Reporter(ctx["boss"], list(ctx["team"]))\n    r.emit(1, "parcial")\n    r.emit(2, "final")\n',
    "svc_10.py": 'from notify import send as deliver\n\n\ndef run(ctx):\n    return [deliver(user, "Ping", "pong", priority=prio) for user, prio in ctx["pairs"]]\n',
}

OLD_TEST = '''import unittest

import notify
from services import svc_01, svc_04


class T(unittest.TestCase):
    def setUp(self):
        notify.SENT.clear()

    def test_welcome(self):
        svc_01.run({"user": "ana@x.com", "name": "Ana"})
        self.assertEqual(notify.SENT[0]["subject"], "Bem-vindo")
        self.assertEqual(notify.SENT[0]["cc"], [])

    def test_team(self):
        svc_04.run({"team": ["a@x.com", "b@x.com"], "boss": "c@x.com"})
        self.assertEqual([m["to"] for m in notify.SENT], ["a@x.com", "b@x.com"])
        self.assertEqual(notify.SENT[0]["cc"], ["c@x.com"])


if __name__ == "__main__":
    unittest.main()
'''

CTX = {"user": "bia@empresa.com", "name": "Bia", "amount": "1.280,00", "boss": "dir@empresa.com", "week": 46,
       "team": ["t1@empresa.com", "t2@empresa.com", "t3@empresa.com"], "expired": False,
       "pairs": [["p@empresa.com", "low"], ["q@empresa.com", "high"], ["r@empresa.com", "normal"]]}

PROBE = '''import importlib, json, sys
import notify
ctx = json.loads(sys.argv[1])
out = {}
for i in range(1, 11):
    name = f"svc_{i:02d}"
    notify.SENT.clear()
    importlib.import_module("services." + name).run(ctx)
    rows = []
    for m in notify.SENT:
        if isinstance(m, dict):
            rows.append(["dict", m["to"], m["subject"], m["body"], list(m["cc"] or []), m["priority"]])
        else:
            rows.append([type(m).__name__, m.to, m.subject, m.body, list(m.cc or []), m.priority])
    out[name] = rows
extra = {}
if hasattr(notify, "Message"):
    notify.SENT.clear()
    notify.send(notify.Message(to="a", subject="b", body="c"))
    m = notify.SENT[0]
    extra["defaults"] = [list(m.cc), m.priority]
    extra["same_object"] = isinstance(m, notify.Message)
    a, b = notify.Message(to="a", subject="b", body="c"), notify.Message(to="a", subject="b", body="c")
    a.cc.append("x")
    extra["cc_not_shared"] = b.cc == []
    try:
        notify.send("a", "b", "c")
        extra["old_call_rejected"] = False
    except TypeError:
        extra["old_call_rejected"] = True
print(json.dumps({"services": out, "extra": extra}))
'''


def _write_refactor(d: Path) -> None:
    (d / "notify.py").write_text(NOTIFY, encoding="utf-8")
    (d / "services").mkdir(exist_ok=True)
    (d / "services" / "__init__.py").write_text("", encoding="utf-8")
    for name, src in SERVICES.items():
        (d / "services" / name).write_text(src, encoding="utf-8")


def setup_refactor(d: Path) -> dict:
    _write_refactor(d)
    (d / "test_services.py").write_text(OLD_TEST, encoding="utf-8")
    return {"prompt": "Refatore a API de notificações deste projeto:\n"
                      "1. Em `notify.py`, crie a dataclass `Message` com os campos `to`, `subject`, `body`, `cc` (lista, padrão lista vazia "
                      "não compartilhada entre instâncias) e `priority` (padrão \"normal\").\n"
                      "2. `send` passa a aceitar exatamente um argumento, uma `Message`; qualquer outra forma de chamada deve levantar "
                      "`TypeError`. Ela guarda em `SENT` o próprio objeto `Message`.\n"
                      "3. Atualize TODOS os chamadores em `services/` (são 10 arquivos, cada um chama de um jeito) preservando exatamente "
                      "o que cada um envia hoje: destinatário, assunto, corpo, cc e prioridade.\n"
                      "4. Atualize `test_services.py` para a nova API e deixe `python -m unittest -q` passando."}


def _probe(d: Path) -> dict:
    p = _run([PY, "-c", PROBE, json.dumps(CTX)], d)
    if p.returncode != 0:
        raise RuntimeError((p.stderr.strip().splitlines() or ["probe failed"])[-1][:160])
    return json.loads(p.stdout.strip().splitlines()[-1])


def check_refactor(d: Path):
    ref = Path(tempfile.mkdtemp(prefix="refref_"))
    _write_refactor(ref)
    want = _probe(ref)["services"]
    shutil.rmtree(ref, ignore_errors=True)
    try:
        got = _probe(d)
    except Exception as e:
        return False, f"crash: {e}"
    fails = []
    for name, rows in want.items():
        mine = got["services"].get(name, [])
        if [r[1:] for r in mine] != [r[1:] for r in rows]:
            fails.append(f"{name} sends different content")
        elif any(r[0] != "Message" for r in mine):
            fails.append(f"{name} does not store Message")
    ex = got.get("extra") or {}
    for key, want_val in (("defaults", [[], "normal"]), ("same_object", True), ("cc_not_shared", True), ("old_call_rejected", True)):
        if ex.get(key) != want_val:
            fails.append(key)
    t = _run([PY, "-m", "unittest", "-q"], d)
    if t.returncode != 0:
        fails.append("unittest fails")
    return not fails, "ok (10 services + API contract + tests)" if not fails else f"{len(fails)} failed: " + ", ".join(fails)[:160]


sys.path.insert(0, str(Path(__file__).resolve().parent))
import tinylang  # noqa: E402

HARD = {"kvstore": (setup_kvstore, check_kvstore), "pipeline": (setup_pipeline, check_pipeline), "refactor": (setup_refactor, check_refactor),
        "tinylang": (tinylang.setup, tinylang.check)}


def selftest() -> None:
    """Fixture sanity: the reference passes, the shipped state fails, and every injected bug alone is detectable."""
    hidden = Path(tempfile.mkdtemp(prefix="st_")) / "h.csv"
    _make_sales(hidden, 977, 260)
    want = _reference_report(hidden)
    assert want.startswith("RELATORIO"), want[:200]
    for bug in BUGS:
        d = Path(tempfile.mkdtemp(prefix="st_bug_"))
        _write_pipeline(d, [bug])
        p = _run([PY, "-m", "salesrep.cli", str(hidden)], d)
        assert p.returncode != 0 or p.stdout != want, f"bug not detectable on hidden data: {bug[2]!r}"
    d = Path(tempfile.mkdtemp(prefix="st_pipe_"))
    setup_pipeline(d)
    assert not check_pipeline(d)[0]
    _write_pipeline(d, [])
    assert check_pipeline(d)[0], check_pipeline(d)
    d = Path(tempfile.mkdtemp(prefix="st_ref_"))
    setup_refactor(d)
    assert not check_refactor(d)[0]
    print("pipeline: reference ok, 9/9 bugs detectable · refactor: unrefactored state fails as expected")
    print(want)


if __name__ == "__main__":
    selftest()
