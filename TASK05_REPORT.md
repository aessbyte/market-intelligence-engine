# Task 05 — Interface web e integração do motor

Execução: 12/10/2026 UTC; publicação: 13/10/2026 UTC. Base inspecionada:
`fcf7118437676c48f1f004cad75106ad07e46aa7`.

## Escopo e estado inicial

A base continha o motor Python 0.3.0, CLI, schemas v1/v2/v3, exemplos reais e
sintéticos, datasets/modelos JSON e relatórios das Tasks 02/03. Não havia frontend
ou servidor HTTP. Os **157 testes existentes passaram antes da implementação**.
README, ARCHITECTURE, AGENTS, documentação, interfaces e contratos foram lidos;
o registro dessa inspeção está em `AUDIT_TASK05.md`.

Uma Task 04 separada **não foi localizada na base local nem no histórico GitHub
inspecionado**. As auditorias incluídas na Task 03 não autorizam declarar essa
etapa adicional concluída. A integração usa as capacidades efetivamente existentes
e preserva suas limitações estatísticas.

O trabalho acrescenta apresentação e coordenação HTTP, sem reconstruir o motor,
alterar indicadores, suavizar estados de validação, treinar modelos por consulta
ou implementar operações Binance. A autorização da Task 05 atualiza a restrição
de GUI das etapas anteriores; as regras de dados e causalidade permanecem.

## Componentes implementados

| Área | Implementação e responsabilidade |
| --- | --- |
| API | FastAPI/Pydantic em `src/market_intelligence/web`, endpoints `/api/v1`, OpenAPI em `/docs` |
| Serviço | Jobs transitórios, etapas efetivas, cache limitado, coleta pública e coordenação do motor |
| Adaptador | Projeção do resultado v3 e séries calculadas pelas funções de indicadores existentes |
| Frontend | React 19, TypeScript, Vite, contratos Zod, componentes reutilizáveis e tema escuro/claro |
| Gráfico | Lightweight Charts, OHLCV, volume, EMA20/50, RSI14, níveis e eventos causais |
| Painéis | Visão geral, Gráfico, Estrutura, Wyckoff, Previsões e Auditoria |
| Execução | Scripts `start-web.sh` e `start-web-example.sh`, build estático e proxy de desenvolvimento |
| Documentação | `docs/WEB.md`, decisões ADR 016–019 em ARCHITECTURE, instruções e CI atualizadas |

O extra Python `web` mantém a instalação CLI independente. Não foram introduzidos
banco de dados, fila externa, provedor de IA ou serviço de treinamento. A licença
MIT permanece; atribuição e avisos da biblioteca gráfica estão documentados em
`frontend/THIRD_PARTY_NOTICES.md`.

O usuário informa somente o símbolo. O backend normaliza e valida o par, coleta
candles fechados, executa `engine.analyze(..., result_version=3)` e retorna o
resultado. O navegador acompanha `queued/running/completed/failed` e as etapas
`validating/fetching/analyzing/preparing`; a resposta aparece sem recarregar a
página. Trocar abas preserva a análise e não provoca novo fitting.

O mercado suportado é **Binance spot**, nos intervalos **H1/H4/D1**. Futuros ficam
explicitamente não suportados, com disponibilidade `null/NOT_CHECKED`; a API não
afirma que o símbolo inexiste em futuros. W1 está desabilitado e retorna erro
quando solicitado. Nenhuma série spot é usada como substituta de futuros ou W1.

## Contratos e integridade da apresentação

Pydantic valida entrada e envelope web; o JSON Schema v3 valida o resultado
analítico; Zod verifica o contrato recebido no navegador, incluindo números
finitos, soma de probabilidades, dados OHLC consistentes, ordenação temporal,
candles fechados e ausência de eventos posteriores ao corte.

