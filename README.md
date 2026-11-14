# ▲ Hangar Harness

Harness de agentes agnóstico de modelo, econômico em tokens e observável em tempo real.
Python puro (só biblioteca padrão — nada para instalar). Testado em Windows 11; escrito para rodar também em Linux e macOS (ainda não testado lá).

```bash
python -m hangar doctor                                   # sonda a máquina e a configuração
python -m hangar run "corrija os testes que estão falhando" --cwd ./meu-projeto
python -m hangar run "o que diz este áudio?" -a reuniao.mp3 -m liquid/lfm-3-1.7b
python -m hangar run "implemente X" -w pev --planner anthropic/claude-sonnet-5.5 -m openai/gpt-6-luna
python -m hangar run "tarefa longa" -m openai/gpt-6-luna --escalate anthropic/claude-sonnet-5.5   # barato primeiro, forte se travar
python -m hangar resume last                              # retoma a última sessão de onde parou
python -m hangar resume <id> "agora adicione testes"      # nova instrução numa sessão encerrada
python -m hangar undo <id>                                # restaura os arquivos que a sessão alterou
python -m hangar chat                                     # sessão interativa multi-turno
python -m hangar ui                                       # dashboard ao vivo em http://127.0.0.1:3090
```

A chave fica em `.env` (`OPENROUTER_API_KEY=...`) na pasta do projeto, na pasta do harness ou em `~/.hangar/.env`.
Há um modelo em `.env.example`. Opcional: `pip install -e .` instala o comando `hangar` (o pacote não tem dependências).
De qualquer pasta: `python caminho/para/hh.py run "..."`.

## O que ele faz

| Requisito | Como o Hangar resolve |
|---|---|
| Funciona com qualquer modelo | Tool-calling nativo **ou** protocolo textual (`<tool_call>`), escolhido pelo catálogo e trocado sozinho se o provedor recusar tools. Reparo de JSON (truncado, duplamente codificado, aspas simples), aliases de nomes de tools e de argumentos, coerção de tipos, erros que ensinam o uso correto. Modelos fracos recebem catálogo de tools menor e um passo por vez. |
| Entrada de texto, imagem, áudio, vídeo, PDF | `-a arquivo`. Anexo vai nativo quando o modelo aceita a modalidade; senão um modelo de percepção barato converte em texto; se nenhum aceita vídeo, o ffmpeg decompõe em quadros + trilha de áudio. A tool `perceive` permite perguntas de acompanhamento. |
| Explora a máquina | `machine.py` sonda núcleos, RAM, GPU e CLIs instaladas e informa o agente; tools de leitura rodam em paralelo; shell com timeout e kill da árvore de processos; modelos locais via `ollama:modelo` / `lmstudio:modelo`. |
| Logs de tudo | `~/.hangar/sessions/<id>/events.jsonl` (cada chamada de LLM, tool, pergunta, compactação, veredito), `summary.json`, `meta.json`, saídas longas em `spill/`, transcrições em `history_*.json`. |
| Visual em tempo real | `hangar ui`: sessões, streaming de texto/raciocínio, tools com argumentos e resultado, plano, custo/tokens/cache ao vivo, botão Parar. Aba **Grafo ao vivo**: o workflow é desenhado nó a nó enquanto acontece — uma raia por agente (etapa do workflow ou sub-agente), uma linha por turno do modelo, chamadas paralelas lado a lado, arestas de delegação, de revisão (aprova/rejeita) e de retomada, marcadores de escalonamento e compactação; clicar num nó abre o passo na linha do tempo. SVG puro, sem dependências. O servidor só lê os JSONL — mostra execuções de qualquer processo, inclusive as antigas. |
| Conexão fácil com tools | MCP stdio e HTTP lendo o mesmo `.mcp.json` do Claude Code; skills `SKILL.md` (pastas `.hangar/skills`, `.claude/skills`, `~/.claude/skills`); instruções de projeto em `HANGAR.md` / `AGENTS.md` / `CLAUDE.md` / `.claude/CLAUDE.md`; sub-agentes de `.claude/agents`, comandos de barra de `.claude/commands` e, em projetos confiáveis, hooks do Claude Code de `.claude/settings.json`. |
| Pergunta ao usuário | Tool `ask_user` (terminal ou dashboard). Aprovação explícita para comandos destrutivos e escrita fora da pasta de trabalho. |
| Custo baixo por tarefa | Ver abaixo. |

