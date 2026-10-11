# Market Intelligence Engine

Fundação em Python para análise **descritiva, determinística e auditável** de mercados
spot usando OHLCV público da Binance. Etapa 1: coleta, qualidade de dados, indicadores,
regimes, cenários condicionais e CLI. Sem execução de ordens, credenciais privadas,
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

O contrato versionado está em
[`src/market_intelligence/result.schema.json`](src/market_intelligence/result.schema.json).
O resultado contém símbolo, corte temporal, versão do motor e das regras, origem,
hash SHA-256 do snapshot, qualidade por intervalo, indicadores, regime, evidências,
limitações e cenários. Dados simulados têm `source: simulated` e `simulated: true`.
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

Regime agregado exige unanimidade entre H1, H4 e D1. Esses limiares são escolhas
heurísticas documentadas, sem calibração ou alegação de poder preditivo. Os cenários
descrevem condições de persistência/transição e invalidação; `probability` e
`price_target` são obrigatoriamente `null` nesta etapa.

## Demonstração com dados reais

[`examples/btc-snapshot.json`](examples/btc-snapshot.json) foi capturado pelo próprio
cliente público em 11/10/2026. [`examples/btc-analysis.json`](examples/btc-analysis.json)
contém o resultado; [`examples/DEMO.md`](examples/DEMO.md) detalha horário, valores,
hash e reprodução. O snapshot é histórico e não representa uma cotação atual.

## Arquitetura e próximos módulos

Consulte [`ARCHITECTURE.md`](ARCHITECTURE.md), [`AGENTS.md`](AGENTS.md) e
[`VALIDATION.md`](VALIDATION.md). O protocolo `AnalysisModule` recebe candles fechados,
imutáveis e corte temporal explícito. Wyckoff, Smart Money, fluxo, previsão
probabilística e backtesting são extensões futuras, não implementadas nesta etapa.

Não há GUI, infraestrutura de negociação, chave de API, modelo treinado ou backtest.
Nenhuma vantagem estatística é declarada. OHLCV de uma única corretora e regras
descritivas não bastam para estabelecer previsões ou desempenho de uma estratégia.
