"""Benchmark tasks. Each has setup(dir) -> dict(prompt, attachments, answers) and check(dir) -> (ok, detail).
Checks are deterministic code, never an LLM judge."""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run(cmd: list, cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ 1. bugfix
BUGGY = '''"""Utilidades de estoque."""


def parse_price(text):
    """'R$ 1.234,56' -> 1234.56"""
    cleaned = text.replace("R$", "").strip()
    cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def merge_intervals(intervals):
    """Une intervalos (inicio, fim) sobrepostos ou encostados. Retorna ordenado."""
    result = []
    for start, end in intervals:
        if result and start < result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def moving_average(values, window):
    """Media movel simples; devolve len(values) - window + 1 pontos."""
    out = []
    for i in range(len(values) - window):
        out.append(sum(values[i:i + window]) / window)
    return out


def top_sellers(sales, n):
    """sales: dict nome -> quantidade. Top n por quantidade (desc); empate em ordem alfabetica."""
    ranked = sorted(sales.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in ranked[:n]]
'''

TESTS = '''import unittest
from inventory import parse_price, merge_intervals, moving_average, top_sellers


class T(unittest.TestCase):
    def test_price(self):
        self.assertEqual(parse_price("R$ 1.234,56"), 1234.56)
        self.assertEqual(parse_price("R$ 12,50"), 12.5)
        self.assertEqual(parse_price("2.000.000,00"), 2000000.0)

    def test_merge(self):
        self.assertEqual(merge_intervals([(5, 8), (1, 3), (2, 4)]), [(1, 4), (5, 8)])
        self.assertEqual(merge_intervals([(1, 2), (2, 3)]), [(1, 3)])
        self.assertEqual(merge_intervals([]), [])

    def test_moving_average(self):
        self.assertEqual(moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])
        self.assertEqual(moving_average([4, 4], 2), [4.0])

    def test_top(self):
        self.assertEqual(top_sellers({"zinco": 5, "aco": 5, "cobre": 9, "bronze": 1}, 3), ["cobre", "aco", "zinco"])


if __name__ == "__main__":
    unittest.main()
'''


def setup_bugfix(d: Path) -> dict:
    (d / "inventory.py").write_text(BUGGY, encoding="utf-8")
    (d / "test_inventory.py").write_text(TESTS, encoding="utf-8")
    return {"prompt": "Os testes em test_inventory.py estão falhando. Corrija os bugs em inventory.py sem alterar o arquivo de testes "
                      "e confirme rodando `python -m unittest -q`."}


def check_bugfix(d: Path):
    (d / "test_inventory.py").write_text(TESTS, encoding="utf-8")      # pristine tests: tampering does not help
    p = _run([PY, "-m", "unittest", "-q"], d)
    return p.returncode == 0, (p.stderr or p.stdout).strip().splitlines()[-1][:120] if (p.stderr or p.stdout).strip() else ""


# ----------------------------------------------------------------- 2. feature
def _make_log(path: Path, seed: int, n: int) -> None:
    rnd = random.Random(seed)
    paths = ["/api/items", "/api/orders", "/login", "/health", "/api/users", "/static/app.js"]
    lines = []
    for i in range(n):
        st = rnd.choices([200, 201, 304, 400, 404, 500, 503], [60, 6, 8, 6, 10, 6, 4])[0]
        lines.append(f"2026-11-10T14:{i % 60:02d}:{rnd.randrange(60):02d}Z 10.0.{rnd.randrange(4)}.{rnd.randrange(1, 40)} "
                     f"{rnd.choice(['GET', 'POST'])} {rnd.choices(paths, [9, 7, 5, 5, 3, 2])[0]} {st} {rnd.randrange(3, 2400)}")
        if i % 97 == 13:
            lines.append("### linha corrompida ###")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reference(log: Path) -> dict:
    rows = [l.split() for l in log.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if len(r) == 6]
    lat = sorted(int(r[5]) for r in rows)
    counts, paths = {}, {}
    for r in rows:
        counts[r[4]] = counts.get(r[4], 0) + 1
        paths[r[3]] = paths.get(r[3], 0) + 1
    top = sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {"total_requests": len(rows), "unique_ips": len({r[1] for r in rows}), "status_counts": counts,
            "top_paths": [[p, c] for p, c in top], "p95_latency_ms": lat[math.ceil(0.95 * len(lat)) - 1],
            "error_rate": round(sum(1 for r in rows if int(r[4]) >= 400) / len(rows), 4)}


SPEC = """Crie `logstats.py`, uma CLI Python (só biblioteca padrão): `python logstats.py <arquivo.log> <saida.json>`.
Cada linha válida do log tem exatamente 6 campos separados por espaço: `timestamp ip metodo caminho status latencia_ms`.
Linhas com outro número de campos devem ser ignoradas.
O JSON de saída deve ter exatamente estas chaves:
- total_requests: número de linhas válidas
- unique_ips: quantidade de IPs distintos
- status_counts: objeto {"200": n, ...} (status como string)
- top_paths: lista com os 3 caminhos mais acessados, cada item [caminho, contagem], ordenados por contagem desc e, no empate, caminho em ordem alfabética
- p95_latency_ms: percentil 95 pelo método nearest-rank (ordene as latências; índice ceil(0.95*n)-1)
- error_rate: fração de requisições com status >= 400, arredondada para 4 casas
Há um `access.log` de exemplo na pasta. Teste sua CLI com ele antes de terminar."""


def setup_feature(d: Path) -> dict:
    _make_log(d / "access.log", 7, 400)
    return {"prompt": SPEC}


def check_feature(d: Path):
    hidden = d / "_hidden.log"
    _make_log(hidden, 4242, 650)
    out = d / "_hidden_out.json"
    if not (d / "logstats.py").is_file():
        return False, "logstats.py missing"
    p = _run([PY, "logstats.py", str(hidden), str(out)], d)
    if p.returncode != 0 or not out.is_file():
        return False, f"cli failed: {(p.stderr or '').strip()[-120:]}"
    try:
        got, ref = _json(out), _reference(hidden)
    except Exception as e:
        return False, f"bad json: {e}"
    got["top_paths"] = [list(x) for x in got.get("top_paths", [])]
    bad = [k for k in ref if got.get(k) != ref[k]]
    return not bad, "ok" if not bad else f"wrong: {', '.join(bad)}"


# ------------------------------------------------------- media fixture helpers
def _font(d: Path) -> bool:
    for f in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.isfile(f):
            shutil.copy(f, d / "font.ttf")
            return True
    return False


def _ffmpeg(args: list, cwd: Path) -> bool:
    return subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], cwd=str(cwd), capture_output=True).returncode == 0


