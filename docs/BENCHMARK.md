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

## Comparação com o Claude Code (14/11/2026)

`claude -p` (Claude Code 2.1.307, configuração padrão, modo `acceptEdits`), mesmas tarefas, mesma pasta inicial e mesmo
verificador. Custos a preço de API; o do Claude Code é o `total_cost_usd` que ele mesmo informa (numa assinatura não há
cobrança por chamada).

**Mesmo modelo dos dois lados** (`claude-haiku-5.5`), mediana de cinco execuções por tarefa:

| Tarefa | Hangar ok | Custo | Tempo | Tokens entrada | Claude Code ok | Custo | Tempo | Tokens entrada |
|---|---|---|---|---|---|---|---|---|
| bugfix | 5/5 | $0.0017 | 8.7s | 20,7k | 5/5 | $0.0062 | 15.6s | 155k |
| feature | 5/5 | $0.0017 | 9.6s | 17,1k | 5/5 | $0.0095 | 24.6s | 167k |
| kvstore | 5/5 | $0.0055 | 37.4s | 46,8k | 5/5 | $0.0353 | 181.8s | 1.103k |
| **soma** | 15/15 | **$0.0088** | 55.7s | 84,5k | 15/15 | **$0.0510** | 222.0s | 1.425k |

Com o mesmo modelo, o Hangar gastou 5,8× menos, enviou 16,9× menos tokens de entrada, 3,4× menos de saída, e levou 4× menos tempo.

Custo fixo de sessão (`"Responda apenas: ok"`, Haiku 5.5): Claude Code 26.878 tokens de entrada (US$ 0,00246 com cache
frio, US$ 0,00027 quente); Hangar 2.942 (US$ 0,00037 e US$ 0,00003).

**Equipe automática contra o Fable 5.2**, média de duas execuções por tarefa:

| Tarefa | Hangar `auto` | Claude Code (`claude-fable-5-2`) |
|---|---|---|
| bugfix | ✅✅ $0.0009 · 16s · 19,6k | ✅✅ $0.380 · 15s · 111k |
| feature | ✅✅ $0.0017 · 16s · 30,7k | ✅✅ $0.389 · 21s · 77k |
| kvstore | ✅✅ $0.0033 · 54s · 73,1k | ✅✅ $1.008 · 118s · 123k |
| **soma** | **$0.0059** · 86s · 123k | **$1.78** · 154s · 311k |

Aqui o que pesa é o preço do modelo (cerca de 300× no custo, 2,5× nos tokens de entrada): as tarefas não precisam de um modelo de fronteira.

**Um erro nosso que distorceu a primeira medição.** O runner liberava a ferramenta `Bash`, mas no Windows o Claude Code
executa comandos pela ferramenta `PowerShell`; e a pasta temporária ia com nome curto (`USUARI~1`), que ele recusa editar
como caminho suspeito. Com o Fable, as tarefas saíam mesmo assim (6/6), mas a US$ 3,20 e 1,07 milhão de tokens; com o
Haiku, 6 de 15 falhavam. Corrigido em `run_claude` (lista de ferramentas, caminho longo, ambiente limpo), e cada linha do
resultado agora traz `denials`: uma execução com ações negadas mede a configuração, não o agente.

## Análise de dados: uma tarefa aberta (14/11/2026)

Pedido: a análise completa do `bank-full.csv` (UCI Bank Marketing, 45.211 linhas), com relatório em HTML e um modelo
para escolher para quem ligar. Não há resposta única, então a nota vem de um gabarito de 13 itens recalculados da base
(tamanho, taxa de adesão, tratamento da variável que vaza o resultado, gráficos, recomendações) e do verificador
`hangar studio report check`, que conta o que falta no relatório. Mediana de 3 rodadas; todas entregaram os dois
arquivos pedidos.

| configuração | custo US$ | tokens de entrada | tempo | gabarito | tabelas | lacunas |
|---|---|---|---|---|---|---|
| Hangar, claude-haiku-5.5 (skill antiga) | 0,012 | 153 mil | 94 s | 12/13 | 3 | 4 |
| Hangar, claude-haiku-5.5 (skill nova + trava) | 0,017 | 291 mil | 129 s | 12/13 | 32 | 0 |
| Claude Code, claude-haiku-5.5 | 0,048 | 1,13 milhão | 239 s | 13/13 | 9 | 1 |
| Hangar, equipe automática (skill antiga) | 0,005 | 83 mil | 74 s | 12/13 | 1 | 7 |
| Hangar, equipe automática (skill nova + trava) | 0,006 | 167 mil | 112 s | 12/13 | 10 | 0 |
| Hangar, equipe automática + crítico (claude-sonnet-5.5) | 0,194 | 2,0 milhões | 422 s | 12/13 | 24 | 0 |
| Claude Code, claude-fable-5.2 | 3,55 (preço de API) | 893 mil | 487 s | 13/13 | 8 | 3 |

