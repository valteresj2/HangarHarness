"""Wide benchmark task: many independent items, each needing a careful read. One context holding all of them is the
failure mode this measures; nothing here is hard for a reader who looks at one document at a time.
  contracts  24 contracts in prose, each followed by 5-8 amendments (some revoked later). Report, per contract, the
             value, the deadline and the person in charge that are in force. Checked field by field against the generator.
Run `python bench/tasks_wide.py` to self-test the fixture."""
from __future__ import annotations

import datetime as dt
import json
import random
import tempfile
from pathlib import Path

SEED, N = 20261118, 24
PEOPLE = ["Ana Prado", "Bruno Seixas", "Carla Mota", "Diego Farias", "Elisa Rocha", "Fábio Nunes", "Gilda Reis", "Heitor Lima",
          "Inês Barros", "Jonas Peixoto", "Lívia Amaral", "Marcos Viana", "Nádia Couto", "Otávio Brito", "Paula Serra", "Rui Camargo"]
FIRMS = ["Atlas Engenharia", "Boreal Sistemas", "Cedro Logística", "Delta Manutenção", "Estrela Alimentos", "Farol Segurança",
         "Granito Obras", "Horizonte Dados", "Íris Consultoria", "Juta Embalagens", "Lume Energia", "Mirante Transportes"]
OBJECTS = ["manutenção preventiva dos elevadores", "fornecimento de refeições ao turno da noite", "limpeza das áreas comuns",
           "suporte à rede interna", "vigilância do pátio", "transporte de insumos entre as unidades", "calibração dos instrumentos",
           "reforma do telhado do galpão 2", "digitalização do arquivo morto", "locação de empilhadeiras"]
FILLER = [
    "As partes declaram ter lido e compreendido todas as cláusulas, obrigando-se a cumpri-las de boa-fé.",
    "A contratada manterá, durante toda a vigência, as condições de habilitação exigidas na assinatura.",
    "Eventuais tributos incidentes sobre o objeto correm por conta da parte a quem a lei os atribuir.",
    "A fiscalização poderá solicitar relatórios mensais, que serão entregues em até cinco dias úteis.",
    "Nenhuma tolerância quanto ao descumprimento de obrigação importará em novação ou renúncia de direito.",
    "As comunicações entre as partes serão feitas por escrito e dirigidas aos endereços do preâmbulo.",
    "A contratada responde pelos danos causados por seus empregados nas dependências da contratante.",
    "O foro da comarca da sede da contratante é o competente para dirimir as questões deste instrumento.",
    "Os materiais empregados deverão ser novos e de primeira qualidade, sujeitos a recusa pela fiscalização.",
    "A contratante poderá suspender os serviços por até trinta dias sem que isso gere direito a indenização.",
    "Fica vedada a subcontratação total do objeto; a parcial depende de anuência prévia e escrita.",
    "Os empregados da contratada usarão identificação visível enquanto estiverem nas áreas da contratante.",
]


def _money(v: int) -> str:
    return f"R$ {v:,}".replace(",", ".") + ",00"


def _date(d: dt.date) -> str:
    months = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{d.day} de {months[d.month - 1]} de {d.year}"


def _apply(state: dict, ev: dict) -> None:
    k = ev["kind"]
    if k == "value_set":
        state["valor"] = ev["value"]
    elif k == "value_add":
        state["valor"] += ev["delta"]
    elif k == "value_pct":
        state["valor"] += state["valor"] * ev["pct"] // 100
    elif k == "date_set":
        state["prazo"] = ev["date"]
    elif k == "date_add":
        state["prazo"] = state["prazo"] + dt.timedelta(days=ev["days"])
    elif k == "person":
        state["responsavel"] = ev["name"]


def _final(base: dict, events: list[dict]) -> dict:
    """An amendment that a later one revokes is treated as if it had never existed; the rest apply in order."""
    dead = {ev["target"] for ev in events if ev["kind"] == "revoke"}
    state = dict(base)
    for i, ev in enumerate(events, 1):
        if i not in dead and ev["kind"] != "revoke":
            _apply(state, ev)
    return state


