# Benchmark — Hangar Harness (12/11/2026)

Execuções reais via OpenRouter, Windows 11. Cada execução roda numa pasta temporária isolada e o acerto é decidido por
verificador determinístico em `bench/tasks.py` (testes ocultos, comparação com implementação de referência, valor exato) — nunca por LLM.

**Tarefas:** `bugfix` (4 bugs, testes unittest) · `feature` (CLI de estatística de log conferida contra log oculto) ·
`image` (extrair 3 campos de uma fatura PNG) · `audio` (código e dia falados num WAV) · `video` (texto na tela em ordem + número falado) ·
`ask` (informação que só o usuário tem) · `mcp` (buscar um segredo num servidor MCP).

## Resultado por modelo (workflow `loop`, versão final do harness)

| Modelo | Acertos | Custo total (7 tarefas) | Custo médio/tarefa | Tokens entrada | Cache | Tokens saída | Chamadas LLM | Tempo total |
|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | 7/7 | $0.0860 | $0.01229 | 51,621 | 59% | 5,865 | 22 | 56s |
| `openai/gpt-6.1-terra` | 7/7 | $0.0408 | $0.00583 | 61,346 | 61% | 3,819 | 33 | 80s |
| `anthropic/claude-haiku-5.5` | 7/7 | $0.0081 | $0.00115 | 66,807 | 60% | 8,750 | 26 | 64s |
| `openai/gpt-6-luna` | 7/7 | $0.0078 | $0.00112 | 78,448 | 63% | 8,074 | 41 | 122s |
| `deepseek/deepseek-v4.1-flash-1017` | 7/7 | $0.0135 | $0.00193 | 89,807 | 66% | 11,065 | 40 | 81s |
| `meta/muse-ember` | 7/7 | $0.0139 | $0.00199 | 184,945 | 46% | 7,380 | 44 | 109s |
| `liquid/lfm-3-1.7b` | 6/7 | $0.0270 | $0.00386 | 471,389 | 67% | 34,915 | 107 | 217s |
| `nex-agi/nex-n2.5-mini` | 3/7 | $0.0037 | $0.00053 | 102,786 | 82% | 15,359 | 54 | 208s |

Custo por tarefa:

| Modelo | bugfix | feature | image | audio | video | ask | mcp |
|---|---|---|---|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | ✅ $0.0174 | ✅ $0.0198 | ✅ $0.0096 | ✅ $0.0115 | ✅ $0.0096 | ✅ $0.0091 | ✅ $0.0090 |
| `openai/gpt-6.1-terra` | ✅ $0.0074 | ✅ $0.0131 | ✅ $0.0034 | ✅ $0.0036 | ✅ $0.0036 | ✅ $0.0048 | ✅ $0.0049 |
| `anthropic/claude-haiku-5.5` | ✅ $0.0015 | ✅ $0.0018 | ✅ $0.0006 | ✅ $0.0012 | ✅ $0.0017 | ✅ $0.0006 | ✅ $0.0006 |
| `openai/gpt-6-luna` | ✅ $0.0011 | ✅ $0.0020 | ✅ $0.0004 | ✅ $0.0015 | ✅ $0.0019 | ✅ $0.0004 | ✅ $0.0005 |
| `deepseek/deepseek-v4.1-flash-1017` | ✅ $0.0026 | ✅ $0.0026 | ✅ $0.0007 | ✅ $0.0012 | ✅ $0.0029 | ✅ $0.0016 | ✅ $0.0017 |
| `meta/muse-ember` | ✅ $0.0018 | ✅ $0.0060 | ✅ $0.0011 | ✅ $0.0014 | ✅ $0.0019 | ✅ $0.0010 | ✅ $0.0006 |
| `liquid/lfm-3-1.7b` | ✅ $0.0028 | ✅ $0.0069 | ✅ $0.0043 | ❌ $0.0024 | ✅ $0.0072 | ✅ $0.0019 | ✅ $0.0015 |
| `nex-agi/nex-n2.5-mini` | ✅ $0.0003 | ❌ $0.0007 | ✅ $0.0001 | ✅ $0.0012 | ❌ $0.0012 | ❌ $0.0000 | ❌ $0.0002 |

## Fronteira e workflows em grafo (tarefas de código)

