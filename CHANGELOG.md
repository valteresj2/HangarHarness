# Changelog

## v0.5.0

- **Equipe de modelos gerada do benchmark**: `python bench/roster.py` lê `bench/results/*.json` e grava `hangar/roster.json`,
  que o roteador usa no lugar da lista escrita à mão. Um modelo só entra num papel se resolveu todas as execuções das
  tarefas que o papel exige (mínimo de duas por tarefa); a ordem é o custo por tarefa resolvida. `~/.hangar/roster.json`
  substitui a lista que vem no pacote.
- **A equipe mudou com os números**: profundo, planejador e reforço passam de `gpt-6.1-terra`/`claude-sonnet-5.5` para
  `claude-haiku-5.5` — nos nossos resultados ele resolveu a tarefa mais difícil em todas as execuções por menos da metade
  do custo do Terra e um oitavo do Sonnet.
- **Conta por papel**: toda execução diz quanto cada papel gastou (executor, sub-agentes leve e profundo, planejador,
  revisor, reforço, auxiliar, percepção, estúdio) — no CLI, no `summary.json`/`meta.json` (`by_role`), no `turn_end` do
  bridge e no app web (linha abaixo da resposta e coluna de gasto no botão "Modelos", com a evidência de cada escolha).
- **Reforço indevido corrigido**: depois de os testes passarem, um comando só de consulta que falhava (`git status` numa
  pasta sem git, por exemplo) fazia o harness concluir que o trabalho não estava verificado e chamar o modelo de reforço.
  Agora uma consulta que falha não desfaz uma verificação que passou, desde que nada tenha sido editado depois. Em três
  execuções reais de `pev` na tarefa `bugfix`, o custo caiu de US$ 0,0053 para US$ 0,0024–0,0030.
- **Validado com modelos reais** (equipe automática): `pev` em `bugfix` e `feature`; imagem, áudio e vídeo pelo CLI e
  pelo app web (anexo enviado por upload); a conta por papel bate com o total em todas as execuções.

## v0.4.2

- **Grafo ao vivo com o mouse**: arraste para mover a tela, roda do mouse para dar zoom no ponto do cursor, duplo clique no
  fundo (ou "ajustar") para encaixar o grafo inteiro. Ao mexer, o "seguir" é desligado para a tela não pular.

## v0.4.1

- **Equipe de modelos automática** (`model = "auto"`, `hangar run -m auto`): o harness escolhe o modelo de cada papel pelo
  custo por tarefa resolvida nos nossos benchmarks — executor barato, planejador forte, revisor de outro fornecedor,
  reforço que assume quando o executor trava, e modelos próprios para resumir contexto e perceber mídia. Cada papel pode
  ser trocado na tabela `[team]` da configuração.
- **Sub-agentes por nível**: a ferramenta `task` aceita `level` — `light` (busca, leitura, resumo: modelo mais barato) ou
  `deep` (raciocínio difícil: modelo mais forte). Quem delega decide quanto vale gastar.
- **App web sem seletor de modelo**: toda sessão roda na equipe automática; o botão "Modelos: automático" mostra quem faz
  o quê, e a linha de status mostra o modelo que respondeu.
- App web alinhado ao desenho do harness: esforço padrão do harness (baixo) em vez de alto; teto de custo por rodada, e
  não pela conversa inteira; lições aprendidas e regras de fim de sessão ao fechar a conversa; resumo de contexto no
  modelo auxiliar, e não no principal.
- **Modos de trabalho na tela de nova sessão**: além de Conversa, agora dá para iniciar pela interface uma tarefa em
  **Executar e revisar** (`verify`: um revisor independente confere e devolve para correção) ou **Planejar, executar e
  revisar** (`pev`: um modelo planeja, outro executa, um revisor confere), com modelo opcional para o planejador/revisor.
- A tarefa aparece com um divisor por etapa (Planejamento, Execução, Revisão independente), o veredito do revisor e o
  grafo ao vivo aberto, com uma raia por etapa.
- Grafo: o veredito fica na raia do revisor mesmo quando ele não chama nenhuma ferramenta.

## v0.4.0

- **Novo app web** (`hangar ui`), com a mesma cara do Agent Hangar Desktop: barra lateral de sessões (nova, buscar, fixar,
  renomear, arquivar, excluir), conversa com streaming, cartões de ferramenta com diff, cartões de permissão (permitir,
  permitir sempre, negar com motivo) e de pergunta, lista de tarefas fixada, linha de custo/tokens/contexto por rodada, tema
  claro e escuro.
- **Composer**: anexar arquivos (botão, arrastar e soltar, colar imagem), comandos de barra do projeto (`/`), menção de
  arquivos (`@`), troca de modelo, esforço e modo de permissão por sessão, fila de mensagens e Parar.
- **Gravação**: tela + microfone ou só microfone, direto do navegador, com pausar/continuar; o `.webm` vira anexo da mensagem.
- **Painéis laterais**: Terminal (comandos na pasta da sessão), Alterações (git status e diff), Arquivos (árvore, filtro e
  visualizador), Navegador (servidores locais), Artifacts (HTML, SVG, Markdown, imagens e vídeos que o agente criou),
  Harness (instruções, sub-agentes, comandos, skills, hooks e lições, com editor) e **Grafo ao vivo**.