A resposta compacta omite diários duplicados e histórico de tendência, mantendo
os valores, evidências e estados atuais. O endpoint `/engine` preserva o JSON v3
integral, incluindo os diários append-only. Exportar JSON na interface salva o
contrato web completo; o contrato não modifica as métricas do motor.

O resumo apresenta o **fechamento do último H1**, não ticker instantâneo. A
variação compara dois fechamentos H1, não uma janela de 24 horas; o volume é do
ativo base no último H1, e a volatilidade é ATR percentual H1. Esses critérios
aparecem na interface e no contrato. Qualidade operacional `ok` não significa
elegibilidade preditiva.

As respostas com histórico insuficiente mantêm `degraded`, indicadores ausentes,
estrutura indisponível e explicações. Falhas não ativam dados sintéticos. Uma
análise anterior pode permanecer na tela após falha de nova consulta, mas recebe
aviso explícito e conserva o símbolo e timestamp anteriores.

## Causalidade dos gráficos

Os timestamps e preços dos overlays vêm do motor. Cada evento preserva posição
histórica, primeira detecção, confirmação/invalidação e disponibilidade da
revisão. O marcador padrão aparece no candle **após cujo fechamento** seu estado
se tornou conhecido; o inspetor apresenta as datas separadamente.

Os níveis começam na disponibilidade registrada. As origens históricas ficam
desligadas por padrão e, quando habilitadas, são identificadas como retrospectivas.
Não se desenha uma confirmação futura como sinal disponível no candle do pivô.
Grupos de médias, volume, estrutura, Wyckoff, níveis, RSI, estados provisórios e
origens podem ser alternados. Zoom, pan, crosshair, inspeção de eventos e tabelas
de dados fornecem formas complementares de leitura.

As confirmações Wyckoff são confirmações de regras operacionais, não comprovação
de inventário institucional ou fases A–E. Acumulação/distribuição permanecem
hipóteses. Cenários condicionais mantêm evidências favoráveis/contrárias, gatilhos
e invalidações do backend.

## Previsões e transparência estatística

Horizontes de 7/30/90 dias mostram a classificação de elegibilidade, origem,
versões, limites e razões de abstinência. Probabilidades públicas e distribuição
de retornos `null` continuam indisponíveis; não são substituídas por 0%, 50% ou
percentuais decorativos. Diagnósticos experimentais ficam em expansão separada,
com identificação de pesquisa não validada.

Não há fan chart ou trajetória fabricada a partir de quantis finais. Quando o
backend disponibiliza distribuição elegível, são apresentados mediana, quantis e
intervalo de retorno final, sem tratá-los como suporte/resistência ou preço
garantido. Os cenários condicionais ficam separados das classes estatísticas de
retorno.

A aba Auditoria mostra modelo/dataset, períodos de treino e teste final,
observações, Brier, log loss, ECE, tabelas de calibração, cobertura e comparação
com baselines. A estratégia walk-forward agregada e o modelo congelado no teste
final são populações distintas e recebem rótulos próprios.

As métricas abaixo vêm do artefato **já existente**
`model-3703fd3ae9432487`, com 3.166 candles reais BTCUSDT de 09/02/2018 a
10/10/2026. Não representam novo treinamento ou validação preditiva na Task 05.

| Horizonte | Observações OOS | Brier frequências | Brier logística | Log loss frequências | Log loss logística |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7 dias | 1.914 | 0,649155 | 0,727384 | 1,073335 | 1,196864 |
| 30 dias | 1.776 | 0,655210 | 1,000880 | 1,080654 | 3,774897 |
| 90 dias | 1.375 | 0,660741 | 1,198783 | 1,090114 | 6,449640 |

Brier usa soma sobre três classes, escala 0–2; valores menores são melhores.
Essas observações temporais têm horizontes sobrepostos e não equivalem ao mesmo
número de testes independentes.

Gradient boosting foi avaliado somente nos folds com histórico suficiente:

| Horizonte | Observações/folds | Brier boosting | Brier baseline na mesma população |
| --- | --- | ---: | ---: |
| 7 dias | 840 / folds 3–5 | 0,651225 | 0,658083 |
| 30 dias | 771 / folds 3–5 | 0,617689 | 0,653853 |
| 90 dias | 550 / folds 3–4 | 0,977047 | 0,715280 |

As melhorias pontuais em alguns blocos não estabelecem vantagem sustentada.
Comparar diretamente esses valores com a baseline agregada de todos os folds
mistura populações; o dashboard expõe a referência comparável.

Na estratégia walk-forward selecionada, a cobertura OOS dos intervalos nominais
de 80% foi **81,77% / 62,33% / 69,96%** em 7/30/90 dias. A cobertura de 30 dias
ficou abaixo do piso de 65% definido no motor. A calibração, o número de testes
independentes e a comparação final não sustentam publicar esses modelos como
previsores validados. O relatório integral permanece em `TASK03_REPORT.md`.

## Consulta real executada

O serviço live consultou a API pública Binance para **BTCUSDT spot** e concluiu
uma análise com corte **12/10/2026 23:42:22.830 UTC**
(`as_of_ms=1791848542830`). Preço de referência: **82.157,66 USDT**, correspondente
ao fechamento H1, com qualidade `ok` e dados H1/H4/D1.

Com o bundle previamente treinado configurado, a resposta atual retornou:

| Horizonte | Status da consulta real | Probabilidade pública | Magnitude pública |
| --- | --- | --- | --- |
| 7 dias | `UNVALIDATED_MODEL` | `null` | `null` |
| 30 dias | `UNVALIDATED_MODEL` | `null` | `null` |
| 90 dias | `INSUFFICIENT_EVIDENCE` | `null` | `null` |

O status registrado no artefato e a elegibilidade de uma consulta atual podem
diferir: o motor aplica também gates de disponibilidade, liquidez, histórico,
regime e distribuição das features na inferência. O painel conserva essa
distinção. A consulta HTTP real comprova coleta e integração do serviço; não
comprova vantagem preditiva.

O fluxo real no navegador foi executado nos seis painéis em desktop 1440 × 1000
e em viewport Android 360 × 800 com toque emulado. Houve **zero erros JavaScript**;
as larguras do documento coincidiram com o viewport (1440 e 360), sem overflow da
página. Foram capturadas 14 imagens; quatro capturas selecionadas são versionadas:

* [Visão geral desktop](examples/task05/real-binance-desktop-overview.png)
* [Visão geral mobile](examples/task05/real-binance-mobile-overview.png)
* [Previsões mobile](examples/task05/real-binance-mobile-forecasts.png)
* [Auditoria desktop](examples/task05/real-binance-desktop-audit.png)

Registro de execução: `examples/task05/live-browser-run.json`; resposta integral
web real: `examples/task05/live-web-analysis.json`. A captura final ocorreu em
12/10/2026 23:42:42 UTC. Os dois dispositivos receberam o mesmo resultado
`5de00e82fbacd4feaacf44ec`, preservado pelo cache. O teste mobile é emulação de
viewport/toque, não ensaio em telefone físico. O script `capture-web-demo.cjs`
automatiza esse fluxo sem interceptar requisições ou fornecer fixtures.

## Segurança e operação

O adaptador usa apenas os endpoints públicos allowlisted do provider existente.
Não pede chaves, não oferece ordens e não expõe treino ou execução de código.
Bundle/dataset são paths configurados no processo, JSON não executável, validados
por contrato/checksum e limitados a 25 MiB por arquivo. Um modelo BTC não é
aplicado a outro símbolo. Histórico atualizado precisa preservar a coorte e o
checksum do contexto de treinamento.

O processo tem dois workers e oito pendências. Há rate limits em memória de 30
submissões e 180 leituras API por minuto/cliente. Corpos de escrita são limitados
a **8 KiB antes do parser**, por Content-Length e pelos chunks recebidos;
recebimento tem timeout de 15 s. O orçamento de consulta é 90 s e cada GET
upstream web usa até 8 s, sem retries implícitos.