def _text(ev: dict, r: random.Random) -> str:
    k = ev["kind"]
    if k == "value_set":
        return r.choice(["O valor global do contrato passa a ser de {v}.", "Fica o valor total repactuado em {v}.",
                         "As partes ajustam que o preço global, a partir desta data, é de {v}."]).format(v=_money(ev["value"]))
    if k == "value_add":
        up, v = ev["delta"] > 0, _money(abs(ev["delta"]))
        return (r.choice(["Acresce-se ao valor vigente a quantia de {v}.", "O valor em vigor fica aumentado em {v}, em razão de serviços adicionais."])
                if up else r.choice(["Suprime-se do valor vigente a quantia de {v}.", "O valor em vigor fica reduzido em {v}, por supressão de itens."])).format(v=v)
    if k == "value_pct":
        up, p = ev["pct"] > 0, abs(ev["pct"])
        return (r.choice(["Concede-se reajuste de {p}% sobre o valor vigente.", "O valor em vigor é majorado em {p}%."])
                if up else r.choice(["Aplica-se desconto de {p}% sobre o valor vigente.", "O valor em vigor é reduzido em {p}%."])).format(p=p)
    if k == "date_set":
        return r.choice(["O prazo de vigência passa a encerrar-se em {d}.", "Fica o termo final do contrato fixado em {d}."]).format(d=_date(ev["date"]))
    if k == "date_add":
        n = ev["days"]
        return (r.choice(["Prorroga-se o prazo de vigência por {n} dias corridos.", "O termo final em vigor fica adiado em {n} dias corridos."])
                if n > 0 else r.choice(["Antecipa-se o termo final em vigor em {n} dias corridos.", "O prazo de vigência fica reduzido em {n} dias corridos."])).format(n=abs(n))
    if k == "person":
        return r.choice(["A gestão do contrato passa a caber a {n}, em substituição ao gestor anterior.",
                         "Designa-se {n} como responsável pelo contrato a partir desta data."]).format(n=ev["name"])
    return r.choice(["Fica sem efeito o Aditivo nº {t}, como se nunca tivesse sido firmado.",
                     "Revoga-se integralmente o Aditivo nº {t}, que deixa de produzir qualquer efeito desde a origem."]).format(t=ev["target"])


def _contract(i: int, r: random.Random) -> tuple[str, dict]:
    base = {"valor": r.randrange(40, 400) * 1000, "prazo": dt.date(2026, 1, 1) + dt.timedelta(days=r.randrange(200, 500)),
            "responsavel": r.choice(PEOPLE)}
    events: list[dict] = []
    for n in range(1, r.randrange(5, 9) + 1):
        live = [j for j, ev in enumerate(events, 1) if ev["kind"] != "revoke" and j not in {e["target"] for e in events if e["kind"] == "revoke"}]
        kind = r.choice(["value_set", "value_add", "value_add", "value_pct", "date_set", "date_add", "date_add", "person", "revoke", "revoke"])
        if kind == "revoke" and not live:
            kind = "value_add"
        now = _final(base, events)
        if kind == "value_pct" and now["valor"] % 100:
            kind = "value_add"
        if kind == "value_set":
            ev = {"kind": kind, "value": r.randrange(40, 400) * 1000}
        elif kind == "value_add":
            ev = {"kind": kind, "delta": r.choice([-1, 1, 1]) * r.randrange(2, 30) * 500}
        elif kind == "value_pct":
            ev = {"kind": kind, "pct": r.choice([-20, -10, -5, 5, 10, 20, 25])}
        elif kind == "date_set":
            ev = {"kind": kind, "date": now["prazo"] + dt.timedelta(days=r.randrange(-60, 200))}
        elif kind == "date_add":
            ev = {"kind": kind, "days": r.choice([-30, -15, 15, 30, 45, 60, 90, 120])}
        elif kind == "person":
            ev = {"kind": kind, "name": r.choice([p for p in PEOPLE if p != now["responsavel"]])}
        else:
            ev = {"kind": kind, "target": r.choice(live)}
        events.append(ev)
        if _final(base, events)["valor"] <= 0:           # a contract cannot be worth nothing: take the amendment back
            events.pop()
    firm, obj, signed = r.choice(FIRMS), r.choice(OBJECTS), dt.date(2025, r.randrange(1, 13), r.randrange(1, 28))
    out = [f"CONTRATO Nº {i:03d}/2025", "",
           f"Contratante: Companhia Vale do Sol. Contratada: {firm}. Objeto: {obj}.",
           f"Firmado em {_date(signed)}.", "",
           f"Cláusula 1ª. O valor global do contrato é de {_money(base['valor'])}.",
           f"Cláusula 2ª. O prazo de vigência encerra-se em {_date(base['prazo'])}.",
           f"Cláusula 3ª. A gestão do contrato cabe a {base['responsavel']}."]
    for c, line in enumerate(r.sample(FILLER, 6), 4):
        out.append(f"Cláusula {c}ª. {line}")
    when = signed
    for n, ev in enumerate(events, 1):
        when += dt.timedelta(days=r.randrange(20, 70))
        out += ["", f"ADITIVO Nº {n}, de {_date(when)}", f"Cláusula única. {_text(ev, r)}"]
        out += [f"Parágrafo {p}º. {line}" for p, line in enumerate(r.sample(FILLER, r.randrange(1, 4)), 1)]
        out.append("Permanecem inalteradas as demais cláusulas que não conflitem com este aditivo.")
    final = _final(base, events)
    return "\n".join(out) + "\n", {"valor": final["valor"], "prazo": final["prazo"].isoformat(), "responsavel": final["responsavel"]}