def _speak(text: str, wav: Path) -> bool:
    """Windows SAPI text-to-speech (English voice when installed)."""
    if os.name != "nt":
        return False
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "try { $s.SelectVoiceByHints('NotSet','NotSet',0,[System.Globalization.CultureInfo]'en-US') } catch {}; "
          f"$s.Rate = -1; $s.SetOutputToWaveFile('{wav}'); $s.Speak('{text}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
    return wav.is_file() and wav.stat().st_size > 2000


# ------------------------------------------------------------------- 3. image
def setup_image(d: Path) -> dict | None:
    if not (shutil.which("ffmpeg") and _font(d)):
        return None
    lines = ["HANGAR SUPPLY CO.", "INVOICE N. HX-48213", "TOTAL: 7,315.40 USD", "DUE DATE: 2026-12-19"]
    vf = []
    for i, text in enumerate(lines):
        (d / f"l{i}.txt").write_text(text, encoding="utf-8")
        vf.append(f"drawtext=fontfile=font.ttf:textfile=l{i}.txt:x=60:y={50 + i * 85}:fontsize={52 if i == 0 else 40}:fontcolor=black")
    ok = _ffmpeg(["-f", "lavfi", "-i", "color=c=white:s=900x420", "-vf", ",".join(vf), "-frames:v", "1", "invoice.png"], d)
    for f in [d / "font.ttf", *d.glob("l*.txt")]:
        f.unlink(missing_ok=True)
    if not ok:
        return None
    return {"prompt": "A imagem anexa (invoice.png) é uma fatura. Extraia o número da fatura, o total e a data de vencimento e grave em "
                      "`dados.json` com as chaves invoice_number (string), total (número) e due_date (YYYY-MM-DD).",
            "attachments": ["invoice.png"]}


def check_image(d: Path):
    try:
        j = _json(d / "dados.json")
        ok = (str(j["invoice_number"]).strip().upper() == "HX-48213" and abs(float(str(j["total"]).replace(",", "")) - 7315.40) < 0.001
              and str(j["due_date"]).strip() == "2026-12-19")
        return ok, json.dumps(j)[:120]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------- 4. audio
