"""Data analysis task: a full analysis of the UCI Bank Marketing base (bank-full.csv, CC BY 4.0).
The file is not shipped: download it from https://archive.ics.uci.edu/dataset/222/bank+marketing and put it in bench/data/,
or point HANGAR_BENCH_BANK at it. An open analysis has no single right answer, so the check scores facts that do:
numbers recomputed from the base, and the choices a careful analyst makes (the call duration is only known after the call)."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROMPT = """O arquivo bank-full.csv (separador ';') nesta pasta registra os contatos de uma campanha de telemarketing de um banco. \
A coluna y diz se o cliente aderiu ao depósito a prazo.

Faça a análise completa da base e entregue dois arquivos nesta pasta:

1. relatorio.html: relatório em português que abre sozinho no navegador, com os gráficos embutidos no próprio arquivo. \
Cubra a qualidade dos dados, o perfil dos clientes, o que mais se relaciona com a adesão, um modelo para escolher \
para quem ligar na próxima campanha e recomendações práticas.

2. resumo.json com as chaves: linhas, colunas, valores_nulos, taxa_adesao_pct, mes_maior_adesao, \
adesao_poutcome_success_pct e modelo (um objeto com algoritmo, auc_teste e variaveis_usadas).

Python com pandas, numpy, scikit-learn e matplotlib já está instalado; não instale nada."""


def source() -> Path:
    return Path(os.environ.get("HANGAR_BENCH_BANK") or ROOT / "bench" / "data" / "bank-full.csv")


def setup_bank(d: Path) -> dict | None:
    if not source().is_file():
        return None
    shutil.copy(source(), d / "bank-full.csv")
    return {"prompt": PROMPT}


def _num(v) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group().replace(",", ".")) if m else None


def _near(v, want: float, tol: float) -> bool:
    n = _num(v)
    return n is not None and abs(n - want) <= tol


def score_bank(d: Path) -> tuple[list[str], list[str]]:
    """(items met, items missed)."""
    html = (d / "relatorio.html").read_text(encoding="utf-8", errors="replace") if (d / "relatorio.html").is_file() else ""
    try:
        js = json.loads((d / "resumo.json").read_text(encoding="utf-8-sig"))
    except Exception:
        js = {}
    model = js.get("modelo") if isinstance(js.get("modelo"), dict) else {}
    used = " ".join(map(str, model.get("variaveis_usadas") or [])).lower() if isinstance(model.get("variaveis_usadas"), list) else ""
    low = re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=\s]+", "", html).lower()      # text only: an embedded image is not prose
    auc = _num(model.get("auc_teste"))
    charts = len(re.findall(r"<img[^>]+src=[\"']data:image", html, re.I)) + len(re.findall(r"<svg[\s>]", html, re.I)) + len(re.findall(r"<canvas[\s>]", html, re.I))
    external = re.findall(r"<img[^>]+src=[\"'](?!data:)([^\"']+)", html, re.I)
    items = {
        "linhas": _near(js.get("linhas"), 45211, 0),
        "colunas": _near(js.get("colunas"), 17, 0),
        "sem nulos": _near(js.get("valores_nulos"), 0, 0),
        "taxa de adesão": _near(js.get("taxa_adesao_pct"), 11.70, 0.06),
        "mês de maior adesão": str(js.get("mes_maior_adesao", "")).strip().lower()[:3] == "mar",
        "adesão com poutcome success": _near(js.get("adesao_poutcome_success_pct"), 64.73, 0.15),
        "aponta os 'unknown'": "unknown" in low or "desconhecid" in low,
        "aponta o desbalanceamento": bool(re.search(r"desbalance|desequil|imbalanc", low)),
        "modelo sem duration": bool(used) and "duration" not in used,
        "explica o vazamento de duration": bool(re.search(r"duration|dura[çc][ãa]o", low)) and bool(re.search(
            r"vaza|leak|(depois|ap[óo]s|ao fim|ao final|antes|t[ée]rmino) d[ae] (liga[çc][ãa]o|chamada|contato)", low)),
        "AUC plausível": auc is not None and 0.6 <= auc <= 0.99,
        "4+ gráficos embutidos": charts >= 4 and not external,
        "recomendações": "recomenda" in low,
    }
    return [k for k, v in items.items() if v], [k for k, v in items.items() if not v]


def check_bank(d: Path):
    if not (d / "relatorio.html").is_file() or not (d / "resumo.json").is_file():
        return False, "faltou relatorio.html ou resumo.json"
    met, missed = score_bank(d)
    ok = "linhas" in met and "taxa de adesão" in met and (d / "relatorio.html").stat().st_size > 3000
    return ok, f"score {len(met)}/{len(met) + len(missed)}" + (f"; faltou: {', '.join(missed)}" if missed else "")


def method_bank(d: Path) -> dict[str, bool]:
    """Method choices beyond the checklist, written down after a frontier model made them and before the quality layer was measured:
    the base is in chronological order, so a random split flatters the model and the "best month" is a period effect."""
    low = _text(d)
    return {"validação no tempo": bool(re.search(r"valida[çc][ãa]o temporal|teste temporal|divis[ãa]o temporal|corte temporal|split temporal|"
                                                 r"out[- ]of[- ]time|ordem cronol|cronol[óo]gic|contatos posteriores|treino no passado|"
                                                 r"per[íi]odo de teste|[úu]ltim[oa]s \d+ ?% d[aeo]s (linhas|contatos|registros)", low)),
            "efeito de período": bool(re.search(r"efeito d[eo] per[íi]odo|dentro d[eo] (cada|um mesmo|mesmo) m[êe]s|confund|"
                                                r"n[ãa]o (é|e) (o )?calend[áa]rio|reflete o per[íi]odo|poucos contatos|baixo volume|volume (muito )?(baixo|pequeno)", low))}


# ------------------------------------------------------------------ a second base, which the skill was not written against
SHOP_PROMPT = """O arquivo online_shoppers_intention.csv nesta pasta tem sessões de visita a uma loja online. \
A coluna Revenue diz se a sessão terminou em compra.