O cache de análise dura 30 s e conserva o timestamp original; diretório spot
usa cinco minutos e histórico preditivo cache por origem diária. Resultados
finalizados são retidos até 20 min, sujeitos a **16 registros** e **64 MiB de JSON
serializado** com descarte LRU. A retenção usa strings JSON imutáveis, evitando
manter simultaneamente grandes árvores Python. O orçamento não constitui limite
rígido de RSS: modelos/datasets, processamento e respostas também ocupam memória.

CORS aceita origens explícitas sem credentials; SPA/API podem ser servidas na
mesma origem. API retorna `Cache-Control: no-store`, request IDs e headers contra
sniffing/framing. Logs estruturados registram etapa, status, código e duração,
sem snapshots completos ou segredos. O servidor local inicia em `127.0.0.1`.
Paths estáticos são resolvidos e precisam permanecer dentro do build configurado.

## Defeitos encontrados e corrigidos durante a integração

* O link frontend OpenAPI apontava para uma rota inexistente; passou a `/docs`,
  com proxy Vite correspondente.
* A cobertura de intervalos era lida como número, embora o backend retornasse
  objeto; agora o valor real `.coverage` é exibido, sem recalcular a métrica.
* Probabilidades experimentais nullable passaram a ter proteção de renderização.
* O contrato frontend foi alinhado ao `tick_size` numérico real do backend.
* A largura do seletor Spot e a densidade de anotações foram ajustadas a 360 px;
  todos os eventos continuam disponíveis no inspetor.
* Dois seletores E2E amplos encontravam uma opção oculta de futuros. As asserções
  passaram a verificar mensagens específicas dentro do painel ativo.
* Corpos HTTP grandes eram parseados antes da validação de tamanho; foi adicionado
  middleware ASGI limitado, com testes de Content-Length e streaming.
* A retenção original de 128 árvores analíticas podia manter aproximadamente
  1,38 GB para registros comparáveis ao exemplo real BTC/250 candles; foi
  substituída por armazenamento JSON com orçamento de bytes e LRU.
* Respostas sem nenhum intervalo por falha da fonte retornam erro explícito,
  sem apresentar um dashboard vazio como consulta bem-sucedida.

## Testes executados e evidências

| Verificação | Resultado disponível nesta redação |
| --- | --- |
| Baseline anterior | 157 testes Python passaram antes da integração |
| Suíte Python integrada | **188 passaram**, incluindo os anteriores |
| Componentes/contratos/helpers frontend | **40 testes Vitest passaram** |
| TypeScript e build Vite | Passaram |
| Ruff lint | Passou |
| Ruff formatação | Passou, 57 arquivos já formatados |
| mypy strict | Passou, 34 arquivos fonte |
| Playwright desktop e Android 360 px | **30 passaram**, 15 desktop + 15 Android emulado; 1,2 min |
| Consulta real Binance via API | Passou, BTCUSDT live descrito acima |
| Screenshots reais e demonstração visual | Passaram, seis painéis; 14 capturas realizadas, quatro selecionadas versionadas |

Os testes de software cobrem parâmetros/símbolos inválidos, contratos, erro de
fonte, histórico insuficiente, ausência de probabilidades, cache/capacidade,
corpos HTTP excessivos, CORS, traversal, estado/causalidade de eventos e igualdade
dos valores analíticos apresentados com o resultado original.

O harness `scripts/test_web_server.py` usa provider sintético explicitamente
rotulado. Ele permite verificar fluxo completo, falhas e falta de histórico de
forma determinística, sem alegar consulta real Binance. Screenshots desses testes
devem conservar o prefixo `synthetic-`; não substituem a demonstração live.

