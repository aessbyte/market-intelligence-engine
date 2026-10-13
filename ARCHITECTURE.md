# Decisões arquiteturais — Etapas 1, 2, 3 e integração web

ADR 001–007 registram a fundação original. ADR 008–010 ampliam essa fundação na
Task 02; os módulos de estrutura/Wyckoff antes futuros agora têm implementação.
ADR 011–015 registram o pipeline probabilístico da Task 03, preservando os contratos
descritivos e distinguindo implementação de software de validação preditiva.
ADR 016–019 acrescentam a aplicação web da Task 05. Uma Task 04 separada não foi
localizada na base auditada; essa integração não adiciona validação estatística
retroativa aos modelos existentes.

## Fluxo e limites

```text
CLI → BinanceClient → transporte público GET
                       ↓ snapshot bruto versionado
CLI replay ──────────→ engine.analyze
                         ↓ parse → validação temporal e OHLCV
                         ↓ indicadores causais → classificador determinístico
                         ↓ consenso H1/H4/D1 → resultado JSON versionado
```

`binance.py` concentra rede, disponibilidade do símbolo, horário do servidor,
timeouts e paginação. `validation.py` trata forma dos dados e integridade.
`indicators.py` é matemática pura. `regime.py` contém regras versionadas, evidências
e cenários. `engine.py` transforma um snapshot em um resultado sem rede nem relógio.
`cli.py` é o adaptador de entrada/saída. `models.py` contém estruturas imutáveis e
protocolos tipados. Nenhum módulo de análise pode consultar endpoints privados.

## ADR 001 — Python padrão, tipos e fronteiras JSON

Python ≥3.11, `dataclass(frozen=True)`, enums e protocolos. Sem pandas ou TA libraries
na execução: sementes e fórmulas ficam explícitas, sem diferenças ocultas de bibliotecas.
`Any` fica restrito às fronteiras JSON/transporte; objetos internos são tipados.
`mypy --strict` verifica `src`. `float` é adequado a indicadores descritivos; não serve
como contrato de precisão para ordens, saldo ou contabilidade. Ordens não existem.

## ADR 002 — Dados públicos de spot, uma fonte explícita

Somente `/api/v3/time`, `/api/v3/exchangeInfo` e `/api/v3/klines`, via GET, sem chaves
e sem assinatura. A lista de hosts é fechada e a verificação TLS permanece ativa.
O transporte é injetável para integração offline. Endpoint fica no snapshot.
Retry só para 429, 5xx e falhas de conexão; até 2 retries por padrão, com timeout e
espera limitada a 30 segundos. Banimentos 418 e restrições 403/451 não são contornados.
Retentativas não tornam a coleta atômica; o corte temporal comum evita usar candles
abertos enquanto as três requisições são feitas sequencialmente.

## ADR 003 — Corte temporal, continuidade e fail closed

Um único `as_of_ms` é fixado pelo servidor antes da coleta, ou informado pelo usuário
e limitado ao horário desse servidor. UTC, epoch em milissegundos, intervalos fixos
de 1h, 4h e 1d. EndTime é o último milissegundo anterior ao início do intervalo atual.
A série deve preservar ordem de origem, timestamps únicos/alinhados, continuidade,
fechamento `open+interval−1`, preços positivos e finitos, máxima/mínima consistentes,
volumes/trades não negativos e candle fechado mais recente disponível.

Candles com `close_time_ms >= as_of_ms` são excluídos. Não há ordenação corretiva,
interpolação, preenchimento de gaps ou uso de candle parcial. O intervalo deve ter
exatamente o número solicitado de candles fechados, mínimo 100; disponibilidade
parcial gera diagnóstico, indicadores `null` e regime indeterminado nesse intervalo.
Intervalos válidos ainda são analisados, mas o resultado fica `degraded` e o consenso
global não produz um regime direcional com uma série ausente.

## ADR 004 — Fórmulas reproduzíveis e aquecimento