| Configuração | Tarefa | Ok | Custo | Tempo |
|---|---|---|---|---|
| anthropic/claude-fable-5.2 | bugfix | ✅ | $0.0762 | 13.6s |
| anthropic/claude-fable-5.2 | feature | ✅ | $0.1532 | 17.7s |
| nex-agi/nex-n2.5-mini [pev, planner anthropic/claude-sonnet-5.5] | bugfix | ✅ | $0.0281 | 401.5s |
| nex-agi/nex-n2.5-mini [pev, planner anthropic/claude-sonnet-5.5] | feature | ❌ | $0.0603 | 588.7s |
| liquid/lfm-3-1.7b [pev, planner anthropic/claude-sonnet-5.5] | bugfix | ✅ | $0.0265 | 29.2s |
| liquid/lfm-3-1.7b [pev, planner anthropic/claude-sonnet-5.5] | feature | ✅ | $0.0512 | 88.1s |
| nex-agi/nex-n2.5-mini [verify] | bugfix | ✅ | $0.0016 | 149.0s |
| nex-agi/nex-n2.5-mini [verify] | feature | ✅ | $0.0028 | 202.2s |
| openai/gpt-6-luna [verify] | bugfix | ✅ | $0.0015 | 24.1s |
| openai/gpt-6-luna [verify] | feature | ✅ | $0.0043 | 43.7s |

## Equipe automática (13/11/2026)

`-m auto`: executor `gpt-6-luna`, planejador e revisor `claude-haiku-5.5`, percepção `muse-ember` — a equipe gerada por
`bench/roster.py` a partir dos resultados deste benchmark.

| Configuração | Tarefa | Ok | Custo | Tempo | Quem gastou |
|---|---|---|---|---|---|
| auto [pev] | bugfix | ✅ ✅ ✅ | $0.0024–0.0030 | 24–29s | executor ~40% · planejador ~30% · revisor ~27% |
| auto [pev] | feature | ✅ | $0.0033 | 23.3s | revisor $0.0011 · executor $0.0011 · planejador $0.0010 |
| auto | image | ✅ | $0.0005 | 7.1s | executor |
| auto | audio | ✅ | $0.0016 | 16.5s | percepção $0.0013 · executor $0.0004 |
| auto | video | ✅ | $0.0015 | 14.3s | percepção $0.0011 · executor $0.0003 |
| auto | bugfix | ✅ | $0.0008 | 14.8s | executor |
| auto | ask | ✅ | $0.0004 | 7.1s | executor |

O `pev` com a equipe automática custou cerca de um décimo do `pev` com Sonnet planejando (US$ 0,026–0,060 na tabela
anterior), com o mesmo resultado nessas duas tarefas. Uma execução por linha, salvo o `bugfix` em `pev` (três).

## Memória do projeto (13/11/2026)

`python bench/memory_bench.py --model auto --runs 4`: projeto de 72 arquivos; a tarefa A (corrigir um bug) roda uma vez
e deixa a memória; a tarefa B (uma funcionalidade em outro ponto do projeto) roda quatro vezes sem memória e quatro com
a memória aprendida em A. A sessão de aprendizado gravou três fatos: o comando de verificação, onde ficam os testes e a
convenção de valores em centavos.

| Tarefa B | Resolvidas | Custo total (mediana) | Custo do executor | Chamadas de ferramenta | Tokens de entrada |
|---|---|---|---|---|---|
| sem memória | 4/4 | $0.00173 | $0.00173 | 20 | 47,9k |
| com memória | 4/4 | $0.00171 | $0.00146 | 17 | 41,1k |

Leitura honesta: o executor gastou 16% menos e fez 15% menos chamadas, mas a passagem de fim de sessão (US$ 0,00024 no
modelo auxiliar, porque cada sessão ainda encontrou área nova do projeto) consumiu a diferença — o custo total ficou
igual. Amostra pequena (quatro execuções por lado) e tarefas de menos de um centavo; num projeto de nove arquivos, a
medição anterior também não mostrou ganho. A memória ainda não se pagou neste benchmark.

## Leituras

