# Changelog

## v0.7.2

- **Ajuste à força do modelo, como opção** (`--fit`, `model_fit = true`): modelo fraco tem de registrar um plano de 3 a 6
  passos antes de alterar qualquer coisa (o harness cobra o plano, lembra o próximo passo e devolve uma vez o "terminei"
  com itens abertos); modelo forte recebe um catálogo sem `glob`, `grep` e `web_fetch`, que o shell cobre. Catálogos
  restritos pelo aplicativo e papéis sem shell não mudam.
- **Vem desligado, porque a medição não mostrou ganho**: em 120 execuções nas quatro tarefas difíceis de código, o
  catálogo enxuto não mudou acerto nem custo de forma consistente nos modelos fortes, e o plano obrigatório dobrou o
  tempo de um modelo barato que já acertava tudo, sem ganho de acerto sustentável nos que falham. Números em
  `docs/BENCHMARK.md`.

## v0.7.1

- **O harness executa as checagens do crítico**: cada defeito pode vir com um comando de leitura que falha agora e passa
  depois da correção. O harness roda o comando antes de devolver o defeito (se já passa, o defeito é descartado) e de
  novo quando o agente diz que terminou; o que ainda falha volta ao agente sem pagar outra revisão, até duas vezes.
- **Checagem tem de testar o trabalho, não o texto**: comandos que leem o relatório (`.html`, `.md`, `.txt`) são
  recusados, porque procurar uma palavra se resolve reescrevendo a frase. O crítico passa a pedir que o script da
  análise grave os números num `evidence.json` e a comparar valores (por exemplo, o AUC do resumo igual ao AUC da
  validação no tempo). `hangar studio` continua aceito, porque inspeciona a página como um navegador.
- **Regra de parada**: a partir da segunda revisão só contam defeitos com checagem que falha; sem nenhum, a entrega é
  aprovada.
- **Revisão que piora é desfeita**: os arquivos entregues são guardados antes da correção pedida pelo crítico e
  restaurados se, depois dela, a trava de uma skill deixar de passar.
- As checagens só rodam com `permission = "auto"` e nunca comandos que escrevem, apagam, instalam ou baixam.
- **O que isso não resolveu**, medido em duas bases com três rodadas cada: o custo e o tempo ficaram no nível da v0.7.0,
  o crítico continuou sem aprovar nenhuma entrega e, na segunda base, não apontou o uso de variáveis que só existem
  depois da decisão. Detalhes em `docs/BENCHMARK.md`.

## v0.7.0

- **Camada de qualidade** (`--critic`, `hangar/critic.py`): antes de aceitar o "terminei", o modelo mais forte da lista lê
  a entrega e aprova ou devolve até três defeitos, cada um com a evidência, o que fazer e como saber que ficou certo. É
  uma chamada só, sem ferramentas, sobre um resumo dos arquivos entregues (não sobre a conversa), feita depois das
  checagens gratuitas e no máximo duas vezes por agente. `--critic <modelo>` escolhe o modelo, `--critic-scope all`
  estende a sub-agentes e ao planejador; o gasto aparece na linha "crítico" da conta por papel. Desligada por padrão: nas
  nossas medições ela leva uma análise de dados de US$ 0,006 para cerca de US$ 0,20. Uma skill pode trazer critérios
  próprios num `RUBRIC.md`.
- **Trava de skill**: uma skill pode declarar no cabeçalho o comando que prova que o trabalho terminou (`gate`,
  `gate_fail`, `gate_hint`). Se a sessão carregou a skill e esse comando ainda não passou, o harness recusa o "terminei"
  e devolve o que falta (no máximo duas vezes). Vale a saída do comando, não só o código de retorno.
- **Relatórios de análise** (`hangar studio report`): `build` transforma um JSON (seções, tabelas, gráficos de barra e de
  linha, imagens embutidas) num HTML único, com números no formato do leitor; `check` lista o que falta num relatório —
  seções, tabelas, gráficos, colunas da base nunca tratadas, linha de base, validação, importância das variáveis, ganho,
  limites e recomendações.
- **Skill `data-analysis` reescrita**: profundidade como padrão, roteiro de oito seções, regras de modelagem (só o que
  se conhece na hora da decisão, linha de base, validação, ganho por decil) e a trava apontando para `report check`.
- **Benchmark de análise de dados** (`bench/tasks_data.py`): duas bases públicas da UCI com gabarito de fatos recalculados
  da base. O arquivo de dados não acompanha o repositório.
- **Correções no benchmark contra o Claude Code**: o ambiente do processo filho é limpo, a ferramenta PowerShell é
  permitida no Windows, a pasta temporária usa o caminho longo, as recusas de permissão ficam registradas e uma execução
  que não chegou a rodar deixa de contar como falha. Os números anteriores a essas correções foram descartados.

## v0.6.0

- **Backlog do projeto** (`hangar backlog`, `<projeto>/.hangar/backlog.json`): para objetivos maiores que uma sessão. Um
  planejador divide o objetivo em tarefas com dependências e um comando de aceite cada; `hangar backlog run` pega a
  próxima tarefa liberada, uma sessão trabalha nela, e é o harness que roda o comando de aceite — e, em seguida, os
  comandos de todas as tarefas já concluídas, para nada quebrar. A falha volta para a mesma sessão (até três
  conferências). `--all`, `--tasks`, `--budget`, `check` (auditoria sem modelo), `reset`, `add`. O plano é validado antes
  de ser gravado; comandos de aceite repetidos entre tarefas voltam uma vez para o planejador corrigir. O aceite roda no
  ambiente do usuário, não no do shell do agente.
- **Memória do projeto** (`<projeto>/.hangar/memory/`): o agente guarda fatos duráveis do projeto — como rodar os
  testes, onde ficam as coisas, convenções, armadilhas — em arquivos Markdown, um por fato, com um índice que entra no
  contexto de cada sessão. Um fato só é gravado com uma conferência que o próprio harness faz (o comando saiu com
  código 0 nesta sessão; os caminhos existem); comandos lembrados que voltam a rodar confirmam ou derrubam o fato sem
  chamar modelo. Ferramenta `remember`, passagem de fim de sessão no modelo auxiliar (só quando há algo novo),
  `hangar memory`, `--no-memory`, e a lista no painel Harness do app web.
- `bench/memory_bench.py`: mede a memória com duas tarefas diferentes no mesmo projeto (aprende na primeira, compara a
  segunda com e sem memória). O benchmark geral continua rodando sem memória, para cada execução começar do zero.

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