O que o gabarito não mede: o Claude Code com o modelo de fronteira percebeu que a base está em ordem cronológica,
validou o modelo no tempo e mostrou que o "melhor mês" é efeito do período. Sem crítico, o Hangar usa divisão aleatória
e reporta um número otimista. Com `--critic`, o crítico apontou esse defeito na primeira revisão das três rodadas, além
de erros de cálculo nas tabelas de associação; os três relatórios finais passaram a trazer a validação temporal (AUC de
0,74 no tempo contra 0,77 na divisão aleatória, a mesma faixa do modelo de fronteira). Do custo de US$ 0,19, cerca de
US$ 0,14 são as duas chamadas do crítico.

Limites: três rodadas por configuração, com custo variando bastante entre elas (o Claude Code com Haiku foi de US$ 0,044
a US$ 0,197); a skill nova foi escrita depois de ver esta tarefa, o que favorece o "depois" nesta base; a qualidade final
dos relatórios com crítico ainda não foi comparada por leitura lado a lado com a do modelo de fronteira; o crítico pediu
revisão nas duas rodadas de todas as execuções, ou seja, não chegou a aprovar nenhuma entrega.

### Crítico com checagens executadas, e uma segunda base (v0.7.1)

Na v0.7.1 o harness passou a executar as checagens que o crítico propõe e a recusar as que só leem o relatório. Para
separar o efeito da skill (escrita olhando a primeira base) medimos também uma segunda: `online_shoppers_intention.csv`
(UCI, 12.330 sessões de uma loja online), com gabarito de 11 itens. A armadilha dela é de enquadramento: várias colunas
(páginas vistas, tempo na sessão, valor da página) só existem depois que a visita acontece, e um modelo honesto para
decidir na chegada do visitante não pode usá-las. Equipe automática com crítico, mediana de 3 rodadas:

| | crítico da v0.7.0 | com checagens | checagens endurecidas (v0.7.1) |
|---|---|---|---|
| banco: custo US$ | 0,194 | 0,164 | 0,193 |
| banco: tempo | 422 s | 283 s | 419 s |
| banco: validação no tempo | 3 de 3 | 3 de 3 | 3 de 3 |
| loja: custo US$ | 0,212 | 0,182 | 0,181 |
| loja: tempo | 425 s | 325 s | 269 s |
| loja: gabarito | 10/11 | 11/11 | 10/11 |
| loja: modelo só com dados da chegada | 0 de 3 | 2 de 3 | 0 de 3 |

Referências na segunda base: equipe automática sem crítico, US$ 0,007 e 104 s (modelo só com dados da chegada em 1 de
3); Claude Code com claude-fable-5.2, US$ 2,89 a preço de API e 400 s (2 de 2 rodadas).

O que mudou de fato foi o tipo de checagem. Na versão intermediária a maioria procurava palavras no relatório; na
v0.7.1 todas comparam números gravados pelo script de análise (o AUC do resumo igual ao AUC temporal, o intervalo de
confiança contendo a estimativa, as contagens somando o total de linhas), e nas seis rodadas esses números batem com os
do relatório. Na base do banco, o número principal passou a ser o AUC temporal, não o da divisão aleatória.

O que não mudou: o crítico não aponta o erro de enquadramento da segunda base, mesmo com o critério escrito nas
instruções dele; os 2 de 3 da versão intermediária não se repetiram e devem ser ruído. Ele nunca aprovou uma entrega em
24 revisões. Com três rodadas por configuração, as diferenças de custo e de tempo entre as três versões também não
permitem conclusão.

## Ajuste à força do modelo: um resultado negativo (14/11/2026)

Um estudo de desenho de harness relata que planejamento aumenta o acerto de modelos fracos e que modelos fortes vão bem
com poucas ferramentas além do shell. Implementamos as duas coisas atrás de `--fit` e medimos com e sem, três rodadas
por braço, intercaladas, nas tarefas `kvstore`, `pipeline`, `refactor` e `tinylang` (12 execuções por modelo e braço).

