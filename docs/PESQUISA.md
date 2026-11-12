# Pesquisa: o que entrou no Hangar e de onde veio

Síntese das fontes indicadas e do que encontrei além delas (novembro de 2026). Cada item diz onde virou código.

## 1. Das ferramentas

**Codex CLI (OpenAI)** — agente local com modos de aprovação e sandbox, `codex exec` não interativo, `AGENTS.md`, MCP, sub-agentes, skills, anexo de imagem, retomada de sessão.
→ No Hangar: `run --json` para automação, `permission = auto|ask|readonly`, leitura de `AGENTS.md`, MCP, skills, `-a` para anexos.

**Claude Code** — loop único com tools pequenas e precisas (Read/Edit/Glob/Grep/Bash), edição por substituição exata, lista de tarefas, pergunta ao usuário, sub-agentes como isolamento de contexto, teto de ~25k tokens por resposta de tool, skills com divulgação progressiva, `.mcp.json`.
→ No Hangar: o mesmo desenho de tools, `edit` por trecho exato (com tolerância a indentação), `plan`, `ask_user`, `task`, mesmo formato de `.mcp.json` e de `SKILL.md`.

**DeepSeek Harness (dsh)** — arquitetura "tudo é plugin" sobre o Cordis, Web UI local em `127.0.0.1:3080`. A página pública não detalha loop, contexto nem economia de tokens (não consegui abrir `docs/architecture.md`).
→ No Hangar: UI web local como cidadão de primeira classe, e extensão por dados (workflows JSON, MCP, skills) em vez de alterar o núcleo.

**Elephant-Goldfish Model (Google)** — "projete com um elefante, revise com um peixinho-dourado": o agente principal guarda o contexto; revisores novos, sem a conversa anterior, expõem suposições não declaradas. Se não dá para criar contexto limpo, a revisão para.
→ No Hangar: nó `verify` sempre cria um agente novo que recebe só a tarefa, os arquivos alterados e a resposta final, com tools de leitura + shell e veredito estruturado.

## 2. Dos artigos de graph engineering

Fontes: survey arXiv 2608.21156 (Graph Engineering: de inteligência individual a inteligência de sistema), Wavect, Analytics Vidhya e DataCamp (os artigos do Towards Data Science e do Medium bloquearam o acesso automático — usei os resumos públicos e artigos equivalentes).

- **Escada**: prompt → contexto → harness → loop → grafo. Pular degraus produz um sistema que falha em mais lugares.
- **O padrão é o loop.** Grafo só com gatilho real: especialização (modelos/tools diferentes por etapa), paralelismo que se nota, ou verificação por quem não produziu o trabalho.
- **"A engenharia mora nas arestas"**: roteamento, limites de repetição e portões de qualidade ficam nas arestas, não escondidos dentro dos nós.
- **Regras conhecidas ficam em código**, LLM só para interpretação e ambiguidade.
- **Estado tipado e pequeno**, cada nó vê só o que precisa; checkpoint durável; todo loop com teto.
- **Revisor separado e somente leitura** é frequentemente o nó mais valioso; veredito estruturado, não prefixo de texto.
- **Custo**: multiagente usa ~15× os tokens de um chat (medição da Anthropic); fan-out + retry multiplicam o gasto de formas que o diagrama esconde; conte as chamadas antes de construir.
- **Grafo de conhecimento** (Wavect): só compensa com perguntas multi-salto, fatos que mudam no tempo, proveniência e reuso entre sessões; num teste citado, GraphRAG somou 61% de tokens sem melhorar o recall.

→ No Hangar: `graph.py` é um motor de ~150 linhas com nós `agent | verify | shell | human`, rotas nas arestas, `max_visits` em todo nó, estado em `checkpoint.json`, workflows como JSON. `loop` é o padrão; `verify` e `pev` são opt-in. Não incluí grafo de conhecimento: nenhum dos gatilhos se aplica a um harness de tarefas — o `graphify` que você já usa cobre esse papel e pode ser plugado como skill/MCP.

## 3. De economia de tokens (pesquisa adicional)