## Robustez em tarefas longas e complexas

| Problema real (visto nos testes) | O que o harness faz |
|---|---|
| Sessão cai, é interrompida ou bate no limite | Cada agente grava a transcrição a cada turno e o grafo grava checkpoint ao entrar e sair de cada nó; `hangar resume` continua do ponto exato, com totais de custo acumulados. Sessão que não terminou sai como `incomplete`, nunca como `done`. |
| Modelo barato trava | `--escalate MODELO`: ao detectar limite de passos, repetição, estagnação, respostas vazias/cortadas, desistência, comando final falhando ou duas rejeições do revisor, um modelo mais forte assume **a mesma conversa**. Paga-se pelo forte só quando precisa. |
| Estagnação sem repetição consecutiva | Detector de progresso: turnos só com chamadas de leitura já feitas contam como parados (aviso em 2, escalonamento em 4, encerramento em 6). |
| Saída cortada no meio de uma chamada | Chamada truncada nunca é executada; o teto de saída dobra (16k → 32k) e o modelo é orientado a escrever em partes (`write` com `append=true`). |
| Servidores e builds longos | `shell` com `background=true` + tool `process` (output / kill / list); tudo é encerrado ao fim da sessão. |
| Agente mata processos da máquina | Comandos que matam por **nome** (`taskkill /IM`, `pkill`, `killall`, `Stop-Process -Name`) são bloqueados: nos testes, modelos fortes rodaram `taskkill /F /IM python.exe` só para parar o próprio servidor. |
| Contexto estoura | Compactação em 3 níveis com piso de orçamento e histerese (sem isso ela entrava em loop sumarizando a cada turno); plano, notas (`note`), arquivos alterados e processos vivos são reinjetados de forma exata após cada sumarização. |
| Alteração indesejada | Backup do original de cada arquivo antes do primeiro `write`/`edit`; `hangar undo <id>` restaura (mudanças feitas via shell não são rastreadas). |
| Provedor fora do ar | `--fallback a,b`: depois das tentativas com backoff, troca para um modelo reserva. |
| Resultado "pronto" mas errado | Workflow `verify` com `--verifier` mais forte: revisor de contexto limpo roda o código e rejeita; na segunda rejeição o executor é escalado. |

## Estúdio: dashboards, apresentações, imagens e vídeo

O agente produz peças visuais com quatro comandos que ele chama pelo `shell`, guiado por cinco skills embutidas
(`data-analysis`, `dashboard`, `presentation`, `image-generation`, `motion-video`) carregadas só quando a tarefa pede.
São comandos, e não tools, de propósito: schema de tool é pago em toda chamada ao modelo; comando só custa quando é usado.

```bash
python -m hangar studio screenshot pagina.html saida.png --width 1440 --height 900 --full   # captura + erros de console, overflow, texto cortado
python -m hangar studio video anim.html saida.mp4 --duration 15 --fps 30                    # HTML/three.js -> MP4, quadro a quadro
python -m hangar studio image "prompt" assets/hero.png --aspect 16:9                        # modelo de imagem via OpenRouter
python -m hangar studio pptx deck.json deck.pptx                                            # PowerPoint nativo, texto editável
```

- **Navegador headless sem dependências** (`browser.py`): fala o protocolo DevTools do Chrome/Edge por um cliente WebSocket de ~60 linhas.
  O agente usa a captura com a tool `perceive` para olhar o que fez e corrigir.
- **Vídeo determinístico**: a página define `window.hangarFrame(t)` e o renderizador posiciona cada quadro no instante exato (animações CSS
  são posicionadas sozinhas), captura e envia ao ffmpeg. Não é gravação de tela: máquina lenta não perde quadro.
