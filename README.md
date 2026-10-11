# Market Intelligence Engine

Fundação em Python para análise **descritiva, determinística e auditável** de mercados
spot usando OHLCV público da Binance. Etapas 1 e 2: coleta, qualidade de dados,
indicadores, estrutura de mercado, hipóteses Wyckoff, cenários condicionais e CLI.
Sem execução de ordens, credenciais privadas,
previsões de preço ou probabilidades estimadas.

Licença MIT. O repositório permanece privado conforme a criação solicitada; a licença
permite distribuição open source quando o proprietário decidir publicá-lo.

## Instalação

Python 3.11 ou superior. O motor usa apenas a biblioteca padrão.

```bash
git clone https://github.com/aessbyte/market-intelligence-engine.git
cd market-intelligence-engine
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Para desenvolvimento, instalar as ferramentas de verificação:

```bash
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src
```

Os testes usam transporte simulado e não exigem rede. Apenas `test_schema.py` depende
de `jsonschema`, incluído no extra de desenvolvimento. CI executa Python 3.11 e 3.12.

## Uso

```bash
market-intelligence analyze BTCUSDT --snapshot btc-snapshot.json --output btc-analysis.json
market-intelligence analyze ETHUSDT
market-intelligence analyze JUPUSDT --bars 250
market-intelligence analyze BTCUSDT --as-of 2026-10-01T00:00:00Z --snapshot historical.json
market-intelligence replay examples/btc-snapshot.json --output replay.json
market-intelligence analyze BTCUSDT --format text
market-intelligence analyze BTCUSDT --config examples/task02-config.json
market-intelligence replay examples/task02-btc-snapshot.json --format text
```

Também funciona com `python -m market_intelligence`. Sem instalação:
`PYTHONPATH=src python -m market_intelligence replay examples/btc-snapshot.json`.

Símbolos são normalizados para maiúsculas e conferidos em `exchangeInfo`; devem estar
habilitados para spot com status `TRADING`. O cliente consulta H1 (`1h`), H4 (`4h`) e
D1 (`1d`), com 250 candles por intervalo por padrão. `--bars`: de 100 a 5000;
paginação limitada a 1000 por requisição. Histórico curto de um ativo novo gera
resultado degradado, sem preencher candles ausentes.

Endpoint padrão: `https://data-api.binance.vision`, dedicado a dados públicos.
Alternativa explícita: `--base-url https://api.binance.com`. Não há fallback automático
de fonte, de mercado nem para dados simulados. HTTP 403/418/451 e erros de símbolo
encerram a operação aplicável; 429/5xx e erros de conexão têm até duas tentativas
adicionais, com espera limitada e timeout de 15 segundos por chamada.

`--as-of` exige timezone e não pode exceder o horário do servidor Binance. Cada
intervalo usa somente candles cujo fechamento precede esse corte comum. Nenhum
candle aberto, mesmo parcialmente observado, participa da análise.

Saída JSON no stdout (ou `--output`), erros operacionais JSON no stderr:

| Código de saída | Significado |
| --- | --- |
| 0 | Todos os intervalos íntegros; o regime ainda pode ser indeterminado |
| 1 | Erro de entrada, acesso ou envelope do snapshot |
| 2 | Análise degradada: falha, lacuna, histórico insuficiente ou candle inválido |

## Resultado e indicadores

O contrato padrão v2 está em
[`src/market_intelligence/result.schema.json`](src/market_intelligence/result.schema.json).
O resultado contém símbolo, corte temporal, versão do motor e das regras, origem,
hash SHA-256 do snapshot, qualidade por intervalo, indicadores, regime, evidências,
limitações e cenários. Agora inclui estrutura/Wyckoff por intervalo, diário causal
de eventos e concordâncias/conflitos entre D1/H4/H1. Dados simulados têm
`source: simulated` e `simulated: true`.
Um replay preserva a origem declarada pelo snapshot; `source_claim_verified: false`
explicita que o hash **não autentica** a fonte do arquivo fornecido.

| Categoria | Indicadores |
| --- | --- |
| Tendência | SMA20, EMA20/50, distância entre EMAs em ATR, inclinação EMA20 em ATR/candle |
| Momentum | RSI14 de Wilder, eficiência direcional de 20 variações |
| Volatilidade | ATR14, ATR percentual, desvio padrão populacional de 20 log-retornos, bandas de Bollinger 20/2 |
| Volume | Volume atual / média dos 20 candles anteriores, OBV desde o início da janela |

Volatilidade realizada é por candle, **não anualizada**. Volume é em ativo base;
OBV depende do início da janela e não deve ser comparado como nível absoluto entre
janelas diferentes. Volume médio zero resulta em `volume_ratio20: null`. RSI é 50
quando ganhos e perdas são zero, 100 sem perdas e 0 sem ganhos. ATR zero produz
distância e inclinação normalizadas zero.

