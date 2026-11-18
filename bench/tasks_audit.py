"""Wide benchmark task that a script cannot solve: judging code against what its docstring promises.
  audit  18 modules with two functions each. In about half of the modules one function does not do what its docstring
         says (a boundary, a tie-break, an order, a rounding rule). Report, per module, the name of the faulty function
         or "ok". There is nothing to parse and no test suite: each function has to be read (or tried) on its own.
Run `python bench/tasks_audit.py` to self-test the bank: every good body passes its cases, every bad body fails one."""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

SEED, FILES, FAULTY = 20261119, 18, 10

# (signature, docstring, good body, bad body, cases as (args, expected))
BANK = [
    ("limitar(x, minimo, maximo)", "Devolve x restrito ao intervalo [minimo, maximo].",
     "return max(minimo, min(x, maximo))", "return min(minimo, max(x, maximo))", [((5, 0, 10), 5), ((-3, 0, 10), 0)]),
    ("fatiar(itens, tamanho)", "Divide a lista em pedaços de `tamanho` itens; o último pedaço pode ser menor.",
     "return [itens[i:i + tamanho] for i in range(0, len(itens), tamanho)]",
     "return [itens[i:i + tamanho] for i in range(0, len(itens) - tamanho + 1, tamanho)]", [(([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])]),
    ("mediana(valores)", "Mediana da lista; com quantidade par, a média dos dois valores centrais. Não altera a lista recebida.",
     "s = sorted(valores)\nmeio = len(s) // 2\nreturn s[meio] if len(s) % 2 else (s[meio - 1] + s[meio]) / 2",
     "s = sorted(valores)\nmeio = len(s) // 2\nreturn s[meio] if len(s) % 2 else (s[meio] + s[meio + 1]) / 2", [(([4, 1, 3, 2, 9, 7],), 3.5), (([3, 1, 2],), 2)]),
    ("sem_repetidos(itens)", "Remove os repetidos, mantendo cada item na posição da sua primeira ocorrência.",
     "vistos, saida = set(), []\nfor item in itens:\n    if item not in vistos:\n        vistos.add(item)\n        saida.append(item)\nreturn saida",
     "return list(dict.fromkeys(reversed(itens)))[::-1]", [(([1, 2, 1, 3],), [1, 2, 3])]),
    ("bissexto(ano)", "True se o ano é bissexto no calendário gregoriano.",
     "return ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)", "return ano % 4 == 0 and ano % 100 != 0", [((2000,), True), ((1900,), False), ((2024,), True)]),
    ("maximo_corrente(valores)", "Lista em que a posição i traz o maior valor de valores[:i + 1].",
     "saida = []\nfor v in valores:\n    saida.append(v if not saida else max(saida[-1], v))\nreturn saida",
     "saida, atual = [], 0\nfor v in valores:\n    atual = max(atual, v)\n    saida.append(atual)\nreturn saida", [(([-3, -1, -2],), [-3, -1, -1]), (([1, 3, 2],), [1, 3, 3])]),
    ("minutos(texto)", "Converte durações como '1h30m', '45m' ou '12h' em minutos.",
     "m = re.fullmatch(r'(?:(\\d+)h)?(?:(\\d+)m)?', texto)\nreturn int(m.group(1) or 0) * 60 + int(m.group(2) or 0)",
     "m = re.fullmatch(r'(?:(\\d)h)?(?:(\\d+)m)?', texto)\nreturn int(m.group(1) or 0) * 60 + int(m.group(2) or 0)", [(("1h30m",), 90), (("12h",), 720), (("45m",), 45)]),
    ("contar_palavras(texto)", "Conta cada palavra sem diferenciar maiúsculas de minúsculas e sem a pontuação .,!? nas pontas.",
     "contagem = {}\nfor p in texto.lower().split():\n    p = p.strip('.,!?')\n    if p:\n        contagem[p] = contagem.get(p, 0) + 1\nreturn contagem",
     "contagem = {}\nfor p in texto.lower().split():\n    p = p.strip('.,')\n    if p:\n        contagem[p] = contagem.get(p, 0) + 1\nreturn contagem",
     [(("A a. B!",), {"a": 2, "b": 1})]),
    ("intercalar(a, b)", "Junta duas listas em ordem crescente numa só lista em ordem crescente.",
     "i = j = 0\nsaida = []\nwhile i < len(a) and j < len(b):\n    if a[i] <= b[j]:\n        saida.append(a[i])\n        i += 1\n    else:\n        saida.append(b[j])\n        j += 1\nreturn saida + a[i:] + b[j:]",
     "i = j = 0\nsaida = []\nwhile i < len(a) and j < len(b):\n    if a[i] <= b[j]:\n        saida.append(a[i])\n        i += 1\n    else:\n        saida.append(b[j])\n        j += 1\nreturn saida + a[i:]",
     [(([1, 4], [2, 3, 9]), [1, 2, 3, 4, 9]), (([5], [1]), [1, 5])]),
    ("buscar(itens, alvo)", "Índice de `alvo` numa lista em ordem crescente, ou -1 se não estiver nela.",
     "ini, fim = 0, len(itens) - 1\nwhile ini <= fim:\n    meio = (ini + fim) // 2\n    if itens[meio] == alvo:\n        return meio\n    if itens[meio] < alvo:\n        ini = meio + 1\n    else:\n        fim = meio - 1\nreturn -1",
     "ini, fim = 0, len(itens) - 1\nwhile ini < fim:\n    meio = (ini + fim) // 2\n    if itens[meio] == alvo:\n        return meio\n    if itens[meio] < alvo:\n        ini = meio + 1\n    else:\n        fim = meio - 1\nreturn -1",
     [(([1, 3, 5], 5), 2), (([1, 3, 5], 3), 1), (([1, 3, 5], 4), -1)]),
    ("arredondar(x)", "Arredonda para o inteiro mais próximo; a metade exata sobe (2.5 vira 3, -2.5 vira -2).",
     "return math.floor(x + 0.5)", "return round(x)", [((2.5,), 3), ((-2.5,), -2), ((1.4,), 1)]),
    ("achatar(lista)", "Desfaz apenas um nível de aninhamento: [[1, [2]], 3] vira [1, [2], 3].",
     "saida = []\nfor item in lista:\n    saida.extend(item if isinstance(item, list) else [item])\nreturn saida",
     "saida = []\nfor item in lista:\n    saida.extend(achatar(item) if isinstance(item, list) else [item])\nreturn saida", [(([[1, [2]], 3],), [1, [2], 3])]),
    ("dividir(a, b, padrao=0)", "a / b, ou `padrao` quando b é zero.",
     "return a / b if b != 0 else padrao", "return a / b if b > 0 else padrao", [((6, -3), -2.0), ((1, 0), 0), ((6, 3), 2.0)]),
    ("iniciais(nome)", "Iniciais em maiúsculas de cada palavra, ignorando espaços sobrando: ' ana  maria prado' vira 'AMP'.",
     "return ''.join(p[0].upper() for p in nome.split())", "return ''.join(p[:1].upper() for p in nome.strip().split(' ', 2))",
     [((" ana  maria prado",), "AMP"), (("rui camargo de sá",), "RCDS")]),
    ("dias_do_mes(ano, mes)", "Quantidade de dias do mês (1 a 12) no calendário gregoriano.",
     "if mes == 2:\n    return 29 if ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0) else 28\nreturn 30 if mes in (4, 6, 9, 11) else 31",
     "if mes == 2:\n    return 29 if ano % 4 == 0 else 28\nreturn 30 if mes in (4, 6, 9, 11) else 31", [((1900, 2), 28), ((2024, 2), 29), ((2025, 9), 30)]),
    ("encurtar(texto, limite)", "No máximo `limite` caracteres (limite >= 3); quando corta, termina em '...' e o total tem exatamente `limite`.",
     "return texto if len(texto) <= limite else texto[:limite - 3] + '...'", "return texto if len(texto) <= limite else texto[:limite] + '...'",
     [(("abcdefgh", 5), "ab..."), (("abc", 5), "abc")]),
    ("melhores(pontos, n)", "Os n nomes com mais pontos, do maior para o menor; empate decide pelo nome em ordem alfabética.",
     "return sorted(pontos, key=lambda nome: (-pontos[nome], nome))[:n]", "return sorted(pontos, key=pontos.get, reverse=True)[:n]",
     [(({"bia": 7, "ana": 7, "caio": 9}, 2), ["caio", "ana"])]),
    ("girar(itens, k)", "Gira a lista k posições para a direita: girar([1, 2, 3], 1) dá [3, 1, 2]. k pode passar do tamanho.",
     "if not itens:\n    return []\nk %= len(itens)\nreturn itens[len(itens) - k:] + itens[:len(itens) - k]",
     "if not itens:\n    return []\nk %= len(itens)\nreturn itens[k:] + itens[:k]", [(([1, 2, 3], 1), [3, 1, 2]), (([1, 2, 3, 4], 6), [3, 4, 1, 2])]),
    ("no_periodo(dia, inicio, fim)", "True se `dia` está entre `inicio` e `fim`, contando os dois extremos.",
     "return inicio <= dia <= fim", "return inicio <= dia < fim", [((5, 1, 5), True), ((1, 1, 5), True), ((6, 1, 5), False)]),
    ("media(valores)", "Média aritmética; 0.0 para lista vazia.",
     "return sum(valores) / len(valores) if valores else 0.0", "return sum(valores) // len(valores) if valores else 0.0", [(([1, 2],), 1.5), (([],), 0.0)]),
    ("apelido(texto)", "Minúsculas; espaços e '_' viram '-'; outros símbolos somem; '-' repetidos viram um só; sem '-' nas pontas.",
     "s = re.sub(r'[ _]+', '-', texto.lower())\ns = re.sub(r'[^a-z0-9-]', '', s)\nreturn re.sub(r'-+', '-', s).strip('-')",
     "s = re.sub(r'[ _]+', '-', texto.lower())\ns = re.sub(r'[^a-z0-9-]', '', s)\nreturn s.strip('-')", [(("Sala - 2_B!",), "sala-2-b"), (("  Ana Prado ",), "ana-prado")]),
    ("mascarar(numero)", "Troca por '*' todos os dígitos menos os quatro últimos dígitos; espaços ficam onde estão.",
     "total, vistos, saida = sum(c.isdigit() for c in numero), 0, []\nfor c in numero:\n    if c.isdigit():\n        vistos += 1\n        saida.append(c if vistos > total - 4 else '*')\n    else:\n        saida.append(c)\nreturn ''.join(saida)",
     "corte = len(numero) - 4\nreturn ''.join('*' if c.isdigit() and i < corte else c for i, c in enumerate(numero))",
     [(("1234 5678 90 12",), "**** **** 90 12"), (("12345678",), "****5678")]),
    ("montante(capital, taxa, anos)", "Capital com juros compostos anuais à `taxa` (0.1 = 10%) por `anos`, com 2 casas.",
     "return round(capital * (1 + taxa) ** anos, 2)", "return round(capital * (1 + taxa * anos), 2)", [((1000, 0.1, 2), 1210.0), ((500, 0.2, 1), 600.0)]),
    ("maior_sequencia(valores)", "Tamanho da maior sequência de valores iguais e vizinhos; 0 para lista vazia.",
     "melhor = atual = 0\nanterior = object()\nfor v in valores:\n    atual = atual + 1 if v == anterior else 1\n    melhor = max(melhor, atual)\n    anterior = v\nreturn melhor",
     "melhor, atual, anterior = 0, 0, object()\nfor v in valores:\n    if v == anterior:\n        atual += 1\n    else:\n        melhor = max(melhor, atual)\n        atual = 1\n    anterior = v\nreturn melhor",
     [(([1, 2, 2],), 2), (([3, 3, 3, 1],), 3), (([],), 0)]),
    ("sobrepoe(a, b)", "True se os intervalos fechados (inicio, fim) têm ao menos um ponto em comum; encostar conta.",
     "return a[0] <= b[1] and b[0] <= a[1]", "return a[0] < b[1] and b[0] < a[1]", [(((1, 2), (2, 3)), True), (((1, 2), (3, 4)), False)]),
    ("codigo(n, largura)", "Número com zeros à esquerda até `largura` caracteres; o sinal de menos fica na frente: (-5, 4) dá '-005'.",
     "return str(n).zfill(largura)", "return str(n).rjust(largura, '0')", [((-5, 4), "-005"), ((42, 5), "00042")]),
    ("por_tamanho(palavras)", "Dicionário tamanho -> palavras daquele tamanho, cada lista em ordem alfabética.",
     "grupos = {}\nfor p in palavras:\n    grupos.setdefault(len(p), []).append(p)\nreturn {t: sorted(ps) for t, ps in grupos.items()}",
     "grupos = {}\nfor p in sorted(palavras, key=len):\n    grupos.setdefault(len(p), []).append(p)\nreturn grupos", [((["sol", "mar", "lua", "céu5"],), {3: ["lua", "mar", "sol"], 4: ["céu5"]})]),
    ("ultima_posicao(itens, x)", "Índice da última ocorrência de x, ou -1 se não houver.",
     "for i in range(len(itens) - 1, -1, -1):\n    if itens[i] == x:\n        return i\nreturn -1",
     "if x not in itens:\n    return -1\nreturn len(itens) - itens[::-1].index(x)", [(([1, 2, 1], 1), 2), (([1, 2], 9), -1)]),
    ("percentual(parte, total)", "parte / total em porcentagem, com 1 casa decimal; 0.0 quando total é zero.",
     "return round(parte / total * 100, 1) if total else 0.0", "return round(parte / total, 1) * 100 if total else 0.0", [((1, 3), 33.3), ((1, 0), 0.0), ((1, 2), 50.0)]),
    ("palindromo(texto)", "True se o texto se lê igual nos dois sentidos, ignorando maiúsculas, espaços e pontuação.",
     "letras = [c.lower() for c in texto if c.isalnum()]\nreturn letras == letras[::-1]",
     "letras = [c.lower() for c in texto if not c.isspace()]\nreturn letras == letras[::-1]", [(("Ab, a",), True), (("Ana",), True), (("casa",), False)]),
    ("acumulado(valores)", "Somas parciais: a posição i traz a soma de valores[:i + 1].",
     "saida, total = [], 0\nfor v in valores:\n    total += v\n    saida.append(total)\nreturn saida",
     "saida, total = [], 0\nfor v in valores:\n    saida.append(total)\n    total += v\nreturn saida", [(([1, 2, 3],), [1, 3, 6])]),
    ("intervalo(a, b)", "Minutos de 'HH:MM' até 'HH:MM'; se b é mais cedo que a, considera que b é no dia seguinte.",
     "ma = int(a[:2]) * 60 + int(a[3:])\nmb = int(b[:2]) * 60 + int(b[3:])\nreturn mb - ma if mb >= ma else mb - ma + 1440",
     "ma = int(a[:2]) * 60 + int(a[3:])\nmb = int(b[:2]) * 60 + int(b[3:])\nreturn abs(mb - ma)", [(("23:00", "01:00"), 120), (("08:15", "09:00"), 45)]),
    ("vice(valores)", "Segundo maior valor distinto; None se houver menos de dois valores distintos.",
     "s = sorted(set(valores))\nreturn s[-2] if len(s) >= 2 else None", "s = sorted(valores)\nreturn s[-2] if len(set(s)) >= 2 else None",
     [(([3, 3, 1],), 1), (([2, 2],), None), (([1, 5, 4],), 4)]),
    ("com_desconto(preco, pct)", "Preço com desconto de pct por cento, nunca abaixo de zero, com 2 casas.",
     "return round(max(preco * (1 - pct / 100), 0), 2)", "return round(preco * (1 - pct / 100), 2)",
     [((10, 150), 0.0), ((200, 25), 150.0)]),
    ("separar_nome(completo)", "Tupla (primeiro nome, resto); o resto é '' quando só há uma palavra.",
     "primeiro, _, resto = completo.strip().partition(' ')\nreturn primeiro, resto.strip()",
     "resto, _, ultimo = completo.strip().rpartition(' ')\nreturn (resto, ultimo) if resto else (ultimo, '')",
     [(("ana maria prado",), ("ana", "maria prado")), (("rui",), ("rui", ""))]),
    ("na_tolerancia(a, b, tol)", "True se a diferença entre a e b, em valor absoluto, não passa de tol.",
     "return abs(a - b) <= tol", "return a - b <= tol", [((1, 5, 2), False), ((5, 1, 2), False), ((3, 2, 1), True)]),
]


def _source(entry, bad: bool) -> str:
    sig, doc, good, wrong, _ = entry
    body = (wrong if bad else good).rstrip("\n")
    return f"def {sig}:\n    \"\"\"{doc}\"\"\"\n" + "\n".join("    " + l for l in body.splitlines()) + "\n"


def _name(entry) -> str:
    return entry[0].split("(")[0]


def _layout() -> dict[str, tuple[str, str]]:
    """file name -> (source, answer). Deterministic: check() rebuilds the answers."""
    r = random.Random(SEED)
    bank = BANK[:]
    r.shuffle(bank)
    faulty = set(r.sample(range(FILES), FAULTY))
    out = {}
    for i in range(FILES):
        pair = bank[2 * i: 2 * i + 2]
        bad = r.randrange(2) if i in faulty else -1
        src = "import math\nimport re\n\n\n" + "\n\n".join(_source(e, j == bad) for j, e in enumerate(pair))
        out[f"mod_{i + 1:02d}.py"] = (src, _name(pair[bad]) if bad >= 0 else "ok")
    return out


LEIA = """# Auditoria

Cada arquivo em `modulos/` tem duas funções. A docstring de cada função é a especificação: diz exatamente o que a função deve fazer.

Em alguns arquivos, UMA das duas funções não cumpre a própria docstring (um limite, um desempate, uma ordem, uma regra de
arredondamento, um caso de borda). Nos outros arquivos as duas funções estão corretas. Nunca há duas funções erradas no mesmo arquivo.

Entradas de que a docstring não fala (lista vazia quando ela não menciona esse caso, tipos trocados) não contam como defeito.

Não corrija nada. Entregue `auditoria.json` na raiz, com uma chave por arquivo de `modulos/`:

    {"mod_01.py": "ok", "mod_02.py": "nome_da_funcao_errada", ...}

O valor é "ok" quando as duas funções cumprem a docstring, ou o nome da função que não cumpre.
"""


def setup_audit(d: Path) -> dict:
    (d / "modulos").mkdir()
    for name, (src, _) in _layout().items():
        (d / "modulos" / name).write_text(src, encoding="utf-8")
    (d / "LEIA.md").write_text(LEIA, encoding="utf-8")
    return {"prompt": "Leia LEIA.md e produza `auditoria.json`: para cada arquivo de `modulos/`, diga se as duas funções cumprem o que a "
                      "docstring promete (\"ok\") ou qual delas não cumpre. Os defeitos são sutis: examine cada função com cuidado, "
                      "pensando nos casos de borda que a docstring cobre. Confira o resultado antes de dar por concluído."}


def check_audit(d: Path):
    try:
        got = json.loads((d / "auditoria.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, f"auditoria.json: {type(e).__name__}"
    want = {name: ans for name, (_, ans) in _layout().items()}
    got = got if isinstance(got, dict) else {}
    norm = lambda v: str(v).strip().lower().split("(")[0]  # noqa: E731
    right = sum(norm(got.get(n)) == a for n, a in want.items())
    missed = sum(a != "ok" and norm(got.get(n)) == "ok" for n, a in want.items())
    false = sum(a == "ok" and norm(got.get(n)) != "ok" for n, a in want.items())
    return right == FILES, f"{right}/{FILES} modules ({missed} bugs missed, {false} false alarms)"


AUDIT = {"audit": (setup_audit, check_audit)}


def selftest() -> None:
    import math
    import re
    assert len(BANK) == 2 * FILES and len({_name(e) for e in BANK}) == len(BANK)
    for entry in BANK:
        for bad in (False, True):
            ns = {"math": math, "re": re}
            exec(_source(entry, bad), ns)
            fn, wrong = ns[_name(entry)], 0
            for args, expected in entry[4]:
                try:
                    wrong += fn(*args) != expected
                except Exception:
                    wrong += 1
            assert (wrong > 0) == bad, (_name(entry), "bad body passes every case" if bad else "good body fails a case")
    d = Path(tempfile.mkdtemp(prefix="audit_"))
    setup_audit(d)
    assert not check_audit(d)[0]
    (d / "auditoria.json").write_text(json.dumps({n: a for n, (_, a) in _layout().items()}), encoding="utf-8")
    assert check_audit(d)[0], check_audit(d)
    (d / "auditoria.json").write_text(json.dumps({n: "ok" for n in _layout()}), encoding="utf-8")
    print("audit: bank ok ·", check_audit(d)[1], "when everything is called ok ·", sum(len(s) for s, _ in _layout().values()), "chars")
    print(_layout()["mod_01.py"][0])


if __name__ == "__main__":
    selftest()