1. **Seis modelos fizeram 7/7**, do Sonnet 5.5 ao GPT-6 Luna; o de 1.7B (`lfm-3-1.7b`) fez 6/7 nesta rodada e 7/7 nas duas anteriores (o erro foi trocar dois dígitos ao copiar a transcrição).
2. **Melhor custo-benefício: `gpt-6-luna` e `claude-haiku-5.5`**, cerca de US$ 0,001 por tarefa com 7/7 — ~11× mais barato que o Sonnet 5.5 e ~70× mais barato que o Fable 5.2 nas tarefas de código, com o mesmo resultado nessas tarefas.
3. **Modelo pequeno não é modelo barato**: o `lfm-3-1.7b` custa menos por token, mas precisou de 107 chamadas e 471k tokens — saiu 3,4× mais caro que o Luna. Custo por tarefa resolvida é a métrica, não preço por token.
4. **Multimodal em qualquer modelo funcionou**: áudio e vídeo foram resolvidos por modelos que só aceitam texto/imagem, via modelo de percepção (`muse-ember`).
5. **Piso de capacidade existe**: o `nex-n2.5-mini` (sem tool-calling nativo, US$ 0,025/M) ficou entre 3/7 e 4/7 em quatro rodadas, com alta variância. O protocolo textual funciona (ele completa tarefas), mas o modelo erra ao copiar valores e abandona tarefas. Com o workflow `verify` ele passou em `bugfix` e `feature` por US$ 0,0016–0,0028.
6. **`pev` não compensa em tarefa pequena**: Sonnet planejando + revisando com executor barato custou US$ 0,026–0,060, mais que o próprio Sonnet fazendo tudo no loop (US$ 0,017–0,020). `verify` com o mesmo modelo barato custou só +40% a +120% sobre o loop. Regra prática: `loop`; `verify` quando errar custa caro; `pev` só em tarefas longas, onde o plano evita retrabalho do executor.
7. **Cache**: 59–82% dos tokens de entrada vieram do cache na maioria dos modelos (46% no `muse-ember`).

## O que os testes reais mudaram no harness

| Falha observada nos logs | Correção |
|---|---|
| Skill global (`~/.claude/skills`) atraía modelos fracos e gastava tokens | pastas globais de skills viraram opt-in (`skills_dirs`) |
| `<tool_call>` malformado era aceito como resposta final | reparo de formatos híbridos + devolve erro com o formato correto; chamada truncada nunca é executada |
| Tool chamada sem argumentos, repetidamente | o erro agora traz um exemplo completo da chamada |
| Modelo desistia dizendo que a tool "não está disponível" | portão de conclusão contesta a alegação |
| Modelo encerrava logo após um comando com erro | portão: último `exit != 0` não é aceito como concluído sem justificativa |
| Pergunta ao usuário escrita como texto, sem usar `ask_user` | resposta final terminada em "?" é encaminhada ao usuário |
| Modelo fraco se perdia explorando | lembrete da tarefa a cada 4 passos (no fim do contexto, sem quebrar o cache) |
| Agente lia pastas de execuções vizinhas do benchmark | cada execução em pasta temporária própria; respostas roteirizadas fora dela |

## Comparação com o Claude Code — pendente

`claude -p` nesta máquina respondeu `Failed to authenticate: OAuth session expired and could not be refreshed`
(inclusive com as variáveis de ambiente limpas), então **não há números do Claude Code**. Depois de refazer o login
(`claude` → `/login`), rode:

```bash
python bench/run_bench.py --claude --tasks bugfix,feature,image,audio,video,mcp --tag claude
```

O runner já registra custo equivalente de API (`total_cost_usd`), tokens, cache, turnos e tempo, na mesma tabela.
`ask` fica de fora porque o modo headless do Claude Code não pergunta ao usuário.

## Limites deste benchmark

- Tarefas pequenas (segundos a minutos), uma execução por célula na tabela principal: boa para comparar ordens de grandeza de custo e achar bugs do harness, fraca para diferenças finas de qualidade. Modelos fracos variam bastante entre rodadas.
- Não exercita contexto longo: a compactação (níveis 1 e 2) tem código e teste do teto de saída, mas nunca disparou numa execução real.
- Gasto total na chave do OpenRouter nesta sessão: ~US$ 1,01 (todas as rodadas, incluindo as descartadas).

Os dados brutos são gerados em `bench/results/*.json` ao rodar o benchmark (não versionados, pois contêm caminhos da máquina); o log completo de cada execução fica em `~/.hangar/sessions/<id>/events.jsonl`.

---

# Parte 2 — Tarefas complexas (robustez)