def _all() -> dict[str, tuple[str, dict]]:
    r = random.Random(SEED)
    return {f"contrato_{i:02d}.txt": _contract(i, r) for i in range(1, N + 1)}


LEIA = """# Contratos

Cada arquivo em `contratos/` traz um contrato e os aditivos firmados depois dele, em ordem.

Regras para saber o que está em vigor:
- os aditivos se aplicam na ordem em que foram firmados, cada um sobre a situação deixada pelos anteriores;
- um aditivo revogado por outro posterior é tratado como se nunca tivesse existido: refaça a conta sem ele;
- percentuais incidem sobre o valor em vigor no momento do aditivo (já sem os aditivos revogados);
- prazos em dias são dias corridos.

Entregue `resumo.json` na raiz, neste formato (uma chave por arquivo de `contratos/`):

    {"contrato_01.txt": {"valor": 152000, "prazo": "2026-11-30", "responsavel": "Nome Sobrenome"}, ...}

`valor` é um inteiro em reais, `prazo` é a data final em vigor (AAAA-MM-DD), `responsavel` é o nome completo de quem gere o contrato.
"""


def setup_contracts(d: Path) -> dict:
    (d / "contratos").mkdir()
    for name, (text, _) in _all().items():
        (d / "contratos" / name).write_text(text, encoding="utf-8")
    (d / "LEIA.md").write_text(LEIA, encoding="utf-8")
    return {"prompt": "Leia LEIA.md e produza `resumo.json` com o valor, o prazo e o responsável em vigor de cada contrato da pasta "
                      "`contratos/`. Cada contrato tem aditivos, e alguns aditivos são revogados depois: siga as regras do LEIA.md "
                      "com cuidado, contrato por contrato. Confira o resultado antes de dar por concluído."}


def check_contracts(d: Path):
    try:
        got = json.loads((d / "resumo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, f"resumo.json: {type(e).__name__}"
    want = {name: ans for name, (_, ans) in _all().items()}
    right, fields = 0, 0
    for name, ans in want.items():
        g = got.get(name) if isinstance(got, dict) else None
        g = g if isinstance(g, dict) else {}
        hit = [str(g.get("valor")).split(".")[0] == str(ans["valor"]), str(g.get("prazo", "")).strip() == ans["prazo"],
               " ".join(str(g.get("responsavel", "")).split()).lower() == ans["responsavel"].lower()]
        fields += sum(hit)
        right += all(hit)
    return right == N, f"{right}/{N} contracts, {fields}/{3 * N} fields"


WIDE = {"contracts": (setup_contracts, check_contracts)}


def selftest() -> None:
    d = Path(tempfile.mkdtemp(prefix="wide_"))
    setup_contracts(d)
    assert not check_contracts(d)[0]
    (d / "resumo.json").write_text(json.dumps({n: a for n, (_, a) in _all().items()}), encoding="utf-8")
    assert check_contracts(d) == (True, f"{N}/{N} contracts, {3 * N}/{3 * N} fields"), check_contracts(d)
    texts = [t for t, _ in _all().values()]
    assert _all() == _all()                              # the generator is deterministic: check() rebuilds the answers
    revoked = sum("Aditivo nº" in t for t in texts)
    print(f"contracts: reference ok · {N} files, {sum(len(t) for t in texts)} chars, {revoked} with a revoked amendment")
    print(texts[0][:1500])


if __name__ == "__main__":
    selftest()
