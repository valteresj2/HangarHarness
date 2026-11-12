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
| Conexão fácil com tools | MCP stdio e HTTP lendo o mesmo `.mcp.json` do Claude Code; skills `SKILL.md` (pastas `.hangar/skills`, `.claude/skills`, `~/.claude/skills`); instruções de projeto em `HANGAR.md` / `AGENTS.md` / `CLAUDE.md`. |
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
         server.py + ui.html + flow.js (dashboard e grafo ao vivo) · cli.py
bench/   tasks.py (7 tarefas rápidas) · tasks_hard.py + tinylang.py (4 tarefas complexas) · run_bench.py (Hangar × modelos, e Claude Code)
tests/   test_core.py · mcp_vault_server.py
docs/    PESQUISA.md · BENCHMARK.md
```