Faça a análise completa da base e entregue dois arquivos nesta pasta:

1. relatorio.html: relatório em português que abre sozinho no navegador, com os gráficos embutidos no próprio arquivo. \
Cubra a qualidade dos dados, o perfil das sessões, o que mais se relaciona com a compra, um modelo para decidir, \
quando o visitante chega ao site, a quem oferecer um incentivo, e recomendações práticas.

2. resumo.json com as chaves: linhas, colunas, valores_nulos, linhas_duplicadas, taxa_compra_pct e modelo \
(um objeto com algoritmo, auc_teste e variaveis_usadas).

Python com pandas, numpy, scikit-learn e matplotlib já está instalado; não instale nada."""

# measured while the visitor browses: none of these exists "when the visitor arrives"
IN_SESSION = ("pagevalues", "exitrates", "bouncerates", "productrelated", "administrative", "informational")


def _text(d: Path) -> str:
    html = (d / "relatorio.html").read_text(encoding="utf-8", errors="replace") if (d / "relatorio.html").is_file() else ""
    return re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=\s]+", "", html).lower()


def setup_shop(d: Path) -> dict | None:
    src = source().parent / "online_shoppers_intention.csv"
    if not src.is_file():
        return None
    shutil.copy(src, d / src.name)
    return {"prompt": SHOP_PROMPT}


def score_shop(d: Path) -> tuple[list[str], list[str]]:
    html = (d / "relatorio.html").read_text(encoding="utf-8", errors="replace") if (d / "relatorio.html").is_file() else ""
    try:
        js = json.loads((d / "resumo.json").read_text(encoding="utf-8-sig"))
    except Exception:
        js = {}
    model = js.get("modelo") if isinstance(js.get("modelo"), dict) else {}
    used = re.sub(r"[\s_]", "", " ".join(map(str, model.get("variaveis_usadas") or [])).lower()) if isinstance(model.get("variaveis_usadas"), list) else ""
    low, auc = _text(d), _num(model.get("auc_teste"))
    charts = len(re.findall(r"<img[^>]+src=[\"']data:image", html, re.I)) + len(re.findall(r"<svg[\s>]", html, re.I)) + len(re.findall(r"<canvas[\s>]", html, re.I))
    items = {
        "linhas": _near(js.get("linhas"), 12330, 0),
        "colunas": _near(js.get("colunas"), 18, 0),
        "sem nulos": _near(js.get("valores_nulos"), 0, 0),
        "duplicadas": _near(js.get("linhas_duplicadas"), 125, 0),
        "taxa de compra": _near(js.get("taxa_compra_pct"), 15.47, 0.06),
        "aponta o desbalanceamento": bool(re.search(r"desbalance|desequil|imbalanc", low)),
        "modelo sem PageValues": bool(used) and "pagevalues" not in used,
        "explica o vazamento de PageValues": "pagevalues" in re.sub(r"[\s_]", "", low) and bool(re.search(
            r"vaza|leak|(durante|depois|ao longo|ao fim|ao final|no decorrer) d[ae] (sess[ãa]o|visita|navega)|quando (o visitante )?chega", low)),
        "AUC plausível": auc is not None and 0.5 <= auc <= 0.99,
        "4+ gráficos embutidos": charts >= 4,
        "recomendações": "recomenda" in low,
    }
    return [k for k, v in items.items() if v], [k for k, v in items.items() if not v]


def method_shop(d: Path) -> dict[str, bool]:
    """The deeper reading of "when the visitor arrives": every browsing metric is measured during the session, not only PageValues."""
    try:
        model = json.loads((d / "resumo.json").read_text(encoding="utf-8-sig")).get("modelo") or {}
    except Exception:
        model = {}
    used = re.sub(r"[\s_]", "", " ".join(map(str, model.get("variaveis_usadas") or [])).lower())
    return {"modelo só com o que existe na chegada": bool(used) and not any(k in used for k in IN_SESSION),
            "trata as duplicadas": bool(re.search(r"duplicad", _text(d)))}


def check_shop(d: Path):
    if not (d / "relatorio.html").is_file() or not (d / "resumo.json").is_file():
        return False, "faltou relatorio.html ou resumo.json"
    met, missed = score_shop(d)
    ok = "linhas" in met and "taxa de compra" in met and (d / "relatorio.html").stat().st_size > 3000
    return ok, f"score {len(met)}/{len(met) + len(missed)}" + (f"; faltou: {', '.join(missed)}" if missed else "")


DATA = {"bank": (setup_bank, check_bank), "shop": (setup_shop, check_shop)}