EMA N: SMA dos primeiros N preços, depois alpha=2/(N+1). RSI14: variações entre
fechamentos, médias iniciais de 14 ganhos/perdas e suavização de Wilder. ATR14: true
range começa no segundo candle porque requer fechamento anterior; mesma suavização.
SMA/Bollinger: 20 últimos fechamentos e desvio populacional, 2 sigmas. Volatilidade:
desvio populacional dos últimos 20 log-retornos, sem anualização. Eficiência20:
deslocamento absoluto em 20 variações dividido pela soma dos deslocamentos absolutos.
OBV: zero no primeiro candle e soma de volumes assinados pela variação do fechamento.
Volume relativo: volume atual sobre os 20 volumes imediatamente anteriores.

Mínimo 100 e padrão 250 são escolhas de aquecimento, não garantia de convergência ao
histórico infinito. Alterar a janela pode alterar médias suavizadas e o regime.
O hash, corte, janela e versão registram esse contexto.

## ADR 005 — Classificação descritiva e consenso conservador

Limiares e operadores exatos estão no README e em `Rules`. Alta/baixa exigem preço,
distância das EMAs, inclinação e RSI concordantes. Lateralização exige EMAs próximas,
inclinação pequena e baixa eficiência direcional. Nenhuma regra completa implica
indeterminado. O consenso global exige três regimes iguais. Evidências incluem
todos os checks, valores observados e limiares, permitindo auditar decisões negativas.
O campo `status` é qualidade operacional; `regime` é classificação descritiva.

## ADR 006 — Snapshot e contrato de resultado

Snapshot v1 guarda rows Binance sem transformação, símbolo, metadados, corte, horário
do servidor, origem, endpoint, janela e erros por intervalo. JSON canônico UTF-8
(chaves ordenadas, sem NaN, sem espaços) define SHA-256. Hash detecta mudanças no
conteúdo; não comprova origem. `source_claim_verified: false` torna isso explícito.
Resultados não incluem horário local variável e são idênticos ao repetir o snapshot.
Mudanças nas regras ou sementes precisam atualizar versão e demonstração.

Snapshots simulados precisam declarar `source: simulated`; não existe fallback de
rede para preços fictícios. Snapshots importados têm origem declarada pelo fornecedor,
não autenticada pelo motor. Dados do exemplo real foram coletados pela CLI deste projeto.

## ADR 007 — Contratos para extensões futuras

`AnalysisModule.analyze(candles, as_of_ms)` recebe tuple imutável de candles validados,
exclusivamente fechados, e devolve resultado próprio versionado. O orquestrador futuro
deverá registrar nome/versão, parâmetros, evidências e limites de cada módulo.

* Wyckoff/Smart Money: padrões precisam separar timestamp do padrão e instante de
  confirmação. Pivôs que exigem candles à direita só ficam disponíveis após confirmação.
* Fluxo: criar um provider separado para trades/livro, com timestamps de evento e de
  disponibilidade. OHLCV e volume não devem ser apresentados como fluxo observado.
* Previsão probabilística: módulo separado, com horizonte, treino, cutoff, versão do
  modelo, distribuição e evidências de calibração fora da amostra. Sem modelo/evidência,
  manter probabilidade ausente/null. Não derivar probabilidade de consenso de indicadores.
* Backtesting: dados point-in-time, eventos de publicação, aquecimento, custos/slippage,
  splits temporais e walk-forward, sem acesso ao futuro. Dados históricos coletados hoje
  não garantem metadados/listagens ou valores publicados na época.

Não há módulos fictícios registrando resultados vazios como se estivessem implementados.

## Limites conhecidos

exchangeInfo descreve disponibilidade **atual**, inclusive em consultas históricas;
ativos retirados podem ser indisponíveis. Não há universo de listagens point-in-time,
garantia contra revisões da Binance, calendário de incidentes,
WebSocket ou agendamento. Prefixos históricos testam causalidade das fórmulas, não
disponibilidade histórica real. Esses limites precisam ser resolvidos antes de afirmar
validade de um backtest ou vantagem estatística.

## ADR 008 — Eventos causais e separação de módulos

`events.py`: evento imutável e transições append-only. `structure.py`: pivôs,
relações e rompimentos. `wyckoff.py`: faixa congelada, observações de preço,
interpretações condicionais e filtros de liquidez. `multitimeframe.py`: concordâncias
e conflitos sem timeframe privilegiado. `scenarios.py`: três teses condicionais.
`config.py`: configuração validada e serializada. `render.py`: apresentação textual.
Não foi criado outro cliente, validator ou calculador de indicadores.

