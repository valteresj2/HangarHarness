# Changelog

## Não lançado

- Licença MIT adicionada (`LICENSE`).

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