def setup_audio(d: Path) -> dict | None:
    if not _speak("Attention. The warehouse code is seven, four, nine, two. The delivery is scheduled for Friday.", d / "aviso.wav"):
        return None
    return {"prompt": "Ouça o áudio anexo (aviso.wav). Grave `resposta.json` com as chaves codigo (o código do armazém, só os dígitos, "
                      "como string) e dia (o dia da entrega, em inglês como foi falado).",
            "attachments": ["aviso.wav"]}


def check_audio(d: Path):
    try:
        j = _json(d / "resposta.json")
        code = "".join(ch for ch in str(j["codigo"]) if ch.isdigit())
        return code == "7492" and "fri" in str(j["dia"]).lower(), json.dumps(j)[:120]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------- 5. video
def setup_video(d: Path) -> dict | None:
    if not (shutil.which("ffmpeg") and _font(d)):
        return None
    if not _speak("Flight H G three zero five is now boarding.", d / "voz.wav"):
        return None
    gates = ["GATE 14", "GATE 27", "GATE 9"]
    vf = ",".join(f"drawtext=fontfile=font.ttf:text='{g}':enable='between(t,{i * 2},{i * 2 + 2})':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=90:fontcolor=white"
                  for i, g in enumerate(gates))
    ok = _ffmpeg(["-f", "lavfi", "-i", "color=c=0x102a43:s=640x360:d=6:r=10", "-i", "voz.wav", "-vf", vf, "-c:v", "libx264",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "6", "embarque.mp4"], d)
    for f in (d / "font.ttf", d / "voz.wav"):
        f.unlink(missing_ok=True)
    if not ok:
        return None
    return {"prompt": "Assista ao vídeo anexo (embarque.mp4). Grave `video.json` com as chaves portoes (lista com os números dos portões "
                      "na ordem em que aparecem na tela, como inteiros) e voo (o número do voo falado no áudio, só os dígitos, como string).",
            "attachments": ["embarque.mp4"]}


def check_video(d: Path):
    try:
        j = _json(d / "video.json")
        gates = [int(str(x).upper().replace("GATE", "").strip()) for x in j["portoes"]]
        voo = "".join(ch for ch in str(j["voo"]) if ch.isdigit())
        return gates == [14, 27, 9] and voo == "305", json.dumps(j)[:120]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- 6. ask_user
def setup_ask(d: Path) -> dict:
    return {"prompt": "Crie `deploy.json` para o novo serviço com as chaves environment (string) e port (inteiro). "
                      "Eu ainda não te disse qual é o ambiente nem a porta, e não há como descobrir isso nos arquivos: pergunte para mim.",
            "answers": ["O ambiente é homolog-7 e a porta é 8443.", "ambiente homolog-7, porta 8443", "homolog-7 / 8443"]}


def check_ask(d: Path):
    try:
        j = _json(d / "deploy.json")
        return str(j["environment"]) == "homolog-7" and int(j["port"]) == 8443, json.dumps(j)[:120]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------- 7. mcp
def setup_mcp(d: Path) -> dict:
    (d / ".mcp.json").write_text(json.dumps({"mcpServers": {"vault": {
        "command": PY, "args": [str(ROOT / "tests" / "mcp_vault_server.py")]}}}), encoding="utf-8")
    return {"prompt": "Use a ferramenta MCP do servidor `vault` para obter o segredo do cofre `alfa` e grave exatamente esse valor "
                      "(sem mais nada) em `secret.txt`.", "mcp": True}


def check_mcp(d: Path):
    try:
        got = (d / "secret.txt").read_text(encoding="utf-8-sig").strip()
        return got == "HNGR-7Q4X-ALFA-2291", got[:60]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


TASKS = {
    "bugfix": (setup_bugfix, check_bugfix), "feature": (setup_feature, check_feature), "image": (setup_image, check_image),
    "audio": (setup_audio, check_audio), "video": (setup_video, check_video), "ask": (setup_ask, check_ask), "mcp": (setup_mcp, check_mcp),
}

from tasks_hard import HARD  # noqa: E402

TASKS.update(HARD)

from tasks_studio import STUDIO  # noqa: E402

TASKS.update(STUDIO)

from tasks_data import DATA  # noqa: E402

TASKS.update(DATA)