O engine fornece os candles já validados aos módulos puros; módulos também reutilizam
o validator nas chamadas diretas. Nenhum busca rede ou relógio. Estados mutáveis de
faixa/sinal existem apenas dentro de uma execução sequencial; não vazam entre chamadas.
Eventos são dataclasses congeladas; seus dicionários de evidência não são alterados.

O timestamp do gráfico não é a disponibilidade da confirmação. Diário conserva
todas as revisões, enquanto events materializa a revisão atual. Testes de todos
os prefixos verificam igualdade entre diário parcial e diário integral filtrado.
Regras, inclusive empate, buffers, invalidação e liquidez, em TASK02_RULES.md.

## ADR 009 — Contratos e compatibilidade

Motor 0.2.0, resultado padrão schema v2, snapshot permanece v1. Chaves de
indicadores/regime v1 preservadas. Novos campos structure/wyckoff por intervalo,
multitimeframe global e três cenários. `result_version=1`/`--schema-version 1`
reproduzem exatamente o resultado original, inclusive versão legada 0.1.0 e
cenários antigos. `result-v1.schema.json` conserva o contrato anterior.

Schema v2 obriga campos auditáveis e proíbe probabilidade/alvo/retorno inventados.
Não há campo de score disfarçado de probabilidade. Configuration registra todos
os limiares; versões desconhecidas de regra são rejeitadas. Fonte e hash do snapshot
continuam explícitos; JSON importado não é autenticado pelo hash.

## ADR 010 — Cenários e limites do modelo de regras

Regime por indicadores e estrutura são leituras separadas. D1/H4/H1 recebem papéis
contextuais, sem assumir que o maior está correto. Cenário ativo significa condições
operacionais satisfeitas; não estimativa de retorno. Evidência contrária permanece
visível, e invalidações têm níveis ou condições verificáveis. Sem dados íntegros e
liquidez recente suficiente, cenário fica aguardando confirmação.

Faixas são candidatas de OHLCV, não identificação de inventário institucional.
Hipóteses Wyckoff nunca atribuem fase A–E. A versão atual não reconstrói ordem intrabar,
livro/fluxo, nested ranges, microestrutura ou confirmação intercorretoras. Retestes
direcionais têm uma emissão por tipo/faixa. Isso deve ser validado e ampliado antes
de treinar modelos quantitativos sobre os eventos.

## ADR 011 — Dataset histórico persistente e população explícita

`prediction/dataset.py` reutiliza BinanceClient e validation; não cria outro
provider. Armazena rows originais, Binance/spot/símbolo/D1/UTC, endpoint, corte do
servidor, qualidade, histórico curto e versões/hashes. Dataset salvo é a unidade
reproduzível de treinamento. A primeira população é um ativo spot em D1; snapshots
H1/H4 curtos não viram histórico multitemporal fictício.

Invalidade impede treino. Recorte explícito pode selecionar um período contíguo,
com início UTC, justificativa, hash e qualidade do pai. Não há reparo, preenchimento
ou substituição por simulação. No exemplo BTC, o timestamp inválido de 08/02/2018
levou à seleção desde 09/02/2018, antes da modelagem. O pai permanece no registro de
auditoria. SHA-256 garante igualdade do conteúdo, sem autenticar origem/revisões.

## ADR 012 — Features por disponibilidade e alvos separados

`prediction/features.py` gera 65 features D1 com fonte e disponibilidade por scalar.
Indicadores mantêm matemática/sementes existentes, em janela de até 250 candles;
estrutura e Wyckoff preservam contexto integral do dataset. O consumo do diário
sequencial usa somente revisões já disponíveis. Pivôs confirmados não retroagem;
estado final de um evento futuro não é uma feature histórica. Zero para ausência
tem indicador correspondente, evitando confundir falta de evidência com observação.

`prediction/targets.py` cria alvos 7/30/90 dias com endpoint UTC exato, retorno final,
limiar de volatilidade conhecido na origem e disponibilidade do alvo. Excursões
máximas usam apenas candles futuros e ficam separadas das entradas. Constantes de
classes são predefinidas na configuração; teste não escolhe limiares. O dataset não
comprova latência histórica: disponibilidade close+1ms é convenção declarada.

