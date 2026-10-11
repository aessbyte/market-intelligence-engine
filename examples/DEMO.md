# Demonstração real — BTCUSDT

Coleta realizada pela CLI deste projeto no endpoint público
`https://data-api.binance.vision`, em **2026-10-11T17:49:33.788Z**
(horário do servidor/corte, `as_of_ms=1791740973788`). Não são dados simulados.
Foram observados 250 candles fechados em cada intervalo, sem lacunas, duplicatas,
erros de timestamps ou inconsistências OHLCV na janela retornada.

| Intervalo | Último fechamento | RSI14 | ATR14 | Regime |
| --- | ---: | ---: | ---: | --- |
| H1 | 83916,01 | 74,8025 | 212,5200 | alta |
| H4 | 83908,89 | 58,1688 | 582,0408 | indeterminado |
| D1 | 82988,36 | 51,7041 | 2116,3702 | indeterminado |

Preços e ATR em USDT. Os fechamentos diferem porque cada intervalo encerra em um
horário diferente. Últimos candles usados: H1 até 16:59:59.999Z, H4 até
15:59:59.999Z, D1 até 2026-10-10T23:59:59.999Z.

Resultado geral: **indeterminado**, status operacional **ok**. H1 satisfez as
quatro regras de alta. H4 não teve alinhamento entre distância das EMAs e momentum;
D1 não satisfez preço, inclinação e RSI para alta. Nenhum consenso foi forçado.

Snapshot canônico SHA-256:
`3a9baa1f9163f6178d1d396b72577ab7f68619d31a43fbe8c0cfd6cefe01eca0`.

## Reprodução offline

```bash
market-intelligence replay examples/btc-snapshot.json --output /tmp/replay.json
python -c 'import json; assert json.load(open("/tmp/replay.json")) == json.load(open("examples/btc-analysis.json"))'
```

O snapshot preserva as rows brutas retornadas, a disponibilidade atual do símbolo,
origem declarada, endpoint, corte e janela. O resultado completo contém os indicadores
sem arredondamento, limiares e checks individuais. O hash comprova igualdade do
conteúdo, não autenticidade criptográfica da fonte. A demonstração não é previsão,
backtest ou cotação atual. Os cenários têm probabilidade e alvo de preço `null`.

Uma coleta nova pode produzir resultado diferente:

```bash
market-intelligence analyze BTCUSDT --snapshot new-snapshot.json --output new-analysis.json
```