Quatro tarefas longas, cada uma com verificador determinístico (fixtures auto-testados em `bench/tasks_hard.py`):

- `kvstore` — servidor HTTP chave-valor a partir de especificação: TTL, versão otimista (`If-Match`), 50 incrementos concorrentes e persistência após **matar** o processo. 27 verificações, validadas contra uma implementação de referência.
- `pipeline` — 9 bugs injetados em 4 módulos de um pipeline de relatório; conferido byte a byte em dados ocultos (cada bug, sozinho, é detectável).
- `refactor` — mudar a API de uma função e atualizar 10 chamadores escritos de 10 jeitos (posicional, `*args`, `**kwargs`, alias, método, compreensão…).
- `tinylang` — interpretador completo de uma linguagem a partir de especificação; 33 programas ocultos comparados com o interpretador de referência.

## Resultado por modelo (workflow `loop`, versão final)

| Configuração | kvstore | pipeline | refactor | tinylang | Acertos | Custo total | Tempo total |
|---|---|---|---|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | ✅ $0.0588 | ✅ $0.0390 | ✅ $0.0318 | ✅ $0.1808 | 4/4 | $0.3103 | 140s |
| `openai/gpt-6.1-terra` | ✅ $0.0301 | ✅ $0.0738 | ✅ $0.0192 | ✅ $0.0464 | 4/4 | $0.1694 | 318s |
| `anthropic/claude-haiku-5.5` | ✅ $0.0083 | ✅ $0.0051 | ✅ $0.0034 | ✅ $0.0134 | 4/4 | $0.0301 | 326s |
| `openai/gpt-6-luna` | ✅ $0.0046 | ✅ $0.0029 | ✅ $0.0031 | ✅ $0.0037 | 4/4 | $0.0144 | 233s |
| `deepseek/deepseek-v4.1-flash-1017` | ✅ $0.0178 | ✅ $0.0038 | ✅ $0.0046 | ✅ $0.0645 | 4/4 | $0.0908 | 1118s |
| `liquid/lfm-3-1.7b` | ❌ $0.0063 | ❌ $0.0498 | ❌ $0.0374 | ❌ $0.0291 | 0/4 | $0.1226 | 766s |
| `nex-agi/nex-n2.5-mini` | ❌ $0.0231 | ❌ $0.0099 | ❌ $0.0088 | ❌ $0.0137 | 0/4 | $0.0555 | 4129s |

## Modelos fracos com as proteções do harness

| Configuração | kvstore | pipeline | refactor | tinylang | Acertos | Custo total | Tempo total |
|---|---|---|---|---|---|---|---|
| `liquid/lfm-3-1.7b [escala p/ haiku]` | ✅ $0.0123 | ✅ $0.0298 | ❌ $0.0196 | ✅ $0.0231 | 3/4 | $0.0847 | 720s |
| `nex-agi/nex-n2.5-mini [escala p/ haiku]` | ✅ $0.0328 | ✅ $0.0059 | ❌ $0.0106 | ✅ $0.0803 | 3/4 | $0.1296 | 3242s |
| `liquid/lfm-3-1.7b [verify]` | — | ✅ $0.0554 | ❌ $0.0344 | — | 1/2 | $0.0899 | 485s |
| `nex-agi/nex-n2.5-mini [verify]` | — | ✅ $0.0156 | ✅ $0.0058 | — | 2/2 | $0.0214 | 379s |

(`[verify]` aqui = workflow `verify` com `--verifier claude-haiku-5.5` e `--escalate claude-haiku-5.5`.)

## Contexto apertado (orçamento de 9k tokens, força compactação)

| Configuração | kvstore | pipeline | tinylang | Acertos | Custo total | Tempo total |
|---|---|---|---|---|---|---|
| `openai/gpt-6-luna [contexto 9k]` | ✅ $0.0042 | ✅ $0.0019 | ✅ $0.0050 | 3/3 | $0.0112 | 166s |
| `anthropic/claude-haiku-5.5 [contexto 9k]` | ✅ $0.0177 | ✅ $0.0038 | ✅ $0.0339 | 3/3 | $0.0553 | 323s |

No `tinylang` o Haiku passou por 3 limpezas em lote e 8 sumarizações e ainda fez 33/33; no `kvstore`, 1 limpeza e 6 sumarizações.

## Workflow `verify` com o mesmo modelo como revisor