## ADR 013 — Fronteiras cronológicas e modelo final congelado

`prediction/validation.py` define treino expansivo, validação, calibração e teste
por tempo, sem shuffle. Em cada fronteira remove alvos que alcancem a próxima
origem; embargo é configurável. Testes de folds distintos também purgam alvos
atravessando o fim nominal do holdout. Features podem ler passado conhecido, mas
scaler ajusta apenas treino e calibração só usa seu bloco reservado.

`prediction/training.py` fixa candidatos/hiperparâmetros antes da avaliação e
seleciona por Brier/log loss da validação, com desempate por simplicidade. O último
fold emitido é o holdout final. Seu modelo fica congelado antes dos resultados e
não é retreinado ao final. Um fold futuro pode incorporar alvos de holdout antigo
após sua disponibilidade, sem fazer tuning automático pelas métricas observadas.
O relatório diferencia estratégia de seleção entre folds e modelo final congelado.

## ADR 014 — Treinamento opcional, inferência JSON e métricas auditáveis

`prediction/models.py` compara frequências, momentum, logística multinomial e
gradient boosting condicionado à quantidade de treino. NumPy/SciPy/scikit-learn
ficam no extra predictive, com versões fixadas. Inferência calcula softmax, árvores
e temperatura a partir de parâmetros JSON validados, sem pickle ou execução de
código carregado do artefato. O pacote descritivo continua sem dependências runtime.

`prediction/metrics.py` registra Brier multiclass, log loss, acurácia separada, bins
de calibração, ECE, comparações pareadas em origens espaçadas pelo horizonte e
bootstrap com seed. Modelos com folds ausentes carregam referência nos mesmos
folds; médias de populações diferentes não são comparação justa. Intervalos vêm
de mistura empírica de retornos normalizados pela volatilidade, ajustada no treino,
com cobertura medida fora da amostra. Não sobreposição não prova independência.

## ADR 015 — Abstinência, compatibilidade e API sem treinamento implícito

`prediction/inference.py` devolve probabilidades/retornos públicos somente quando
a política de validação e qualidade é satisfeita. Histórico/população insuficientes,
calibração fraca, falta de melhoria contra baseline, poucos holdouts independentes,
drift, regime raro e dados incompatíveis produzem abstinência. Diagnósticos numéricos
experimentais têm rótulo próprio; nunca preenchem campos públicos ausentes.

Engine 0.3.0 preserva resultado padrão v2 e replay legado v1. V3 explícito integra
predições sem recalcular treinamento: `analyze(snapshot, config=None,
result_version=3, prediction_bundle=bundle, prediction_dataset=dataset)`. O histórico
de features deve começar no contexto original e preservar hash dos candles usados
na criação do bundle. Recorte curto ou revisão desse histórico impede inferência.
CLI dataset/train/predict separa coleta, modelagem e uso; JSON é consumível por API
web futura, sem fitting no navegador.

`prediction_origin_ms` identifica referência no último fechamento diário;
`as_of_ms` identifica corte da emissão/análise. Disponibilidade informacional do
bundle inclui dados e alvos de avaliação. Instante real da produção é registrado
separadamente no registro operacional; não se alega emissão histórica antes do
treinamento efetivo. Registry com carimbo de criação/verificação criptográfica ainda
precisa ser desenvolvido. Classes de retorno não são os cenários de regras, que
mantêm probabilidades null. Nenhuma camada autoriza negociação automática.

## ADR 016 — Adaptadores web separados do motor

FastAPI/Pydantic em `web/` é um extra opcional; não substitui CLI, transporte,
regras ou inferência. `AnalysisService` chama `engine.analyze(..., result_version=3)`
com snapshot e artefatos explícitos. React/TypeScript/Vite fica em `frontend/`.
O resultado padrão da CLI permanece v2 e o replay legado v1 permanece disponível.

```text
React/TypeScript → POST /api/v1/analyses → job transitório
                       ↓ provider BinanceClient ou replay explícito
                       ↓ snapshot fechado + histórico/modelo previamente carregado
                  engine.analyze v3, sem rede e sem fitting
                       ↓ validação JSON Schema original
                  adaptador de apresentação → contrato web Pydantic
                       ↓ validação Zod no navegador
                  dashboard + Lightweight Charts
```

