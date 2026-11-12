"""Showcase task: a full data-analysis job with six deliverables.
  analysis.json   exact figures (checked against a reference implementation)
  dashboard.html  loads in a real browser with no console errors, has charts, no horizontal overflow
  deck.html       HTML presentation
  deck.pptx       valid PowerPoint package with slides and pictures
  assets/hero.*   generated image
  video.mp4       10-30 s, >= 1280 px wide, frames that actually change
The numbers are checked exactly; the design is not something a script can grade - screenshots are saved to
_review/ so a human (or a vision model) can look."""
from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.dom import minidom

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REGIONS = {"Sudeste": 1.9, "Sul": 1.0, "Nordeste": 0.9, "Centro-Oeste": 0.6, "Norte": 0.4}
CHANNELS = ["Loja física", "Online", "Televendas"]
PRODUCTS = {"Notebook Pro 14": ("Computadores", 5400), "Monitor 27 4K": ("Periféricos", 2300), "Teclado Mecânico": ("Periféricos", 480),
            "Mouse Sem Fio": ("Periféricos", 160), "Headset Studio": ("Áudio", 690), "Webcam HD": ("Periféricos", 320),
            "Dock USB-C": ("Acessórios", 540), "SSD Externo 1TB": ("Armazenamento", 610)}

DATA_README = """# Base de vendas 2026 (`vendas.csv`)

Um registro por pedido, separador `,`, codificação UTF-8. Colunas:
`order_id, data (AAAA-MM-DD), regiao, canal, produto, categoria, quantidade, preco_unitario, status, cliente_id`

Regras de negócio para a análise:
- Há linhas duplicadas (mesmo `order_id`): considere apenas a PRIMEIRA ocorrência de cada pedido.
- `status` pode ser `pago`, `enviado` ou `cancelado`. Pedidos cancelados NÃO entram em receita, ticket ou rankings.
- Receita do pedido = `quantidade * preco_unitario`.
- Taxa de cancelamento = pedidos cancelados / total de pedidos distintos (após remover duplicatas).
- Ticket médio = receita / número de pedidos não cancelados.
"""

PROMPT = """Você recebeu a base `vendas.csv` (leia `LEIA-ME.md` para as regras de negócio). Faça uma análise completa e entregue, nesta pasta:

1. `analysis.json` com exatamente estas chaves (valores numéricos sem arredondar além de 2 casas):
   - `receita_total`, `pedidos` (não cancelados), `ticket_medio`, `taxa_cancelamento` (fração entre 0 e 1, 4 casas)
   - `receita_por_regiao` (objeto região -> receita), `receita_por_canal` (objeto canal -> receita)
   - `receita_por_mes` (objeto "AAAA-MM" -> receita, todos os meses da base)
   - `top_produtos` (lista dos 5 produtos de maior receita, cada item `[produto, receita]`, em ordem decrescente)
   - `melhor_mes` ("AAAA-MM" de maior receita)
   - `insights` (lista de 3 a 5 frases, cada uma com pelo menos um número)
2. `dashboard.html`: dashboard moderno e autocontido com KPIs, gráficos e os insights.
3. `deck.html`: apresentação em HTML (6 a 10 slides) contando a história dos dados.
4. `deck.pptx`: a mesma apresentação em PowerPoint, com texto editável e os gráficos como imagens.
5. `assets/hero.png`: uma imagem gerada por modelo de imagem para a capa da apresentação (use-a no deck).
6. `video.mp4`: vídeo de motion graphics de 12 a 20 segundos, 1920x1080, feito com three.js, apresentando os principais números.

Quero design de alto nível: moderno, consistente entre as peças (mesma paleta e tipografia), nada de aparência de template padrão.
Carregue as skills `data-analysis`, `dashboard`, `presentation`, `image-generation` e `motion-video` antes de começar cada parte,
verifique cada peça visualmente antes de concluir e, ao final, liste os arquivos entregues."""