- **PPTX sem dependências** (`pptx.py`): escreve o XML do pacote direto; 8 layouts (capa, seção, KPIs, tópicos, imagem, duas colunas, citação,
  encerramento) com tema configurável. Validado abrindo no PowerPoint real.
- **Imagem**: padrão `google/gemini-3.1-flash-image` (cerca de US$ 0,07 por imagem); o gasto entra na conta da sessão.
- Requisitos: Chrome ou Edge para captura/vídeo, ffmpeg para vídeo, chave do OpenRouter para imagem.

## Equipe de modelos: o harness escolhe quem faz o quê

Com `model = "auto"` (o padrão do app web; no CLI, `hangar run -m auto "…"`) o harness monta a equipe sozinho:

| Papel | Modelo | Por quê | Evidência |
|---|---|---|---|
| executor | `openai/gpt-6-luna` | o mais barato que resolveu todas as tarefas do dia a dia, de mídia e difíceis | 50/50 execuções · US$ 0.0015 por tarefa resolvida |
| sub-agente leve (`level: light`) | `openai/gpt-6-luna` | busca, leitura e resumo | 22/22 execuções · US$ 0.0009 por tarefa resolvida |
| sub-agente profundo (`level: deep`) | `anthropic/claude-haiku-5.5` | o mais barato que resolveu a tarefa mais difícil | 31/31 execuções · US$ 0.0234 na tarefa mais difícil |
| planejador (`pev`) | `anthropic/claude-haiku-5.5` | o plano orienta todo o resto | 31/31 execuções · US$ 0.0234 na tarefa mais difícil |
| revisor (`verify`, `pev`) | `anthropic/claude-haiku-5.5` | de outro fornecedor que o executor: não divide os mesmos pontos cegos | 28/28 execuções · US$ 0.0028 por tarefa resolvida |
| reforço | `anthropic/claude-haiku-5.5` | assume a conversa só quando o executor trava | 31/31 execuções · US$ 0.0234 na tarefa mais difícil |
| auxiliar | `openai/gpt-6-luna` | resumo de contexto e lições | 22/22 execuções · US$ 0.0009 por tarefa resolvida |
| percepção | `meta/muse-ember` | imagem, áudio e vídeo | 9/9 execuções · US$ 0.0016 por tarefa resolvida |

A equipe não é escrita à mão: `python bench/roster.py` lê os resultados do benchmark e grava `hangar/roster.json`, que o
roteador usa. Um modelo só entra num papel se resolveu **todas** as execuções das tarefas que o papel exige, com pelo
menos duas execuções por tarefa; dentro do papel, a ordem é o custo por tarefa resolvida.

| Papel | Precisa ter resolvido | Ordenado pelo custo em |
|---|---|---|
| executor | dia a dia + mídia + difíceis | as mesmas |
| leve, auxiliar | dia a dia | dia a dia |
| revisor | dia a dia + difíceis | as mesmas |
| profundo, planejador, reforço | dia a dia + difíceis + a mais difícil (`tinylang`) | a mais difícil |
| percepção | mídia, e aceitar imagem, áudio e vídeo | mídia |

Rodou o benchmark de novo (`python bench/run_bench.py …`)? Rode `python bench/roster.py` e a equipe acompanha os números.
Para usar uma lista só sua, grave em `~/.hangar/roster.json` (`--out`). Se um modelo sair do catálogo, o próximo da fila
assume. Para trocar um papel na mão:

```toml
[team]
worker = "anthropic/claude-haiku-5.5"
deep = ["openai/gpt-6.1-terra", "anthropic/claude-sonnet-5.5"]
```

Com um modelo fixo (`-m openai/gpt-6-luna`) nada é roteado: é a sua escolha para tudo.

### Quem gastou o quê

Toda execução termina com a conta por papel — no CLI, no `summary.json` (`by_role`) e no app web (linha abaixo da
resposta e coluna de gasto no botão "Modelos"):