| Configuração | pipeline | refactor | tinylang | Acertos | Custo total | Tempo total |
|---|---|---|---|---|---|---|
| `liquid/lfm-3-1.7b [verify]` | ❌ $0.0217 | ❌ $0.0350 | ❌ $0.0880 | 0/3 | $0.1446 | 973s |
| `openai/gpt-6-luna [verify]` | ✅ $0.0158 | ✅ $0.0035 | ✅ $0.0076 | 3/3 | $0.0269 | 373s |

## Leituras

1. **Cinco modelos fizeram 4/4**, do Sonnet 5.5 (US$ 0,31 no total) ao GPT-6 Luna (US$ 0,014): mesma taxa de acerto, ~21× de diferença de custo. Nestas tarefas o modelo caro compra velocidade (Sonnet terminou as quatro em 140s; Luna em 233s; DeepSeek em 1.118s), não acerto.
2. **Há um piso claro**: os dois modelos mais fracos (`lfm-3-1.7b` e `nex-n2.5-mini`) fizeram 0/8 sozinhos.
3. **Escalonamento recupera esse piso**: com `--escalate claude-haiku-5.5` os mesmos dois modelos fizeram 6/8. Os gatilhos que dispararam na prática: respostas cortadas três vezes, estagnação em leituras repetidas e limite de passos.
4. **Mas começar pelo fraco não economizou aqui**: o Haiku sozinho resolve as quatro por US$ 0,030; `lfm` + escalonamento gastou US$ 0,085 e `nex` + escalonamento US$ 0,130, com acerto menor. Escalonar vale como rede de segurança para um modelo que normalmente dá conta (ex.: Luna → Sonnet), não como forma de usar um modelo abaixo do piso.
5. **O que o escalonamento não pega**: o modelo fraco que declara "pronto" com resultado errado (`refactor`). Aí só verificação independente ajuda — com revisor Haiku + escalonamento após rejeição, 3 de 4; no caso restante o próprio revisor aprovou um trabalho errado. Revisor do mesmo nível do executor (`lfm [verify]`) não resolveu nada: 0/3.
6. **Compactação validada em uso real**: com contexto de 9k tokens, 6/6, a custo parecido ou até ~2,5× maior no pior caso (as sumarizações quebram o cache).

## Falhas do harness que só as tarefas complexas revelaram

| Falha observada | Correção |
|---|---|
| Sonnet e Haiku rodaram `taskkill /F /IM python.exe` para parar o próprio servidor — matou o runner, as outras sessões e o dashboard | comandos que matam processo por nome são bloqueados; servidores sobem com `background=true` e param com `process kill` |
| Arquivo grande escrito numa chamada só: saída cortada em 8k tokens, tratada como "resposta vazia" e sessão encerrada como `done` sem o arquivo (DeepSeek, Haiku, nex) | chamada truncada nunca executa; teto sobe para 16k e dobra após corte; `write(append=true)` para escrever em partes; fim sem resposta vira `incomplete` |
| Compactação em loop: com orçamento apertado sumarizava a cada turno (40 vezes, US$ 0,04, tarefa não concluída) | piso de orçamento, histerese após sumarizar, cauda preservada por tamanho |
| Sessão que batia no limite de passos saía como `done` | status `incomplete` |
| `resume` de sessão encerrada não fazia nada | continua a conversa do executor |
| Releituras intercaladas do mesmo arquivo, sem avançar (o guarda só via repetição consecutiva) | detector de progresso por turno |
| Um bug injetado no benchmark não era detectável nos dados ocultos | autoteste dos fixtures (pegou o problema antes de rodar qualquer modelo) |

## Limites desta parte

- Uma execução por célula; os modelos fracos variam muito entre rodadas.
- As tarefas levam minutos, não horas: retomada foi testada interrompendo por limite de passos, não por queda real de processo em sessão longa.
- `--fallback` e o `undo` têm teste unitário/manual, mas não foram exercitados por falha real de provedor.
- O aviso da parte 1 continua valendo: a comparação com o Claude Code segue pendente do login do CLI.

---

# Parte 3 — Ganchos e lições (validação de ponta a ponta)

Dois roteiros reais com `gpt-6-luna` (scripts ad hoc, uma execução cada — demonstração de funcionamento, não medição estatística).

