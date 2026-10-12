# Task 02 — Exemplos real e simulado

## Execução real de BTCUSDT

Coleta pública pelo cliente do projeto, `https://data-api.binance.vision`, sem
credenciais, com cutoff do servidor **2026-10-11T18:33:48.435Z**
(`as_of_ms=1791743628435`). 250 candles fechados por intervalo; 750 no total.
Todos passaram nas validações da Etapa 1.

Snapshot canônico SHA-256:
`a8a150a4921a2a3af36cb4481bcec6e6e707be9c472996275518cf66422c292e`.
Resultado JSON canônico SHA-256:
`f961b946c04184e43126c7879929bbd88b30b3f2f0703295a93be00b96d2ef2c`.

Na auditoria Task 03, corrigidos IDs de falsas rupturas que colidiam no mesmo
candle e ocultavam observações distintas. O JSON/texto foram regenerados com a
correção; tendências e estados dos cenários descritos abaixo são preservados.
O hash anterior, do commit Task 02, era
`526c0f7dcf6cf0ff30749003676eee91a34b24cfb18aba5b3f250f7b16c7fc7e`.

| Leitura | D1 | H4 | H1 |
| --- | --- | --- | --- |
| Estrutura | baixa | lateralização | lateralização |

Regime agregado dos indicadores: indeterminado. Consenso estrutural: indeterminado.
Conflitos D1/H4 e D1/H1 foram preservados. Cenários no corte: bullish aguardando
confirmação; bearish invalidado; neutral ativo. Neutral não elimina o contexto
baixista D1: satisfaz a regra de faixas em dois intervalos e registra evidências contrárias.
Não se atribuiu probabilidade, alvo, retorno esperado ou fase Wyckoff.

Arquivos: `task02-btc-snapshot.json` (rows brutas), `task02-btc-analysis.json`
(diário completo/evidências) e `task02-btc-analysis.txt` (leitura textual).
Replay local produziu o mesmo resultado canônico da execução conectada.

```bash
market-intelligence replay examples/task02-btc-snapshot.json --output /tmp/task02.json
market-intelligence replay examples/task02-btc-snapshot.json --format text
python -c 'import json; assert json.load(open("/tmp/task02.json")) == json.load(open("examples/task02-btc-analysis.json"))'
```

Dados são uma captura histórica, não a cotação atual. Uma coleta nova terá outro
corte e pode mudar eventos/estados. Hash confere conteúdo, não autentica a Binance.

## Sequência sintética

`task02-synthetic-snapshot.json` declara `source=simulated`, endpoint de fixture e
100 candles por intervalo. Sequência criada: faixa oscilando entre preços de teste,
seguida por rompimento com volume, follow-through e reteste. SOS e LPS satisfazem
as regras nos três intervalos. Isso **não representa preços observados**, nem uma
agregação real H1→H4→D1; serve apenas à demonstração dos contratos/algoritmos.

Os eventos não forçam um cenário bullish: este ainda aguarda confirmação quando
os votos estruturais não satisfazem a regra, apesar do padrão SOS/LPS. Saída em
`task02-synthetic-analysis.json` e `.txt`. Fixtures pequenas para Spring/Upthrust,
SOW/LPSY e invalidações em `tests/task02_fixtures.py`, também explicitamente simuladas.

```bash
market-intelligence replay examples/task02-synthetic-snapshot.json --format text
```