| Achado | Fonte | No Hangar |
|---|---|---|
| Cache de prompt é a maior alavanca; exige prefixo idêntico byte a byte desde o token zero | docs OpenRouter, Bouchard, dev.to | system prompt sem relógio, sondagem da máquina cacheada por 24h, histórico append-only, `session_id` |
| Leitura de cache custa 0,1× (Anthropic, DeepSeek) a 0,25–0,5× (OpenAI, Gemini, Grok) | docs OpenRouter | `cache_control` automático para Anthropic; os demais são implícitos |
| Sumarizar quebra o cache; manter tudo + cache ganhou em custo e em memória (92% vs 38% de recall) | Bouchard | sumarização só a 85% do orçamento |
| Só limitar a saída das tools cortou 38% do custo por turno sem perder memória | Bouchard | `tool_output_cap` + spill em disco |
| Escada de compactação: truncar/limpar → sumarizar → realocar para arquivos | Bouchard | níveis 0, 1 e 2 em `context.py` |
| Schemas de tools reenviados sem cache são puro desperdício; adiar e anexar, não trocar | dev.to | `tool_search` + `mcp_call`, lista de tools fixa |
| Sub-agente queima dezenas de milhares de tokens e devolve 1–2k | dev.to | `task` limitado a 8 KB de relatório |
| Delegação só é confiável nos modelos mais fortes (0,85 vs ~0,43) | dev.to | `task` removido no tier `weak` |
| Higiene para modelos fracos: recuperar JSON duplamente codificado, erros limpos, schemas simples | dev.to | `toolcall.py` |
| Disjuntor para chamada idêntica repetida; teto de iterações | dev.to | guarda de repetição + `max_steps` + `max_cost_usd` |
| Saída custa ~5× a entrada: limitar `max_tokens`, pedir raciocínio curto | dev.to | `max_output_tokens`, `reasoning_effort = low` |

Ressalva: vários desses números vêm de um único blog ou estudo de fornecedor. Usei-os como direção de projeto; o que vale para este harness é o que o benchmark em `BENCHMARK.md` mede.

## 4. Harness² (Google Research, arXiv 2610.14224)

Camada que reescreve o harness de outro agente (OpenCode/Codex) sem tocar no modelo, em dois níveis: por tarefa, um passo
**Propose–Probe–Compose** (roda a tarefa, propõe edições, roda de novo com cada candidato e compõe um harness melhor, sem gabarito);
entre tarefas, uma **biblioteca de melhorias** com o harness adotado e um `EXPERIENCE.md` (situação, fraqueza, mudança, evidência).
Trata o harness como oito componentes editáveis: prompt, guardrails, memória, skills, orientação de tools, scripts, sub-agentes e plugins.
Reporta até +11,5 pontos com um passo; na ablação, tirar a biblioteca custa ~3 pontos.

| Ideia | Decisão no Hangar |
|---|---|
| Biblioteca de experiência com evidência | **Adotada** (`lessons.py`): só de sessões verificadas e com atrito, com procedência, fusão de duplicatas e validade |
| Plugins como middleware no loop de tools | **Adotada** (`hooks.py`): regras declarativas e plugins Python em `pre_tool`, `post_tool`, `pre_finish`, `session_end` |
| Edições "invariantes" x "de domínio" | Adotada como escopo das lições: `general` x `project` |
| Propose–Probe–Compose em toda tarefa | **Não adotada**: ≥ 4 execuções por tarefa, e a seleção sem gabarito erra (o artigo relata 55 preferido a 95). Aqui o modelo barato já resolve as tarefas complexas por centavos, e o workflow `verify` cobre a checagem independente |
| Ajuste do harness contra benchmark | Em aberto: faria sentido offline, onde temos verificador determinístico |

Avisos do artigo que vimos na prática: agente buscando o gabarito (aqui, um modelo lendo as pastas das execuções vizinhas) e execução sem sandbox.

## Fontes

- https://github.com/openai/codex · https://learn.chatgpt.com/docs/codex/cli
- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/google/elephant-goldfish-model
- https://tldr.takara.ai/p/2608.21156 · https://github.com/DEEP-JLU/Awesome-Graph-Engineering
- https://wavect.io/blog/graph-engineering-ai-agents.md
- https://www.analyticsvidhya.com/blog/2026/07/graph-engineering/
- https://www.datacamp.com/tutorial/graph-engineering-guide
- https://towardsdatascience.com/graph-engineering-for-ai-agents-from-prompts-and-loops-to-workflows/ (acesso bloqueado)
- https://medium.com/@adnanmasood/graph-engineering-for-ai-agents-the-practitioners-guide-to-designing-multi-agent-systems-as-f9a4559aa693 (acesso bloqueado)
- https://www.louisbouchard.ai/context-engineering-2026/
- https://dev.to/truongpx396/optimizing-ai-agents-token-economics-the-harness-context-engineering-5bg1
- https://openrouter.ai/docs/guides/best-practices/prompt-caching
- https://github.com/google-research/harness2 · https://arxiv.org/abs/2610.14224 · https://aiidelist.com/blog/google-harness2-self-improving-ai-agents.md