def make_data(path: Path, seed: int = 2026, n: int = 4200) -> None:
    rnd = random.Random(seed)
    rows = []
    names, weights = list(REGIONS), list(REGIONS.values())
    for i in range(1, n + 1):
        month = rnd.choices(range(1, 10), [6, 6, 7, 7, 8, 8, 11, 12, 13])[0]          # the year accelerates from July
        region = rnd.choices(names, weights)[0]
        if region == "Sudeste" and month >= 7 and rnd.random() < 0.35:
            month = rnd.choice([7, 8, 9])                                              # ...and the Southeast drives it
        channel = rnd.choices(CHANNELS, [5, 3 + month * 0.55, 1.2])[0]                 # online grows through the year
        product = rnd.choices(list(PRODUCTS), [5, 6, 9, 12, 7, 6 if month < 6 else 2, 5, 6])[0]   # the webcam fades
        cat, price = PRODUCTS[product]
        price = round(price * rnd.choice([1.0, 1.0, 0.95, 0.9, 1.05]), 2)
        qty = rnd.choices([1, 2, 3, 5], [60, 25, 10, 5])[0]
        status = rnd.choices(["pago", "enviado", "cancelado"], [70, 23, 7 if channel != "Televendas" else 16])[0]
        rows.append([f"PED-{i:05d}", f"2026-{month:02d}-{rnd.randint(1, 28):02d}", region, channel, product, cat, qty, f"{price:.2f}", status,
                     f"C{rnd.randint(1, 1400):04d}"])
    for i in rnd.sample(range(len(rows)), 90):                                         # duplicated orders (later copy differs)
        dup = list(rows[i])
        dup[6] = int(dup[6]) + 1
        rows.append(dup)
    head = rows[:n]
    tail = rows[n:]
    rnd.shuffle(tail)
    rows = head + tail
    rows.sort(key=lambda r: r[1])                                                      # stable: the first occurrence stays first
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "data", "regiao", "canal", "produto", "categoria", "quantidade", "preco_unitario", "status", "cliente_id"])
        w.writerows(rows)


def reference(path: Path) -> dict:
    seen, orders = set(), []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["order_id"] in seen:
                continue
            seen.add(r["order_id"])
            orders.append(r)
    ok = [r for r in orders if r["status"] != "cancelado"]
    rev = lambda r: int(r["quantidade"]) * float(r["preco_unitario"])
    by = lambda key: {k: round(v, 2) for k, v in _sum(ok, key, rev).items()}
    total = sum(rev(r) for r in ok)
    months = _sum(ok, lambda r: r["data"][:7], rev)
    prods = sorted(_sum(ok, lambda r: r["produto"], rev).items(), key=lambda kv: -kv[1])[:5]
    return {"receita_total": round(total, 2), "pedidos": len(ok), "ticket_medio": round(total / len(ok), 2),
            "taxa_cancelamento": round((len(orders) - len(ok)) / len(orders), 4),
            "receita_por_regiao": by(lambda r: r["regiao"]), "receita_por_canal": by(lambda r: r["canal"]),
            "receita_por_mes": {k: round(v, 2) for k, v in sorted(months.items())},
            "top_produtos": [[p, round(v, 2)] for p, v in prods], "melhor_mes": max(months, key=months.get)}


def _sum(rows, key, val) -> dict:
    out = defaultdict(float)
    for r in rows:
        out[key(r)] += val(r)
    return dict(out)


def setup(d: Path) -> dict:
    make_data(d / "vendas.csv")
    (d / "LEIA-ME.md").write_text(DATA_README, encoding="utf-8")
    return {"prompt": PROMPT}


def _close(a, b, tol=0.011) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _page(path: Path, shot: Path, width=1440, height=900) -> dict:
    from hangar.browser import Browser
    probe = """(() => { const svgs = [...document.querySelectorAll('svg')].filter(s => s.querySelectorAll('rect,path,circle,line,polyline,polygon').length >= 4).length;
      const canv = [...document.querySelectorAll('canvas')].filter(c => c.width > 50 && c.height > 50).length;
      const slides = Math.max(document.querySelectorAll('section').length, document.querySelectorAll('[class*=slide]').length);
      const de = document.documentElement;
      return {charts: svgs + canv, slides, text: document.body.innerText.length, overflow: de.scrollWidth - de.clientWidth, body: document.body.innerText.slice(0, 20000)}; })()"""
    with Browser(width, height) as b:
        b.goto(str(path), settle_ms=1500)
        info = b.eval(probe) or {}
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b.screenshot(full_page=True))
        info["errors"] = list(dict.fromkeys(b.errors))
    return info