```text
— done · 41.2s · 9 llm calls · 11 tool calls · 30120 in (18044 cached) / 2210 out · $0.00412
    worker      $0.00231 · 5 calls · gpt-6-luna
    verifier    $0.00102 · 2 calls · claude-haiku-5.5
    deep        $0.00079 · 2 calls · claude-haiku-5.5
```

Os papéis são `worker`, `light`, `deep`, `sub` (sub-agente sem nível), `planner`, `verifier`, `escalation`, `helper`,
`perception` e `studio` (geração de imagem). A soma dos papéis é o custo total da sessão.

## Backlog: trabalho maior que uma sessão

Uma sessão resolve uma tarefa e esquece. Para um objetivo que não cabe numa sessão — um sistema inteiro, uma migração —
o harness mantém um backlog em disco: tarefas com dependências e, em cada uma, **um comando de aceite**.

```bash
hangar backlog plan "Criar um interpretador de calculadora com variáveis, erros claros e CLI" -m auto
hangar backlog                     # o objetivo, as tarefas, o que está pronto, qual é a próxima
hangar backlog run                 # trabalha na próxima tarefa (uma sessão)
hangar backlog run --all --budget 0.50   # segue até não haver mais o que fazer, ou até gastar US$ 0,50
hangar backlog check               # sem modelo: tudo o que foi dado como pronto continua passando?
hangar backlog reset [id]          # devolve as tarefas que falharam (ou uma) para a fila
hangar backlog add "Exportar em CSV" --accept "python -m unittest tests.test_csv" --deps cli
```

Fica em `<projeto>/.hangar/backlog.json`, um arquivo que dá para ler e editar.

- **Quem diz que está pronto é o harness.** Ao fim da sessão ele mesmo roda o comando de aceite da tarefa; a tarefa só
  vira `done` se o comando sair com código 0. A palavra do agente não conta.
- **Nada do que já estava pronto pode quebrar.** Depois do aceite da tarefa, rodam de novo os comandos de aceite de
  todas as tarefas já concluídas. Se um deles falha, a tarefa não é aceita.
- **A falha volta para a mesma sessão**, com a saída do comando, até três conferências. Depois disso a tarefa fica
  `failed`, o que depende dela fica bloqueado, e o harness segue com o que for independente.
- **O aceite roda no ambiente do usuário**, sem as variáveis que o shell do agente recebe (`PYTHONUTF8`,
  `PYTHONIOENCODING`): o que passa só no ambiente do agente não passa aqui.
- **O plano é validado antes de ser gravado**: ids únicos, dependências que existem, sem ciclo, comando de aceite em toda
  tarefa e nenhum comando destrutivo. Duas tarefas com o mesmo comando são recusadas — para a segunda ele já passaria
  antes do trabalho — e o planejador recebe o motivo e corrige uma vez.
- Um aceite que já passa antes de a tarefa começar é marcado como conferência fraca (`weak`) no arquivo.
- `--budget` é o teto de gasto da chamada inteira; cada sessão continua com o próprio `max_cost_usd`.

Com a memória do projeto ligada, o que uma tarefa descobre (como rodar os testes, onde ficam as coisas) já está no
contexto da seguinte.

## Memória do projeto

O agente guarda fatos duráveis do projeto em que trabalha, para a próxima sessão não pagar de novo para descobri-los:
como rodar os testes, onde ficam as coisas, uma convenção do código, uma armadilha.

```text
<projeto>/.hangar/memory/
  MEMORY.md            índice, uma linha por fato
  test-command.md      um arquivo por fato
  tests-layout.md
```

São arquivos de texto: dá para ler, editar, apagar e versionar junto com o projeto. Só o índice entra no contexto de
cada sessão (cerca de uma linha por fato); o detalhe de um fato é lido sob demanda.

O que impede a memória de virar um monte de palpites:

- **Só entra o que o harness consegue conferir.** Um fato do tipo `command` exige que aquele comando exato tenha saído
  com código 0 na sessão; todo caminho citado precisa existir dentro do projeto; um fato sem comando nem caminho é
  recusado. Segredos e comandos de uso único (`python -c …`) nunca entram.
- **Os fatos se mantêm sozinhos, sem chamar modelo.** Quando um comando lembrado roda de novo e passa, o fato é
  confirmado; se falha duas vezes seguidas, sai do índice. Um fato cujo arquivo sumiu também sai, marcado como fora de uso.
- **Duas formas de escrever, um portão só.** O agente principal tem a ferramenta `remember`; e, no fim de uma sessão
  verificada que explorou o projeto sem salvar nada, o modelo auxiliar propõe até três fatos — que passam pela mesma
  conferência. Se não há nada novo, essa passagem não roda e não gasta tokens.
- **Limite de 40 fatos por projeto**; os menos confirmados saem primeiro.

```bash
hangar memory                      # lista os fatos deste projeto
hangar memory rm test-command      # apaga um
hangar memory clear                # apaga todos
hangar run "…" --no-memory         # esta execução não lê nem escreve memória
```

No app web, os fatos aparecem no painel **Harness**, com botão para esquecer. Sub-agentes, planejador e revisor leem a
memória, mas só o agente principal escreve. `memory = false` na configuração desliga tudo.

## O app web (`hangar ui`)

```bash
python -m hangar ui
```

Abre em `http://127.0.0.1:3090` uma interface completa, com o mesmo desenho do Agent Hangar Desktop:

- **Sessões** na barra lateral (buscar, fixar, renomear, arquivar), cada uma com a sua pasta, modelo, esforço e modo de
  permissão. A conversa continua depois de fechar e reabrir.
- **Conversa** com streaming, diff das edições, cartões de permissão e de pergunta, lista de tarefas e custo por rodada.
- **Modos de trabalho**: Conversa (vários turnos), Executar e revisar (`verify`) ou Planejar, executar e revisar (`pev`);
  nos dois últimos a tarefa roda até o fim, com um revisor independente, e cada etapa aparece na conversa e no grafo.
- **Anexos e gravação**: anexe arquivos (botão, arrastar, colar imagem) ou grave a tela e o microfone pelo navegador;
  a gravação vira um anexo `.webm`. Para o modelo entender vídeo e áudio é preciso o `ffmpeg` e um modelo de percepção.
- **Painéis**: Terminal, Alterações (git), Arquivos, Navegador, Artifacts, Harness e Grafo ao vivo.

O servidor escuta só em `127.0.0.1` e exige um token gerado a cada execução; ele lê arquivos apenas dentro da pasta de
cada sessão. O Terminal roda comandos avulsos (não é um terminal interativo).

## Modo bridge: o harness como motor de outro programa

