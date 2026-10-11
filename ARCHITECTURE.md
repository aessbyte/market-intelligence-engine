# Decisões arquiteturais — Etapas 1 e 2

ADR 001–007 registram a fundação original. ADR 008–010 ampliam essa fundação na
Task 02; os módulos de estrutura/Wyckoff antes futuros agora têm implementação.

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
garantia contra revisões da Binance, calendário de incidentes, cache persistente,
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