Não há banco de dados, serviço externo de IA, treinamento HTTP ou endpoint de
ordens. O adaptador calcula séries gráficas com `indicators.ema` e `calculate`
existentes, preservando sementes e fórmulas. O navegador formata valores e desenha;
não escolhe regime, cenário, calibração ou elegibilidade.

## ADR 017 — Contrato versionado, jobs e retenção limitada

API em `/api/v1`, schemas Pydantic e OpenAPI. A resposta web contém resultado
analítico, OHLCV, séries de indicadores, eventos, níveis, proveniência, metadados
de mercado, qualidade do modelo e cache. A projeção compacta omite somente diários
duplicados e histórico de tendência da resposta principal. O JSON v3 integral,
incluindo `event_journal`, é acessível em `/analyses/{id}/engine`.

Análise é POST assíncrono com ID, polling de job e etapas realmente executadas:
validação, coleta, análise e preparação. Não se inventam percentuais de progresso.
Dois threads de execução e fila de oito pendências evitam bloquear o servidor de
consultas. IDs e resultados são transitórios; reiniciar o processo os remove.

Cache de análise por modo, símbolo, janela e assinatura de artefatos: 30 segundos.
Resultados/job concluídos têm retenção de 20 minutos, no máximo 16 registros;
o JSON retido tem orçamento de 64 MiB e descarte LRU. Isso limita o material
serializado persistido em memória, não representa um limite de RSS. Diretório de
símbolos usa cache de cinco minutos. Histórico D1 para inferência é reutilizado
por origem diária. Artefatos são carregados e validados na inicialização; trocar
modelo/dataset exige reiniciar o serviço, invalidando cache e jobs.

## ADR 018 — Causalidade e honestidade na apresentação

Lightweight Charts mostra H1/H4/D1 recebidos do backend. W1 não é agregado no
navegador e futuros não são tratados como spot. Metadados de ativo base/cotação
e tick vêm de `exchangeInfo`; a ausência de mercado não consultado permanece
desconhecida. Preço de referência e variação usam o último candle H1 fechado,
não um ticker instantâneo ou variação de 24 horas.

Marcadores usam o candle associado à disponibilidade da confirmação/invalidação
ou candidatura; a coordenada vertical e o inspetor preservam o preço do evento.
Rótulos curtos e densidade adaptativa reduzem sobreposição sem remover registros. Linhas de níveis
começam quando ficam conhecidas. A origem histórica fica desativada por padrão e,
quando habilitada, é explicitamente retrospectiva. O inspetor separa posição
histórica, primeira detecção, confirmação, invalidação e disponibilidade da revisão.

Probabilidade/retorno públicos `null` aparecem como indisponíveis, nunca zero ou
50%. Diagnósticos experimentais exigem expansão e rótulo de pesquisa; os gates
estatísticos existentes continuam valendo. Métricas OOS agregadas, teste final,
calibração, cobertura e baseline na mesma população são distintos. Cenários
condicionais não se tornam classes estatísticas nem trajetórias futuras. A síntese
textual é composição direta de observações e estados estruturados, sem LLM.

## ADR 019 — Execução web, segurança e mobile

Build estático servido pelo mesmo FastAPI evita um segundo serviço em produção.
Vite usa proxy local em desenvolvimento. CORS aceita origens explícitas e não
usa credenciais; nenhum segredo ou chave Binance é enviado ao navegador. A API
valida símbolos/parâmetros, limita corpo a 8 KiB antes do parsing, mantém timeout
de recebimento e orçamento da consulta, aplica limites por cliente e emite logs
JSON com request IDs. Diretório estático é contido no build configurado.

O deployment inicial usa um processo API; jobs/cache/rate limits não são
distribuídos. HTTPS em proxy frontal é o caminho de publicação e uso Android;
não é necessário Termux. Layout adapta de 360 px a desktop, tabs preservam o
resultado, teclado tem foco visível e tabelas rolam dentro do painel.

Manifest e ícones preparam instalação PWA em navegadores compatíveis. Sem service
worker de dados/API, a aplicação não oferece análises offline nem reutiliza
cotação arquivada como atual. Replay é configuração explícita de servidor,
identificada com corte histórico. Falha Binance não ativa exemplos ou simulação.