`python -m hangar bridge` mantém uma conversa por processo e fala JSON em linhas pelo stdin/stdout. É como o
[Agent Hangar Desktop](https://github.com/valteresj2/hangar) roda sessões no Hangar Harness.

```
hospedeiro -> harness                                   harness -> hospedeiro
{"type":"start", cwd, model, base_url, permission}      {"type":"ready", session, resumed, model, context_window}
{"type":"user", text, attachments?, images?}            delta · thinking · assistant · tool_start · tool_end · plan · notice…
{"type":"permission_response", qid, decision, message?} {"type":"permission", qid, tool, args, title, can_always}
{"type":"answer", qid, answer}                          {"type":"question", qid, question, options}
{"type":"interrupt"} · {"type":"set_options", ...}      {"type":"turn_end", status, cost, prompt, completion, cached, …}
{"type":"close"}
```

- A chave da API vai na variável de ambiente `HANGAR_BRIDGE_KEY`, nunca numa mensagem.
- `permission`: `ask` (pergunta antes de escrever e de rodar comandos), `edits` (só comandos perguntam), `auto`, `readonly` (modo plano).
- `resume: <id>` no `start` continua a conversa de uma sessão anterior. O stdout carrega só o protocolo.
- Testado de ponta a ponta contra um servidor falso em `tests/test_bridge.py`.

## Regras do projeto: ganchos e plugins

Política do projeto fica em código, não em pedidos ao modelo. Em `hangar.toml`:

```toml
[[hooks]]                       # nunca tocar nos testes
event = "pre_tool"
tool = "write|edit"
match = "tests/"
action = "deny"
message = "os testes são a especificação"

[[hooks]]                       # só termina com os testes passando
event = "pre_finish"
action = "run"
command = "python -m unittest -q"

[[hooks]]                       # lint depois de cada edição; a saída volta para o modelo
event = "post_tool"
tool = "write|edit"
action = "run"
command = "python -m ruff check ."
```

Eventos: `pre_tool`, `post_tool`, `pre_finish`, `session_end`. Ações: `deny`, `ask`, `warn`, `run`. `tool` e `match` são expressões regulares
(sobre o nome da tool e sobre os argumentos em JSON). Um `pre_finish` que falha devolve o agente ao trabalho, até 3 vezes; se ainda falhar, a sessão sai como `incomplete`.

Plugins em Python (`~/.hangar/plugins/*.py` ou `.hangar/plugins/*.py` do projeto) podem definir `pre_tool`, `post_tool`, `pre_finish` e `session_end`.

**Confiança:** regras que só restringem (`deny`, `ask`, `warn`) valem sempre. O que executa código vindo da pasta do projeto (`action = "run"` e plugins `.py`)
só roda com `--trust-project` ou com a pasta em `trusted_projects` no `~/.hangar/config.toml` — um repositório não consegue se declarar confiável.
`python -m hangar hooks` mostra o que está ativo.

**Cuidado ao escrever `match`:** o agente pode pôr opções no meio do comando. `git\\s+commit` não pega `git -c user.name=x commit`; use
`\\bgit\\b[^|;&]*\\bcommit\\b`. É casamento de texto, não análise do comando: serve de trilho, não de sandbox.

## Lições entre sessões

Ao fim de uma sessão, um modelo auxiliar barato pode registrar até 2 lições em `~/.hangar/lessons/`; na sessão seguinte as mais relevantes entram como dicas junto da tarefa.

- **Só aprende do que foi verificado**: a sessão precisa ter terminado `done` com o último comando em sucesso (ou revisor aprovando) **e** ter tido atrito real. Sem atrito não há chamada extra, logo não há custo.
- **Com procedência**: cada lição guarda sessão, modelo, data, pasta e a evidência em que se apoia.
- **Sem acúmulo**: lição parecida é fundida (conta confirmações), expira em 90 dias e a biblioteca tem teto de 200.
- **Escopo**: `project` vale só para aquela pasta; `general` vale para a máquina e entra apenas se combinar com a tarefa nova.
- **Não aprende a contornar regra**: o que um gancho bloqueou é política, não lição.

`python -m hangar lessons` lista (com evidência), `lessons rm <id>` e `lessons clear` removem; `--no-lessons` desliga numa execução (o benchmark roda sempre assim).

## Economia de tokens (onde o dinheiro vai)

1. **Prefixo estável** — system prompt sem relógio nem contadores, tools em ordem fixa, histórico append-only, `session_id` para roteamento fixo: o cache do provedor acerta turno após turno.
2. **Teto na entrada** — todo resultado de tool é cortado (cabeça + cauda) ao entrar no contexto; o resto vai para disco com o caminho para `grep`/`read`.
3. **Limpeza em lote** — ao encher 60% do orçamento, resultados antigos são limpos de uma vez (uma reconstrução de cache, não uma por turno).
4. **Sumarização só no fim** — a 85%, um modelo auxiliar barato gera um checkpoint; a transcrição completa fica em disco.
5. **Carga adiada** — skills só com nome + descrição; com muitas tools MCP, entram `tool_search` + `mcp_call` em vez de dezenas de schemas.
6. **Poucas tools, descrições curtas** — 14 tools nativas (12 para modelos fracos); o schema é reenviado a cada chamada.
7. **Guardas de gasto** — limite de passos, orçamento em US$ por tarefa, disjuntor para chamada repetida, `max_tokens` em toda chamada, raciocínio em `low` por padrão.
8. **Sub-agentes como firewall de contexto** — `task` devolve só um relatório curto (desligado em modelos fracos).
9. **Barato primeiro** — com `--escalate`, o modelo caro só entra quando o barato trava (ver BENCHMARK.md).

## Workflows como grafos

O padrão é **um loop** (mais barato e mais fácil de depurar). Grafos entram quando há um gatilho real: especialização, paralelismo ou verificação independente.

| Workflow | Grafo | Quando usar |
|---|---|---|
| `loop` | work | padrão |
| `verify` | work → review ⟲ | quando errar custa caro: revisor de contexto limpo ("goldfish") checa o resultado |
| `pev` | plan → execute → review ⟲ | modelo forte planeja, modelo barato executa, revisor aprova |

Workflows próprios são JSON em `.hangar/workflows/<nome>.json` com nós `agent`, `verify`, `shell` (portão determinístico) e `human`:

```json
{"name": "tdd", "start": "code", "nodes": [
  {"id": "code", "type": "agent", "model": "$worker", "prompt": "{task}", "retry_prompt": "Os testes falharam:\n{feedback}\nCorrija.", "next": "tests"},
  {"id": "tests", "type": "shell", "command": "python -m unittest -q", "next": {"ok": "$end", "fail": "code"}, "max_visits": 4}
]}
```

Todo nó tem limite de visitas; o estado é salvo em `checkpoint.json` após cada nó.

## Configuração (`hangar.toml` no projeto ou `~/.hangar/config.toml`)

```toml
model = "openai/gpt-6-luna"
planner_model = "anthropic/claude-sonnet-5.5"
perception_model = "meta/muse-ember"
max_cost_usd = 2.0
permission = "auto"        # auto | ask | readonly

[tiers]
"ollama:qwen3" = "weak"    # strong | standard | weak

[providers.meu_gateway]
base_url = "http://localhost:4000/v1"
api_key_env = "MEU_GATEWAY_KEY"
```

## Limites honestos

- A proteção do shell é uma lista de padrões destrutivos + confirmação, **não um sandbox**. Para código não confiável, rode em contêiner/VM.
- Servidores MCP do `.mcp.json` do projeto são iniciados automaticamente: só use em pastas em que você confia.
- `web_search` usa a página HTML do DuckDuckGo (sem chave) e pode falhar; conecte um MCP de busca para uso sério.
- `undo` cobre só o que passou por `write`/`edit`; o que um comando de shell alterou não é desfeito.
- O bloqueio de "matar por nome" e a lista de comandos destrutivos são heurísticas por padrão de texto: um comando ofuscado passa.
- As lições são escritas por um modelo e podem estar erradas mesmo com evidência; revise com `hangar lessons` de tempos em tempos. O ganho medido até agora vem de um único caso.

## Estrutura

```
hangar/  agent.py (loop) · graph.py (workflows) · tools.py · toolcall.py (reparo/protocolo textual) · context.py (economia)
         llm.py · models.py (catálogo/tiers) · media.py (multimodal) · mcp.py · skills.py · machine.py · session.py · events.py
         hooks.py (regras e plugins no loop) · lessons.py (lições entre sessões)
         studio.py + browser.py + pptx.py (peças visuais) · skills/ (5 skills embutidas)
         bridge.py (motor para outros programas, protocolo stdio)
         server.py + ui.html + flow.js (dashboard e grafo ao vivo) · cli.py
bench/   tasks.py (7 tarefas rápidas) · tasks_hard.py + tinylang.py (4 tarefas complexas) · tasks_studio.py (análise de dados com 6 entregáveis) · run_bench.py (Hangar × modelos, e Claude Code)
tests/   test_core.py · mcp_vault_server.py
docs/    PESQUISA.md · BENCHMARK.md
```

## Licença

[MIT](LICENSE).