| modelo (nível) | acerto sem / com | custo total US$ sem / com | passos (mediana) sem / com | tempo mediano sem / com |
|---|---|---|---|---|
| claude-sonnet-5.5 (forte) | 12/12 / 12/12 | 0,95 / 0,93 | 6 / 6 | 21 s / 25 s |
| gpt-6.1-terra (forte) | 12/12 / 12/12 | 0,64 / 0,49 | 12 / 15 | 67 s / 86 s |
| deepseek-v4.1-flash (fraco) | 12/12 / 12/12 | 0,16 / 0,15 | 16 / 28 | 56 s / 114 s |
| lfm-3-1.7b (fraco) | 0/12 / 2/12 | 0,28 / 0,39 | 35 / 44 | 220 s / 267 s |
| nex-n2.5-mini (fraco) | 0/12 / 0/12 | 0,09 / 0,13 | 48 / 61 | 182 s / 407 s |

Leitura: nos modelos fortes, tirar três ferramentas não mudou nada de forma consistente (a queda no total do
gpt-6.1-terra vem de poucas execuções caras no braço sem ajuste; a mediana por tarefa é a mesma). Nos fracos, o plano
custa um passo inteiro a cada atualização, porque eles fazem uma chamada por vez: o modelo que já acertava tudo levou o
dobro do tempo e 2,3 vezes mais tokens de entrada, e dois acertos em 24 contra zero em 24 não bastam para afirmar ganho.
O nex-n2.5-mini não acertou nada em nenhum braço neste dia, embora tenha acertado parte dessas tarefas antes; a causa
não foi investigada. Por isso o ajuste fica desligado por padrão.

Duas explicações prováveis para o achado não se repetir aqui: o Hangar já reduzia ferramentas e forçava uma chamada por
vez para modelo fraco, e o nível "fraco" é definido por preço, o que inclui modelos baratos e capazes.

## Diagnósticos após cada edição (15/11/2026)

Depois de cada `write` ou `edit` o harness confere o arquivo (sintaxe e nomes indefinidos em Python, validade de JSON e
TOML, sintaxe de JavaScript) e devolve o problema no mesmo resultado. Medido com e sem (`--no-diagnostics`), três
rodadas por braço, nas tarefas `kvstore`, `pipeline`, `refactor` e `tinylang` (12 execuções por modelo e braço).

| modelo | acerto sem / com | custo total US$ sem / com | tempo mediano sem / com |
|---|---|---|---|
| claude-haiku-5.5 | 11/12 / 12/12 | 0,102 / 0,104 | 33 s / 32 s |
| gpt-6-luna | 12/12 / 12/12 | 0,038 / 0,049 | 44 s / 55 s |
| deepseek-v4.1-flash | 12/12 / 12/12 | 0,161 / 0,165 | 48 s / 136 s |
| lfm-3-1.7b | 0/12 / 0/12 | 0,067 / 0,110 | 143 s / 220 s |
| nex-n2.5-mini | 2/12 / 1/12 | 0,124 / 0,115 | 409 s / 416 s |
| total | 37/60 / 37/60 | 0,49 / 0,54 | |

Leitura: o acerto não mudou. Os diagnósticos dispararam em 10 das 60 execuções do braço ligado, e todos apontavam um
erro real (um módulo usado sem importar, nomes deixados para trás numa refatoração, dois erros de sintaxe); três foram
em modelos que resolvem tudo, que corrigiram em seguida. O custo total do braço ligado foi 10% maior, o que não dá para
atribuir ao mecanismo: ele só acrescenta texto quando há erro, e foram poucas linhas no experimento inteiro. Estas
tarefas têm teste, então o agente descobre o mesmo erro ao rodá-lo logo depois; o efeito em tarefas sem teste pronto
não foi medido. A terceira rodada do braço desligado foi interrompida e refeita em separado.

Falsos positivos do verificador de nomes: 3 em cerca de 1.200 arquivos da biblioteca padrão do Python (nomes criados
dinamicamente), fora os arquivos de teste que erram de propósito.

## Lições com previsão e resultado (18/11/2026)

Oito rodadas seguidas com a biblioteca de lições ligada, numa biblioteca vazia e isolada: três modelos nas quatro tarefas
difíceis de código, 96 execuções, US$ 0,81. As quatro primeiras rodadas usaram a primeira versão (lição com `signal`,
histórico e aposentadoria); as quatro últimas, a versão publicada, depois de corrigir o que as primeiras mostraram. A
referência sem lições é o braço com diagnósticos da seção anterior.

| Modelo | Sem lições | Primeira versão | Versão publicada |
|---|---|---|---|
| `deepseek/deepseek-v4.1-flash-1017` | 12/12 | 16/16 | 16/16 |
| `openai/gpt-6-luna` | 12/12 | 13/16 | 15/16 |
| `nex-agi/nex-n2.5-mini` | 1/12 | 0/16 | 1/16 |

- **Não há ganho de acerto medido, nem prejuízo.** Na versão publicada, a única falha do `gpt-6-luna` aconteceu na
  rodada 1, antes de existir qualquer lição; com lições ele acertou 12 de 12. Custo por rodada entre US$ 0,09 e 0,13
  nas duas versões.