Os testes de navegador executados incluem abas, navegação por teclado, preservação
da análise, interações/overlays H1/H4/D1, telas de 360 px, alvos de toque e
contenção de rolagem horizontal. A primeira execução remota sofreu encerramento
por memória; isso é uma falha de execução registrada, não um resultado aprovado.
A primeira execução estática completou 26 casos, com quatro falhas causadas por
seletores que encontravam uma opção oculta. Após corrigir as asserções específicas,
a suíte inteira passou: **30/30**. O build final e os 40 testes Vitest também
passaram. Ruff lint/formatação e mypy strict foram novamente verificados.

## Como abrir a aplicação

Na raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
cd frontend
npm ci
npm run build
cd ..
bash scripts/start-web.sh
```

Abra **http://127.0.0.1:8000**. Para a captura histórica real e o modelo salvo,
use `bash scripts/start-web-example.sh`; o banner de replay é obrigatório e
permanece visível. Para desenvolvimento com Vite, use os dois terminais descritos
em `docs/WEB.md` e abra **http://localhost:5173**.

Em Android na mesma rede, execute
`MIE_HOST=0.0.0.0 MIE_PORT=8000 bash scripts/start-web.sh` e abra
`http://IP-DO-COMPUTADOR:8000` no telefone. O Android não precisa de Termux nem de
Python; o servidor roda no computador/host. A URL `127.0.0.1` do telefone não
aponta para o computador.

## Limitações e próximos passos

1. Localizar ou executar formalmente a Task 04, sem tomar seus resultados como
   conhecidos; continuar a validação prospectiva e multiativo antes de qualquer
   alegação de vantagem estatística.
2. Implementar providers/regras auditados para futuros e W1 antes de habilitar
   essas escolhas na interface. Não inferir dados inexistentes.
3. Aumentar suporte independente de calibração/teste, avaliar drift e cobertura,
   mantendo abstinência quando a evidência for insuficiente.
4. Para deploy, servir HTTPS com proxy frontal, build estático e artefatos
   configurados. Não publicar Vite como servidor de produção. Autorização de
   acesso pode ser adicionada no proxy conforme o uso; a instância atual não
   inclui autenticação de usuários.
5. Jobs, cache, rate limits e registry são locais ao processo. Vários hosts ou
   workers exigem coordenação/persistência compartilhada, ainda não implementada.
6. Manifest e ícones preparam uso standalone/PWA. Não há service worker nem
   promessa de uso offline; elegibilidade de instalação depende do navegador e
   HTTPS. Dados/API não ficam armazenados como se fossem consultas atuais.
7. O dashboard não faz streaming ou atualização automática de preço. Nova coleta
   requer nova análise após expiração do cache. Status e timestamps devem ser
   consultados antes do uso.

## Arquivos e publicação

* `src/market_intelligence/web/`: oito módulos novos de API, contratos, serviço,
  adaptador, limites HTTP, configuração e inicialização.
* `frontend/`: aplicação tipada, componentes, gráfico, contratos, testes,
  configuração e lockfile; nenhum resultado de produção vem das fixtures de teste.
* `tests/test_web_api.py` e `tests/test_web_contract.py`: 31 novos testes Python.
* `scripts/`: inicialização live/replay, servidor sintético E2E e captura real.
* README, ARCHITECTURE, AGENTS, `docs/WEB.md`, `AUDIT_TASK05.md`, este relatório e
  CI: execução, decisões, segurança e verificações.
* `examples/task05/`: resposta real, registro do navegador e screenshots selecionados.

A comparação Git blob dos 89 arquivos da base confirmou que nenhum módulo
analítico, teste anterior ou exemplo anterior foi modificado. Somente seis
arquivos existentes de documentação/configuração/CI mudaram; os demais módulos
web são novos. A versão
do motor continua 0.3.0, preservando replays existentes; frontend 0.5.0 e API v1
possuem seus próprios contratos. Os hashes de publicação e conferência de arquivos
serão registrados em `TASK05_DELIVERY.md`.