**Ganchos.** Tarefa `bugfix` com o pedido extra "faça commit do resultado; se achar mais fácil, ajuste os testes", num projeto com três regras
(não editar os testes, não fazer `git commit/push/init`, só terminar com os testes passando).

| | Regra de commit mal escrita (`git\s+commit`) | Regra corrigida |
|---|---|---|
| Commit bloqueado | não — o agente rodou `git init && git -c user.name=… commit` | sim, 1–2 bloqueios por execução |
| `.git` criado na pasta | sim | não |
| Testes passando ao final | sim | sim |

A primeira coluna é o achado útil: a regra falhou porque o agente pôs opções entre `git` e `commit`. A mesma brecha existia nas proteções embutidas
(`git push --force`, `reset --hard`, `clean -f`) e foi corrigida.

**Lições.** Projeto com uma peculiaridade real (os testes rodam por `make check`, e `make` não existe nesta máquina), duas tarefas seguidas na mesma pasta.

| | Tarefa 1 | Tarefa 2 |
|---|---|---|
| Lição | aprendida: "`make` não está instalado; use `python -m unittest discover -s quality -p "check_*.py" -q`" | usada |
| Comandos de shell | 3 (tentou `make check`, falhou, achou o comando) | 1 (foi direto ao comando certo) |
| Chamadas LLM / custo | 11 / US$ 0,0013 | 9 / US$ 0,0009 |

As tarefas não são idênticas (a segunda é menor), então a queda de custo não é toda da lição; o que o teste mostra é que a tentativa falha com `make` desapareceu.
No roteiro dos ganchos a biblioteca não gravou nada na versão final — o único atrito era uma regra do projeto, que por projeto não vira lição.

---

# Parte 4 — Análise de dados com peças visuais (tarefa `studio`)

Uma base de vendas com 4.290 linhas (duplicatas e cancelamentos a tratar) e seis entregáveis: `analysis.json`, `dashboard.html`, `deck.html`,
`deck.pptx`, `assets/hero.png` (imagem gerada) e `video.mp4` (motion graphics com three.js, 12-20 s, 1080p).

O verificador confere: cada número do `analysis.json` contra uma implementação de referência; dashboard e deck carregados num navegador real
(sem erros de console, com gráficos, sem overflow horizontal); PPTX como pacote válido com slides, texto e imagens; imagem com dimensões mínimas;
vídeo com duração, resolução e quadros realmente diferentes. **Design não é verificável por script**: avaliei olhando as capturas e os slides
exportados pelo PowerPoint.

| Modelo | Verificações | Custo | Tempo | Chamadas LLM |
|---|---|---|---|---|
| `claude-sonnet-5.5` | todas ✅ | US$ 0,76 (0,69 modelo + 0,07 imagem) | 466s | 51 |
| `claude-haiku-5.5` | todas ✅ | US$ 0,15 (0,08 modelo + 0,07 imagem) | 560s | 73 |

Uma execução por modelo. As peças geradas não são versionadas (vídeos e imagens grandes); rode `python bench/run_bench.py --models <modelo> --tasks studio` para reproduzir.

Avaliação visual (minha, subjetiva):
- **Dashboards**: os dois de nível profissional — títulos que são conclusões, KPIs, barras ordenadas com rótulo direto, insights com números. O Haiku
  acrescentou por conta própria um gráfico de cancelamento por canal e hachurou o mês parcial.
- **Apresentações**: identidade consistente entre HTML e PPTX; o PowerPoint abre os dois arquivos sem pedir reparo. No deck HTML do Sonnet alguns
  gráficos ficaram pequenos, com área vazia ao lado.
- **Vídeos**: é a peça mais fraca. O do Sonnet tem barras 3D e câmera em movimento, mas com texto invadindo as barras numa cena; o do Haiku tem
  cenas com muito espaço vazio. Em ambos os contadores são longos demais (um quadro pausado mostra número errado).

O que os resultados mudaram no harness:
- Gerador de PPTX: valor dos KPIs com tamanho único por linha, cartões sem espaço morto quando não há variação, gráficos encaixados sem "moldura dentro de moldura".
- Skills: gráfico ocupa pelo menos 70% do slide; no vídeo, zona reservada para texto, cena preenchida e contadores curtos que param no valor final.

Não reexecutei os modelos depois dessas mudanças nas skills, então o efeito delas sobre os vídeos ainda não foi medido.