def check(d: Path):
    fails, notes = [], []
    review = d / "_review"
    ref = reference(d / "vendas.csv")
    # 1. numbers
    try:
        got = json.loads((d / "analysis.json").read_text(encoding="utf-8-sig"))
        for k in ("receita_total", "pedidos", "ticket_medio"):
            if not _close(got.get(k), ref[k]):
                fails.append(f"analysis.{k} ({got.get(k)} != {ref[k]})")
        if not _close(got.get("taxa_cancelamento"), ref["taxa_cancelamento"], 0.00011):
            fails.append(f"analysis.taxa_cancelamento ({got.get('taxa_cancelamento')} != {ref['taxa_cancelamento']})")
        for k in ("receita_por_regiao", "receita_por_canal", "receita_por_mes"):
            g = got.get(k) or {}
            if set(g) != set(ref[k]) or any(not _close(g[x], ref[k][x]) for x in ref[k]):
                fails.append(f"analysis.{k}")
        tp = got.get("top_produtos") or []
        if [x[0] for x in tp] != [x[0] for x in ref["top_produtos"]] or any(not _close(a[1], b[1]) for a, b in zip(tp, ref["top_produtos"])):
            fails.append("analysis.top_produtos")
        if got.get("melhor_mes") != ref["melhor_mes"]:
            fails.append("analysis.melhor_mes")
        ins = got.get("insights") or []
        if not (3 <= len(ins) <= 5) or any(not any(ch.isdigit() for ch in str(s)) for s in ins):
            fails.append("analysis.insights (3-5 frases com número)")
    except Exception as e:
        fails.append(f"analysis.json: {type(e).__name__}: {e}"[:120])
    # 2-3. pages in a real browser
    for name, min_charts, min_slides in (("dashboard.html", 3, 0), ("deck.html", 0, 6)):
        f = d / name
        if not f.is_file():
            fails.append(f"{name} missing")
            continue
        try:
            info = _page(f, review / (f.stem + ".png"))
        except Exception as e:
            fails.append(f"{name}: {type(e).__name__}: {e}"[:140])
            continue
        if info["errors"]:
            fails.append(f"{name}: console errors ({info['errors'][0][:80]})")
        if info["text"] < 300:
            fails.append(f"{name}: almost no text")
        if info["charts"] < min_charts:
            fails.append(f"{name}: {info['charts']} charts (< {min_charts})")
        if info["slides"] < min_slides:
            fails.append(f"{name}: {info['slides']} slides (< {min_slides})")
        if name == "dashboard.html":
            if info["overflow"] > 4:
                fails.append(f"dashboard.html: horizontal overflow {info['overflow']}px at 1440")
            if sum(1 for r in REGIONS if r in info["body"]) < 4:
                fails.append("dashboard.html: regions from the data are not shown")
        notes.append(f"{name}: {info['charts']} charts, {info['slides']} slides, {info['text']} chars")
    # 4. pptx
    f = d / "deck.pptx"
    try:
        with zipfile.ZipFile(f) as z:
            if z.testzip():
                raise ValueError("corrupt zip")
            names = z.namelist()
            slides = [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            media = [n for n in names if n.startswith("ppt/media/")]
            for n in slides:
                minidom.parseString(z.read(n))
            text = sum(z.read(n).count(b"<a:t>") for n in slides)
        if len(slides) < 6:
            fails.append(f"deck.pptx: {len(slides)} slides (< 6)")
        if not media:
            fails.append("deck.pptx: no pictures")
        if text < 12:
            fails.append("deck.pptx: almost no editable text")
        notes.append(f"deck.pptx: {len(slides)} slides, {len(media)} images, {text} text runs")
    except Exception as e:
        fails.append(f"deck.pptx: {type(e).__name__}: {e}"[:120])
    # 5. generated image
    hero = next((p for p in (d / "assets").glob("hero.*")), None) if (d / "assets").is_dir() else None
    try:
        from hangar.pptx import image_size
        w, h = image_size(hero)
        if w < 768:
            fails.append(f"assets/hero: only {w}px wide")
        notes.append(f"hero: {w}x{h}")
    except Exception as e:
        fails.append(f"assets/hero.png: {type(e).__name__}"[:80])
    # 6. video
    v = d / "video.mp4"
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration", "-of", "csv=p=0", str(v)],
                           capture_output=True, text=True, timeout=60)
        w, h, dur = p.stdout.strip().split(",")[:3]
        w, h, dur = int(w), int(h), float(dur)
        if not 10 <= dur <= 30:
            fails.append(f"video.mp4: {dur:.1f}s (expected 12-20)")
        if w < 1280:
            fails.append(f"video.mp4: {w}px wide")
        hashes = set()
        review.mkdir(exist_ok=True)
        for i, frac in enumerate((0.15, 0.5, 0.85)):
            out = review / f"video_{i}.png"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{dur * frac:.2f}", "-i", str(v), "-frames:v", "1", str(out)], capture_output=True, timeout=120)
            hashes.add(hashlib.md5(out.read_bytes()).hexdigest() if out.is_file() else str(i))
        if len(hashes) < 3:
            fails.append("video.mp4: frames at 15% / 50% / 85% are identical")
        notes.append(f"video: {w}x{h} {dur:.1f}s")
    except Exception as e:
        fails.append(f"video.mp4: {type(e).__name__}: {e}"[:100])
    return not fails, ("ok — " if not fails else f"{len(fails)} failed: " + "; ".join(fails)[:300] + " — ") + " · ".join(notes)


STUDIO = {"studio": (setup, check)}


if __name__ == "__main__":
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="studio_ref_"))
    setup(d)
    print(json.dumps(reference(d / "vendas.csv"), ensure_ascii=False, indent=1))
    print("rows", sum(1 for _ in open(d / "vendas.csv", encoding="utf-8")) - 1)
    shutil.rmtree(d, ignore_errors=True)