Regra `regime-v1`, exigindo simultaneamente:

| Regime | Condições |
| --- | --- |
| Alta | fechamento > EMA20; (EMA20−EMA50)/ATR ≥ 0,5; inclinação EMA20 de 5 candles / (5×ATR) ≥ 0,05; RSI14 ≥ 55 |
| Baixa | fechamento < EMA20; distância ≤ −0,5; inclinação ≤ −0,05; RSI14 ≤ 45 |
| Lateralização | distância absoluta < 0,5; inclinação absoluta < 0,05; eficiência20 ≤ 0,3 |
| Indeterminado | nenhuma condição completa, dados inválidos ou intervalos divergentes |

O regime de indicadores existente continua exigindo unanimidade entre H1, H4 e D1.
Ele é separado da nova leitura estrutural. Esses limiares são escolhas
heurísticas documentadas, sem calibração ou alegação de poder preditivo. Os cenários
descrevem teses bullish, bearish e neutral, com evidências favoráveis/contrárias,
gatilhos, níveis e invalidações; `probability` e `price_target` são obrigatoriamente
`null`. Slots futuros de probabilidade calibrada e retorno esperado também são null.

## Estrutura, Wyckoff e cenários — Task 02

Pivôs configuráveis (default 2 candles à esquerda/direita), HH/HL/LH/LL, BOS/CHoCH
por fechamentos, níveis, rompimentos e possíveis falsas rupturas. Cada evento
registra tempo no gráfico, primeira detecção, disponibilidade da revisão,
confirmação/invalidação, evidências e parâmetros. O diário preserva candidatos;
a confirmação à direita não é disponibilizada retroativamente.

Wyckoff: faixa congelada a partir de janela anterior, testes de extremos,
Spring/Upthrust, SOS/SOW e LPS/LPSY com follow-through e filtros de volume/liquidez.
Observações são separadas de interpretações. Acumulação, distribuição,
reacumulação e redistribuição são hipóteses; fases A–E não são declaradas.

D1 contextualiza, H4 mostra desenvolvimento intermediário e H1 detalhes. O motor
registra conflitos sem presumir que D1 esteja certo. Cenários são `active`,
`awaiting_confirmation` ou `invalidated`, com insuficiências explícitas. Nenhuma
pontuação descritiva é convertida em probabilidade.

Fórmulas, operadores e limites completos: [`TASK02_RULES.md`](TASK02_RULES.md).
Auditoria anterior às mudanças: [`AUDIT_TASK02.md`](AUDIT_TASK02.md).
Entrega, verificação e roadmap quantitativo: [`TASK02_REPORT.md`](TASK02_REPORT.md).

### Compatibilidade da Etapa 1

Snapshots v1, comandos e chaves de indicadores/regime foram preservados. O resultado
padrão mudou para schema v2; consumidores que exigem contrato v1 devem usar:

```bash
market-intelligence replay examples/btc-snapshot.json --schema-version 1 --output legacy.json
```

API: `analyze(snapshot, config=None, result_version=2)`; usar `result_version=1`
para resultado legado idêntico. Schema legado: `result-v1.schema.json`.
Regras/indicadores da Etapa 1 não foram recalculados por outra implementação.

## Demonstração com dados reais

[`examples/btc-snapshot.json`](examples/btc-snapshot.json) foi capturado pelo próprio
cliente público em 11/10/2026. [`examples/btc-analysis.json`](examples/btc-analysis.json)
contém o resultado legado v1; [`examples/DEMO.md`](examples/DEMO.md) detalha horário, valores,
hash e reprodução. O snapshot é histórico e não representa uma cotação atual.

A execução integrada v2 está em `examples/task02-btc-*` (snapshot, JSON e texto).
[`examples/TASK02_DEMO.md`](examples/TASK02_DEMO.md) registra o corte e limitações.
`examples/task02-synthetic-*` é uma sequência **simulada**, criada para demonstrar
SOS/LPS. Nenhum de seus preços foi observado na Binance.

## Arquitetura e próximos módulos

Consulte [`ARCHITECTURE.md`](ARCHITECTURE.md), [`AGENTS.md`](AGENTS.md) e
[`VALIDATION.md`](VALIDATION.md). O protocolo `AnalysisModule` recebe candles fechados,
imutáveis e corte temporal explícito. Estrutura e Wyckoff são módulos operacionais
de regras. Smart Money completo, fluxo, previsão probabilística e backtesting
continuam como extensões futuras.

Não há GUI, infraestrutura de negociação, chave de API, modelo treinado ou backtest.
Nenhuma vantagem estatística é declarada. OHLCV de uma única corretora e regras
descritivas não bastam para estabelecer previsões ou desempenho de uma estratégia.
