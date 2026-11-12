"""Hard task 4: implement an interpreter for the 'Tiny' language from a written spec.
The reference interpreter below produces the expected output of 32 hidden programs."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SPEC = r'''# Tiny — especificação da linguagem

Implemente `tiny.py` (só biblioteca padrão): `python tiny.py programa.tiny` executa o programa.
Há exemplos com a saída esperada em `examples/` (`*.tiny` e `*.out`). A correção será conferida com dezenas de outros programas.

## Léxico
- Comentário: `#` até o fim da linha.
- Inteiros (`42`), strings entre aspas duplas com escapes `\n`, `\"` e `\\`, identificadores `[A-Za-z_][A-Za-z0-9_]*`.
- Palavras-chave: `let fn return if else while print true false nil and or not`.
- Uma instrução por linha. Dentro de `( )` e `[ ]` quebras de linha são ignoradas. Blocos usam `{ }` e podem ficar
  numa única linha com uma instrução: `if x { print 1 } else { print 2 }`.

## Tipos
int, string, bool, nil, list.

## Instruções
- `let x = expr` — declara no escopo atual (redeclarar sobrescreve).
- `x = expr` — atribui a uma variável existente (procura no escopo local, depois no global); se não existe é erro `undefined variable x`.
- `xs[i] = expr` — atribui a um elemento de lista.
- `print e1, e2, ...` — imprime os valores separados por um espaço, e uma quebra de linha.
- `if cond { ... } else if cond { ... } else { ... }`
- `while cond { ... }`
- `fn nome(a, b) { ... }` — declara uma função (sempre global). Ela passa a existir quando essa linha é executada;
  chamá-la antes disso é `undefined function`. `return expr` ou `return` (devolve nil). Sem `return`, devolve nil.
- Uma expressão sozinha (normalmente uma chamada) também é uma instrução.

## Escopo
Existe o escopo global e um escopo local por chamada de função. Blocos de `if`/`while` NÃO criam escopo.
Dentro de uma função, `let` cria variável local; a leitura procura no local e depois no global. Funções podem ser recursivas.

## Expressões — precedência da menor para a maior
1. `or`
2. `and`
3. `not`
4. `==  !=  <  <=  >  >=`
5. `+  -`
6. `*  /  %`
7. `-` unário
8. chamada `f(x)` e índice `x[i]`
9. literais, variáveis, parênteses, lista `[a, b, c]`

## Semântica
- `+`: int+int, string+string (concatena), list+list (concatena). Qualquer outra combinação: `type error`.
- `-  *  /  %` e `-` unário: só int (senão `type error`). `/` é divisão inteira truncada em direção a zero (`-7 / 2 == -3`);
  `%` tem o sinal do dividendo (`-7 % 2 == -1`). Divisor zero: `division by zero`.
- `<  <=  >  >=`: int com int ou string com string (senão `type error`).
- `==` e `!=`: aceitam quaisquer valores; tipos diferentes nunca são iguais (`1 == true` é false). Listas são iguais se têm os mesmos elementos.
- Operandos e argumentos são avaliados da esquerda para a direita.
- Veracidade: `false` e `nil` são falsos; todo o resto é verdadeiro (inclusive `0`, `""` e `[]`).
- `and`/`or` têm curto-circuito e sempre devolvem bool. `not x` devolve bool.
- Índice: em lista ou string (devolve string de 1 caractere), base 0. Índice negativo ou fora do intervalo: `index out of range`.
  Índice não inteiro, ou indexar outro tipo: `type error`.
- Variável não definida: `undefined variable NOME`. Função não definida: `undefined function NOME`.
  Número errado de argumentos (funções e builtins): `wrong number of arguments`.

## Builtins
- `len(x)` — tamanho de string ou lista (outro tipo: `type error`).
- `push(lista, v)` — acrescenta no fim; devolve nil.
- `pop(lista)` — remove e devolve o último; lista vazia: `pop from empty list`.
- `str(x)` — o mesmo texto que `print` mostraria.
- `int(s)` — string para int (aceita sinal `-`); inválida: `invalid integer`. Se já for int, devolve o próprio.
- `range(n)` — lista `[0, 1, ..., n-1]`.

## Formato do print
int em decimal; string crua; `true`/`false`; `nil`; lista como `[1, "a", true, nil, [2]]`
(strings DENTRO de listas aparecem entre aspas duplas; separador `, `; lista vazia `[]`).

## Erros de execução
Ao ocorrer um erro, o programa para imediatamente, escreve em stdout uma linha `error: <mensagem>` e termina com código de saída 1.
O que já tinha sido impresso antes permanece. Sem erro, o código de saída é 0. Erros de sintaxe não serão testados.
'''


class TinyError(Exception):
    pass


class _Return(Exception):
    def __init__(self, value):
        self.value = value


_TOK = re.compile(r'[ \t\r]*(?:(#[^\n]*)|(\d+)|"((?:\\.|[^"\\])*)"|([A-Za-z_]\w*)|(==|!=|<=|>=|[-+*/%<>=(){}\[\],])|(\n))')
_KW = {"let", "fn", "return", "if", "else", "while", "print", "true", "false", "nil", "and", "or", "not"}


def _lex(src: str) -> list:
    out, pos, depth = [], 0, 0
    src = src.rstrip() + "\n"
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m:
            raise TinyError("syntax error")
        pos = m.end()
        if m.group(1) is not None:
            continue
        if m.group(2) is not None:
            out.append(("int", int(m.group(2))))
        elif m.group(3) is not None:
            out.append(("str", m.group(3).replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")))
        elif m.group(4) is not None:
            out.append(("kw" if m.group(4) in _KW else "id", m.group(4)))
        elif m.group(5) is not None:
            depth += m.group(5) in "([" and 1 or (m.group(5) in ")]" and -1 or 0)
            out.append(("op", m.group(5)))
        elif depth == 0:
            out.append(("nl", "\n"))
    out.append(("eof", ""))
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, kind=None, val=None):
        k, v = self.t[self.i]
        return (kind is None or k == kind) and (val is None or v == val)

    def take(self, kind=None, val=None):
        if not self.peek(kind, val):
            raise TinyError("syntax error")
        self.i += 1
        return self.t[self.i - 1][1]

    def skip_nl(self):
        while self.peek("nl"):
            self.i += 1

    def program(self):
        out = []
        self.skip_nl()
        while not self.peek("eof"):
            out.append(self.stmt())
            self.skip_nl()
        return out

    def block(self):
        self.take("op", "{")
        out = []
        self.skip_nl()
        while not self.peek("op", "}"):
            out.append(self.stmt())
            self.skip_nl()
        self.take("op", "}")
        return out

    def stmt(self):
        if self.peek("kw", "let"):
            self.i += 1
            name = self.take("id")
            self.take("op", "=")
            return ("let", name, self.expr())
        if self.peek("kw", "print"):
            self.i += 1
            args = [self.expr()]
            while self.peek("op", ","):
                self.i += 1
                args.append(self.expr())
            return ("print", args)
        if self.peek("kw", "if"):
            self.i += 1
            cond, then, other = self.expr(), None, []
            then = self.block()
            if self.peek("kw", "else"):
                self.i += 1
                other = [self.stmt()] if self.peek("kw", "if") else self.block()
            return ("if", cond, then, other)
        if self.peek("kw", "while"):
            self.i += 1
            cond = self.expr()
            return ("while", cond, self.block())
        if self.peek("kw", "fn"):
            self.i += 1
            name, params = self.take("id"), []
            self.take("op", "(")
            while not self.peek("op", ")"):
                params.append(self.take("id"))
                if self.peek("op", ","):
                    self.i += 1
            self.take("op", ")")
            return ("fn", name, params, self.block())
        if self.peek("kw", "return"):
            self.i += 1
            return ("return", None if self.peek("nl") or self.peek("op", "}") or self.peek("eof") else self.expr())
        e = self.expr()
        if self.peek("op", "="):
            self.i += 1
            if e[0] == "var":
                return ("assign", e[1], self.expr())
            if e[0] == "index":
                return ("setindex", e[1], e[2], self.expr())
            raise TinyError("syntax error")
        return ("expr", e)

    def expr(self):
        return self.binary(0)

    LEVELS = [("or",), ("and",), None, ("==", "!=", "<", "<=", ">", ">="), ("+", "-"), ("*", "/", "%")]

    def binary(self, lvl):
        if lvl == 2:
            if self.peek("kw", "not"):
                self.i += 1
                return ("not", self.binary(2))
            return self.binary(3)
        if lvl >= len(self.LEVELS):
            return self.unary()
        left = self.binary(lvl + 1)
        while self.t[self.i][0] in ("op", "kw") and self.t[self.i][1] in self.LEVELS[lvl]:
            op = self.t[self.i][1]
            self.i += 1
            left = ("bin", op, left, self.binary(lvl + 1))
        return left

    def unary(self):
        if self.peek("op", "-"):
            self.i += 1
            return ("neg", self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.peek("op", "["):
                self.i += 1
                idx = self.expr()
                self.take("op", "]")
                e = ("index", e, idx)
            elif self.peek("op", "(") and e[0] == "var":
                self.i += 1
                args = []
                while not self.peek("op", ")"):
                    args.append(self.expr())
                    if self.peek("op", ","):
                        self.i += 1
                self.take("op", ")")
                e = ("call", e[1], args)
            else:
                return e

    def primary(self):
        k, v = self.t[self.i]
        self.i += 1
        if k in ("int", "str"):
            return ("lit", v)
        if k == "kw" and v in ("true", "false", "nil"):
            return ("lit", {"true": True, "false": False, "nil": None}[v])
        if k == "id":
            return ("var", v)
        if k == "op" and v == "(":
            e = self.expr()
            self.take("op", ")")
            return e
        if k == "op" and v == "[":
            items = []
            while not self.peek("op", "]"):
                items.append(self.expr())
                if self.peek("op", ","):
                    self.i += 1
            self.take("op", "]")
            return ("list", items)
        raise TinyError("syntax error")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _eq(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    return a == b


def show(v, nested=False) -> str:
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v + '"' if nested else v
    if isinstance(v, list):
        return "[" + ", ".join(show(x, True) for x in v) + "]"
    return str(v)


class Interp:
    def __init__(self):
        self.g, self.fns, self.out = {}, {}, []

    def truthy(self, v):
        return v is not False and v is not None

    def run(self, stmts, loc):
        for s in stmts:
            k = s[0]
            if k == "let":
                (self.g if loc is None else loc)[s[1]] = self.ev(s[2], loc)
            elif k == "assign":
                v = self.ev(s[2], loc)
                if loc is not None and s[1] in loc:
                    loc[s[1]] = v
                elif s[1] in self.g:
                    self.g[s[1]] = v
                else:
                    raise TinyError(f"undefined variable {s[1]}")
            elif k == "setindex":
                target, idx, v = self.ev(s[1], loc), self.ev(s[2], loc), self.ev(s[3], loc)
                if not isinstance(target, list) or not _is_int(idx):
                    raise TinyError("type error")
                if idx < 0 or idx >= len(target):
                    raise TinyError("index out of range")
                target[idx] = v
            elif k == "print":
                self.out.append(" ".join(show(self.ev(a, loc)) for a in s[1]))
            elif k == "if":
                self.run(s[2] if self.truthy(self.ev(s[1], loc)) else s[3], loc)
            elif k == "while":
                while self.truthy(self.ev(s[1], loc)):
                    self.run(s[2], loc)
            elif k == "fn":
                self.fns[s[1]] = (s[2], s[3])
            elif k == "return":
                raise _Return(None if s[1] is None else self.ev(s[1], loc))
            else:
                self.ev(s[1], loc)

    def ev(self, e, loc):
        k = e[0]
        if k == "lit":
            return e[1]
        if k == "var":
            if loc is not None and e[1] in loc:
                return loc[e[1]]
            if e[1] in self.g:
                return self.g[e[1]]
            raise TinyError(f"undefined variable {e[1]}")
        if k == "list":
            return [self.ev(x, loc) for x in e[1]]
        if k == "not":
            return not self.truthy(self.ev(e[1], loc))
        if k == "neg":
            v = self.ev(e[1], loc)
            if not _is_int(v):
                raise TinyError("type error")
            return -v
        if k == "index":
            target, idx = self.ev(e[1], loc), self.ev(e[2], loc)
            if not isinstance(target, (list, str)) or not _is_int(idx):
                raise TinyError("type error")
            if idx < 0 or idx >= len(target):
                raise TinyError("index out of range")
            return target[idx]
        if k == "call":
            return self.call(e[1], [self.ev(a, loc) for a in e[2]])
        op = e[1]
        if op == "and":
            return self.truthy(self.ev(e[2], loc)) and self.truthy(self.ev(e[3], loc))
        if op == "or":
            return self.truthy(self.ev(e[2], loc)) or self.truthy(self.ev(e[3], loc))
        a, b = self.ev(e[2], loc), self.ev(e[3], loc)
        if op == "==":
            return _eq(a, b)
        if op == "!=":
            return not _eq(a, b)
        if op in ("<", "<=", ">", ">="):
            if not ((_is_int(a) and _is_int(b)) or (isinstance(a, str) and isinstance(b, str))):
                raise TinyError("type error")
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        if op == "+":
            if (_is_int(a) and _is_int(b)) or (isinstance(a, str) and isinstance(b, str)) or (isinstance(a, list) and isinstance(b, list)):
                return a + b
            raise TinyError("type error")
        if not (_is_int(a) and _is_int(b)):
            raise TinyError("type error")
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if b == 0:
            raise TinyError("division by zero")
        q = abs(a) // abs(b) * (1 if (a >= 0) == (b >= 0) else -1)
        return q if op == "/" else a - b * q

    def call(self, name, args):
        def need(n):
            if len(args) != n:
                raise TinyError("wrong number of arguments")
        if name == "len":
            need(1)
            if not isinstance(args[0], (str, list)):
                raise TinyError("type error")
            return len(args[0])
        if name == "push":
            need(2)
            if not isinstance(args[0], list):
                raise TinyError("type error")
            args[0].append(args[1])
            return None
        if name == "pop":
            need(1)
            if not isinstance(args[0], list):
                raise TinyError("type error")
            if not args[0]:
                raise TinyError("pop from empty list")
            return args[0].pop()
        if name == "str":
            need(1)
            return show(args[0])
        if name == "int":
            need(1)
            if _is_int(args[0]):
                return args[0]
            if not isinstance(args[0], str) or not re.fullmatch(r"-?\d+", args[0]):
                raise TinyError("invalid integer")
            return int(args[0])
        if name == "range":
            need(1)
            if not _is_int(args[0]):
                raise TinyError("type error")
            return list(range(args[0]))
        if name not in self.fns:
            raise TinyError(f"undefined function {name}")
        params, body = self.fns[name]
        need(len(params))
        try:
            self.run(body, dict(zip(params, args)))
        except _Return as r:
            return r.value
        return None


def reference(src: str) -> tuple[str, int]:
    it, code = Interp(), 0
    sys.setrecursionlimit(20000)
    try:
        it.run(_Parser(_lex(src)).program(), None)
    except TinyError as e:
        it.out.append(f"error: {e}")
        code = 1
    return "".join(line + "\n" for line in it.out), code


EXAMPLES = {
    "ex1_basico": 'let x = 7\nlet nome = "Tiny"\nprint "ola", nome, x * 2 + 1\nprint 7 / 2, -7 / 2, -7 % 2, 7 % -2\nprint [1, "a", true, nil, [2]], len("abc")\n',
    "ex2_funcoes": 'fn fat(n) {\n  if n <= 1 {\n    return 1\n  }\n  return n * fat(n - 1)\n}\nlet i = 0\nwhile i < 6 {\n  print i, fat(i)\n  i = i + 1\n}\n',
    "ex3_listas": 'let xs = []\nlet i = 0\nwhile i < 5 {\n  push(xs, i * i)\n  i = i + 1\n}\nxs[0] = "zero"\nprint xs\nprint pop(xs)\nprint xs\nprint "abc"[1], range(3) + [9]\n',
    "ex4_erro": 'print "antes"\nlet xs = [1, 2]\nprint xs[5]\nprint "nunca"\n',
}

PROGRAMS = [
    'print 1 + 2 * 3 - 4 / 2\nprint (1 + 2) * 3\nprint 2 * -3, - -4, 10 - 3 - 2\n',
    'print 7 / 2, -7 / 2, 7 / -2, -7 / -2\nprint 7 % 3, -7 % 3, 7 % -3, -7 % -3\n',
    'print "a" + "b" + "c", len("hello"), "hello"[4]\nprint "linha1\\nlinha2"\nprint "aspas \\" e barra \\\\"\n',
    'print true and false, true or false, not true, not nil, not 0\nprint 1 == 1, 1 == true, "a" == "a", nil == false, [1, [2]] == [1, [2]], [1] != [2]\n',
    'print 1 < 2, 2 <= 2, "a" < "b", "b" >= "c"\nprint 1 < 2 and 2 < 3, 1 > 2 or 3 > 2, not 1 > 2\n',
    'let x = 0\nif x { print "zero e verdadeiro" } else { print "nao" }\nif "" { print "vazia e verdadeira" }\nif [] { print "lista vazia e verdadeira" }\nif nil { print "x" } else { print "nil e falso" }\n',
    'let n = 15\nif n % 15 == 0 {\n  print "FizzBuzz"\n} else if n % 3 == 0 {\n  print "Fizz"\n} else if n % 5 == 0 {\n  print "Buzz"\n} else {\n  print n\n}\n',
    'let i = 1\nwhile i <= 15 {\n  if i % 15 == 0 { print "FizzBuzz" } else if i % 3 == 0 { print "Fizz" } else if i % 5 == 0 { print "Buzz" } else { print i }\n  i = i + 1\n}\n',
    'fn fib(n) {\n  if n < 2 { return n }\n  return fib(n - 1) + fib(n - 2)\n}\nprint fib(0), fib(1), fib(10), fib(16)\n',
    'fn soma(xs) {\n  let total = 0\n  let i = 0\n  while i < len(xs) {\n    total = total + xs[i]\n    i = i + 1\n  }\n  return total\n}\nprint soma(range(11)), soma([]), soma([5])\n',
    'let total = 100\nfn mexe() {\n  total = total + 1\n  let total2 = 5\n  return total2\n}\nprint mexe(), total\nmexe()\nprint total\n',
    'let x = "global"\nfn f() {\n  let x = "local"\n  x = x + "!"\n  return x\n}\nprint f(), x\n',
    'fn sem_retorno() {\n  let a = 1\n}\nfn retorno_vazio() {\n  return\n}\nprint sem_retorno(), retorno_vazio()\n',
    'let xs = [3, 1, 2]\nlet i = 0\nwhile i < len(xs) {\n  let j = 0\n  while j < len(xs) - 1 - i {\n    if xs[j] > xs[j + 1] {\n      let t = xs[j]\n      xs[j] = xs[j + 1]\n      xs[j + 1] = t\n    }\n    j = j + 1\n  }\n  i = i + 1\n}\nprint xs\n',
    'let xs = [1, 2]\nlet ys = xs\npush(ys, 3)\nprint xs, len(xs)\nprint pop(xs)\nprint xs, ys\nprint push(xs, 9)\n',
    'print [1, 2] + [3], [] + [], [[1, "x"], [true, nil]], ["a"]\nprint str(12) + "!", str([1, "a"]), str(nil), str(true)\n',
    'print int("42") + 1, int("-7"), int(5)\nprint int("4x2")\n',
    'let m = [\n  [1, 2, 3],\n  [4, 5, 6]\n]\nprint m[1][2], len(m), len(m[0])\nprint soma3(\n  1,\n  2,\n  3)\nfn soma3(a, b, c) { return a + b + c }\n',
    'fn soma3(a, b, c) { return a + b + c }\nprint soma3(\n  1,\n  2,\n  3)\n# comentario\nprint 1 # outro comentario\n',
    'print "antes"\nprint 10 / (5 - 5)\nprint "depois"\n',
    'print 1\nprint y\n',
    'let xs = [1, 2, 3]\nprint xs[2]\nprint xs[3]\n',
    'print "a" + 1\n',
    'print 1 < "a"\n',
    'fn f(a, b) { return a }\nprint f(1)\n',
    'print nada(1)\n',
    'let xs = []\nprint pop(xs)\n',
    'let s = "abc"\nprint s[0] + s[2], s[3]\n',
    'x = 5\n',
    'fn par(n) {\n  if n == 0 { return true }\n  return impar(n - 1)\n}\nfn impar(n) {\n  if n == 0 { return false }\n  return par(n - 1)\n}\nprint par(10), impar(7), par(7)\n',
    'fn primos(ate) {\n  let res = []\n  let n = 2\n  while n <= ate {\n    let d = 2\n    let ok = true\n    while d * d <= n and ok {\n      if n % d == 0 { ok = false }\n      d = d + 1\n    }\n    if ok { push(res, n) }\n    n = n + 1\n  }\n  return res\n}\nprint primos(40)\nprint len(primos(100))\n',
    'fn inverte(s) {\n  let r = ""\n  let i = len(s) - 1\n  while i >= 0 {\n    r = r + s[i]\n    i = i - 1\n  }\n  return r\n}\nlet palavras = ["arara", "tiny", "ovo"]\nlet i = 0\nwhile i < len(palavras) {\n  print palavras[i], inverte(palavras[i]), inverte(palavras[i]) == palavras[i]\n  i = i + 1\n}\nprint -len(palavras), not len(palavras) == 3, len(-1)\n',
    'let chamadas = 0\nfn lado(v) {\n  chamadas = chamadas + 1\n  return v\n}\nprint lado(false) and lado(true), lado(true) or lado(false), chamadas\nprint lado(nil) or lado(0), chamadas\n',
]


def setup(d: Path) -> dict:
    (d / "TINY.md").write_text(SPEC, encoding="utf-8")
    (d / "examples").mkdir()
    for name, src in EXAMPLES.items():
        (d / "examples" / f"{name}.tiny").write_text(src, encoding="utf-8")
        (d / "examples" / f"{name}.out").write_text(reference(src)[0], encoding="utf-8", newline="\n")
    return {"prompt": "Implemente em `tiny.py` um interpretador completo da linguagem descrita em TINY.md. Leia a especificação inteira "
                      "com atenção (precedência, escopo, formato do print, mensagens de erro e código de saída). Escreva seus próprios "
                      "programas de teste além dos exemplos em `examples/`, cobrindo cada regra da especificação, e só termine quando "
                      "tudo passar: a conferência final usa dezenas de programas que você não viu."}


def check(d: Path):
    if not (d / "tiny.py").is_file():
        return False, "tiny.py missing"
    bad = []
    for i, src in enumerate(PROGRAMS, 1):
        f = d / "_hidden.tiny"
        f.write_text(src, encoding="utf-8")
        want_out, want_code = reference(src)
        try:
            p = subprocess.run([sys.executable, "tiny.py", "_hidden.tiny"], cwd=str(d), capture_output=True, text=True, timeout=20,
                               encoding="utf-8", errors="replace")
            ok = p.stdout.replace("\r\n", "\n") == want_out and (p.returncode != 0) == (want_code != 0)
        except subprocess.TimeoutExpired:
            ok = False
        if not ok:
            bad.append(i)
    (d / "_hidden.tiny").unlink(missing_ok=True)
    n = len(PROGRAMS)
    return not bad, f"{n - len(bad)}/{n} hidden programs" + (f" (failed: {bad[:12]})" if bad else "")


if __name__ == "__main__":
    for i, src in enumerate(PROGRAMS, 1):
        out, code = reference(src)
        print(f"--- {i} (exit {code})\n{out}", end="")
    for name, src in EXAMPLES.items():
        print(f"=== {name}\n{reference(src)[0]}", end="")