- **O que a primeira versão errava**: lições chegavam a tarefas sem relação (a de respostas HTTP vazias foi entregue na
  tarefa do interpretador; outra apareceu em 18 sessões) e 4 dos 7 sinais eram genéricos (`file not found`, `[exit 128]`).
  Uma lição sem sinal estava a um uso de ser aposentada só por ter sido mostrada ao modelo que não passa em nada.
- **Na versão publicada**: a lição de testes HTTP só foi entregue na tarefa do servidor; 7 das 8 lições têm sinal, todos
  específicos (`missing required argument(s): path.`). A mais usada foi tentada 32 vezes e o erro voltou 4.
- **O que continua ruim**: o revisor marcou 6 das 8 lições como válidas para qualquer tarefa (o teto de duas por sessão
  segura o efeito); três lições parecidas sobre argumento obrigatório faltando não se fundiram; com seis sessões em
  paralelo os contadores perdem atualizações (uma lição ficou com 6 usos e 9 tentativas).
- **O que não foi medido**: a aposentadoria. Nenhuma lição foi aposentada em oito rodadas; o efeito dela só aparece com
  semanas de acúmulo. A queda de erros de ferramenta do `nex-n2.5-mini` vista nas quatro primeiras rodadas (37, 13, 5, 9)
  não se repetiu nas quatro últimas (24, 36, 22, 17).

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

---

# Parte 5 — Workflows dinâmicos (`run_workflow`), 18/11/2026

Pergunta: dar ao agente uma ferramenta para dividir o trabalho em subagentes melhora o resultado em tarefas com muitos
itens independentes? Dois braços por tarefa: um loop só, e o mesmo loop com `--workflows`. Três rodadas por modelo (uma
para o Sonnet).

## Tarefa `contracts`

24 contratos em texto, cada um com aditivos e revogações; a entrega é um `resumo.json` com três campos vigentes por
contrato. Passa só com 24/24. 21 execuções, US$ 0,39.

| Modelo | Um loop | Com `--workflows` | Usou a ferramenta | Custo médio |
|---|---|---|---|---|
| `gpt-6-luna` | 0/3 (20, 22 e 16 de 24) | 2/3 (24, 23 e 24) | 3 de 3 | US$ 0,007 → 0,014 |
| `deepseek-v4.1-flash` | 3/3 | 3/3 | 1 de 3 | US$ 0,013 → 0,019 |
| `claude-haiku-5.5` | 3/3 | 2/3 | 1 de 3 | a execução que usou: 23/24 e US$ 0,033 |
| `claude-sonnet-5.5` | 1/1 | 1/1 | nunca | sem diferença |

- O `gpt-6-luna` lê contrato por contrato e erra alguns quando faz isso num contexto só; com um subagente por contrato
  acerta. É o único ganho medido.
- `deepseek`, `haiku` e `sonnet` resolvem escrevendo um programa que lê os contratos. Para eles a tarefa é programável,
  e o workflow só acrescenta custo. A única falha do Haiku foi justamente na vez em que usou a ferramenta.
- Sem a instrução no prompt de sistema sobre quando usar a ferramenta, o `gpt-6-luna` não a chamou nenhuma vez.

## Tarefa `audit`

18 módulos com duas funções cada; 10 funções não cumprem a própria docstring. A entrega aponta, por módulo, `ok` ou o
nome da função com defeito. Feita para não ser programável. 20 execuções, US$ 0,15.

| Modelo | Um loop | Com `--workflows` | Usou a ferramenta |
|---|---|---|---|
| `deepseek-v4.1-flash` | 3/3 | 3/3 | nunca |
| `gpt-6-luna` | 2/3 | 3/3 | nunca |
| `claude-haiku-5.5` | 1/3 | 2/3 | nunca |
| `claude-sonnet-5.5` | 1/1 | 1/1 | nunca |

Nenhum modelo chamou `run_workflow`, então os dois braços rodaram a mesma coisa e a diferença entre eles é ruído. Toda
falha foi um único defeito não visto (17/18); não houve falso alarme. A tarefa ficou pequena: os 18 módulos somam cerca
de 8 mil caracteres e cabem com folga num contexto.

## Limites desta parte

- O ganho vem de um modelo, numa tarefa, em três rodadas.
- Não foi medido o caso em que a literatura mostra vantagem para subagentes: material maior que um contexto e que não
  se resolve com script. Texto gerado por regras ou vira programável, ou fica pequeno; uma tarefa assim pede material
  real e gabarito feito à mão.
- Por isso o recurso sai desligado por padrão.