- Cada sessão é um processo `hangar bridge`; a conversa é retomada depois de fechar o app. Rodadas do CLI continuam
  aparecendo, em modo leitura.
- Segurança: token por execução em toda chamada de API, checagem de host local, leitura de arquivos restrita à pasta da
  sessão e artifacts servidos em sandbox (origem opaca).
- Bridge: opção `lessons`. Navegador headless: `extra_args`.

## v0.3.0

- **Superfície `.claude/` do projeto**: além de `CLAUDE.md`/`AGENTS.md`/`HANGAR.md` na raiz, o harness agora lê `.claude/CLAUDE.md`,
  os sub-agentes de `.claude/agents/*.md` (delegados com `task(prompt, agent="nome")`), os comandos de barra de
  `.claude/commands/**/*.md` (`/nome argumentos`, com `$ARGUMENTS` e `$1`…) e, em projetos confiáveis, os hooks do Claude Code
  de `.claude/settings.json` (`PreToolUse`, `PostToolUse`, `Stop`; bloqueio por código de saída 2 ou `decision: block`).
  Um harness escrito para o Claude Code vale também aqui.
- **Bridge**: `trust_project` (o hospedeiro atesta a pasta), `allowed_tools` (restringe as tools da conversa; `[]` = juiz sem tools),
  `confine` (as tools de arquivo não saem da pasta de trabalho) e a lista de comandos de barra no evento `ready`.

## v0.2.0

- **Modo bridge** (`python -m hangar bridge`): o harness como motor de outro programa, por JSON em linhas no stdin/stdout.
  Conversa multi-turno, pedidos de permissão estruturados (permitir, permitir sempre, negar com motivo), perguntas, interrupção,
  troca de modelo e de modo entre turnos e retomada por id de sessão. É o que o app Agent Hangar Desktop usa.
- Modo de permissão `edits` (edições na pasta sem perguntar; comandos ainda perguntam) e interrupção que cancela o stream do modelo e o comando em execução.
- Evento `thinking` com o raciocínio do modelo; `model_info` e `system_append` configuráveis pelo hospedeiro; servidores MCP extras passados pelo hospedeiro.

- **Estúdio** (`python -m hangar studio`): `screenshot`/`check` (navegador headless via DevTools, sem dependências), `video` (HTML/three.js para MP4
  quadro a quadro), `image` (modelos de imagem do OpenRouter) e `pptx` (PowerPoint nativo com texto editável).
- Cinco skills embutidas: `data-analysis`, `dashboard`, `presentation`, `image-generation`, `motion-video`.
- Gasto de comandos do estúdio (imagens) contabilizado na sessão.
- Tarefa de benchmark `studio`: análise de dados com dashboard, deck HTML, PPTX, imagem e vídeo.

## v0.1.1

- Licença MIT adicionada (`LICENSE`) e declarada no pacote. Nenhuma mudança de código em relação à v0.1.0.

## v0.1.0 — primeira versão

Harness de agentes em Python puro (só biblioteca padrão), testado em Windows 11 com modelos via OpenRouter.

### Núcleo
- Loop de agente único para qualquer modelo: tool-calling nativo ou protocolo textual, com reparo de JSON, aliases e coerção de argumentos.
- 14 tools nativas: arquivos (`read`, `write`, `edit`, `glob`, `grep`), `shell` (com execução em segundo plano), `process`, web, `perceive`, `ask_user`, `plan`, `note`, `task` (sub-agentes).
- Entrada multimodal (imagem, áudio, vídeo, PDF) nativa ou via modelo de percepção, com decomposição de vídeo por ffmpeg.
- MCP (stdio e HTTP, mesmo `.mcp.json` do Claude Code) e skills `SKILL.md` com carga adiada.
- Workflows como grafos em JSON: `loop`, `verify`, `pev`, e nós `agent`, `verify`, `shell`, `human`.

### Economia de tokens
- Prefixo estável para cache, teto por resultado de tool com spill em disco, limpeza em lote, sumarização com piso e histerese.

### Robustez
- Retomada de sessão (`resume`), status `incomplete`, escalonamento de modelo (`--escalate`), fallback de provedor (`--fallback`).
- Detector de estagnação, tratamento de saída truncada, escrita em partes, portões de conclusão.
- Backup e `undo` dos arquivos alterados; bloqueio de comandos que matam processos por nome.

### Política e aprendizado
- Ganchos declarativos e plugins Python em `pre_tool`, `post_tool`, `pre_finish`, `session_end`, com modelo de confiança por projeto.
- Biblioteca de lições entre sessões, só de sessões verificadas, com procedência, fusão e validade.

### Observabilidade
- Log JSONL de todos os eventos por sessão.
- Dashboard web em tempo real (`hangar ui`) com linha do tempo e grafo ao vivo do workflow em SVG.

### Benchmark
- 7 tarefas rápidas e 4 complexas com verificador determinístico (`bench/`); resultados em `docs/BENCHMARK.md`.

### Limites conhecidos
- Não há sandbox: as proteções de shell são heurísticas por padrão de texto.
- Testado apenas em Windows 11.
- A comparação com o Claude Code não foi executada.
- Sem licença definida nesta versão.
