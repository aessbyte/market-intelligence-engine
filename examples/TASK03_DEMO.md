# Task 03 — Demonstração real BTCUSDT

Os arquivos `task03-btc-*` contêm dados reais coletados da API pública Binance spot,
com corte **2026-10-11 19:49:42.394 UTC**. Não são preços atuais. O pipeline foi
treinado em 11/10/2026, 20:04:40–20:05:03 UTC; não se alega emissão prospectiva às
00:00 da origem diária. `task03-run.json` separa horário operacional e disponibilidade
informacional assumida.

## Arquivos e origem

| Arquivo | Conteúdo |
| --- | --- |
| task03-btc-dataset.json | 3.166 candles D1 reais de 09/02/2018 a 10/10/2026, origem, UTC, qualidade e recorte auditado |
| task03-config.json | Parâmetros predefinidos, seed 42 e protocolo temporal |
| task03-btc-model.json | Bundle JSON, parâmetros, contexto, versões e relatório |
| task03-btc-evaluation.json | Métricas por horizonte/modelo/fold, calibração, purge, cobertura e holdout final |
| task03-btc-prediction.json | Resultado de inferência com abstinência e diagnósticos experimentais identificados |
| task03-btc-prediction.txt | Leitura textual da previsão |
| task03-btc-snapshot.json | Snapshot real D1/H4/H1 com corte histórico alinhado ao dataset |
| task03-btc-analysis.json / .txt | Resultado v3 integrado em JSON/texto, com estrutura, Wyckoff, cenários e previsões |
| task03-run.json | Período operacional, configuração, versões e hashes |
| task03-data-audit.json | Falha da captura original e critério explícito do recorte |

Dataset SHA-256:
`d4b3fb3b08d6d2a62b5913228bd0d7a733bf9ba2cf570f15dee268cb091e4868`.
Bundle: `model-3703fd3ae9432487`, SHA-256:
`3703fd3ae94324879015dc47831daaf45157fdffc1db3379bb2d24bcc7d85838`.
O digest canônico do histórico de candles é
`ec6e531fea10cf760cc22b57dff175dc58aa8a2bc66cf75dd4e12f380c554d64`.
Esses hashes verificam igualdade de conteúdo; não autenticam o fornecedor.

O snapshot D1/H4/H1 foi coletado em 12/10/2026 com o corte histórico de 11/10/2026
19:49:42.394 UTC, 250 candles fechados por intervalo. Metadata exchangeInfo e horário
do servidor refletem 12/10; não são dados de listagem point-in-time. Snapshot
canônico SHA-256:
`7d6b4857c0a85a474fcf2ca874dbb6ed52ef4ed237eed1f66a2fa4304a587571`.
Resultado integrado canônico SHA-256:
`83cfa4a219a927c476a98c5bdbab31737dd043794dc700fb9e9b282fdd238c39`.

A captura original de 3.342 candles foi recusada por um timestamp de fechamento
incompatível com D1 em 08/02/2018. Não houve correção silenciosa. O período contíguo
desde 09/02/2018 foi escolhido por integridade antes de qualquer resultado de modelo;
176 rows foram excluídas, com hash/qualidade do pai preservados no registro.

## Reprodução offline

Na raiz do repositório, após instalar `.[dev,predictive]`:

```bash
market-intelligence train examples/task03-btc-dataset.json \
  --config examples/task03-config.json \
  --output /tmp/task03-btc-model.json --report /tmp/task03-btc-evaluation.json

market-intelligence predict examples/task03-btc-dataset.json \
  --model examples/task03-btc-model.json --output /tmp/task03-btc-prediction.json

market-intelligence predict examples/task03-btc-dataset.json \
  --model examples/task03-btc-model.json --format text

market-intelligence replay examples/task03-btc-snapshot.json \
  --schema-version 3 --model examples/task03-btc-model.json \
  --prediction-dataset examples/task03-btc-dataset.json \
  --output /tmp/task03-btc-analysis.json

market-intelligence replay examples/task03-btc-snapshot.json \
  --schema-version 3 --model examples/task03-btc-model.json \
  --prediction-dataset examples/task03-btc-dataset.json --format text
```

Com os arquivos salvos, inferência não exige rede nem o extra de treinamento.
Comparar JSON canônico, não a indentação dos arquivos. Reproduzir o bundle exige
mesmas versões/configuração; diferenças de plataforma podem afetar aritmética de
fitting. `task03-run.json` é um registro operacional, não entrada determinística.

O modelo exige o histórico completo desde seu início, preservando candles usados
no bundle. Um dataset curto com apenas os 250 últimos candles não reproduz o
contexto integral de pivôs/Wyckoff e é recusado. Outra captura pode incorporar novos
candles, mas precisa preservar o histórico e ter corte compatível com a análise.

## Coleta explícita de uma nova população

```bash
market-intelligence dataset BTCUSDT --bars 5000 \
  --start 2018-02-09T00:00:00Z \
  --selection-reason 'Excluir período anterior: fechamento D1 inválido em 2018-02-08; critério de integridade' \
  --output /tmp/btc-dataset-current.json

market-intelligence train /tmp/btc-dataset-current.json \
  --config examples/task03-config.json --output /tmp/btc-model-current.json \
  --report /tmp/btc-evaluation-current.json

market-intelligence analyze BTCUSDT --schema-version 3 \
  --model /tmp/btc-model-current.json \
  --prediction-dataset /tmp/btc-dataset-current.json --format text
```

Esses comandos usam rede e geram uma nova captura/resultados; não prometem igualdade
com o experimento salvo. Para outros símbolos, o início do período e o critério de
qualidade precisam refletir seus próprios dados. Histórico curto ou inconsistente
não ativa simulação.

## Resultado observado

Referência de preço: último fechamento D1, **82.988,36 USDT**, origem
11/10/2026 00:00 UTC. Todos os campos públicos de probabilidades e magnitude são null.

| Horizonte | Status | N OOS / origens não sobrepostas | Brier da política de seleção | Log loss | Cobertura nominal 80% |
| --- | --- | --- | ---: | ---: | ---: |
| 7 dias | UNVALIDATED_MODEL | 1.914 / 278 | 0,649886 | 1,074473 | 81,77% |
| 30 dias | UNVALIDATED_MODEL | 1.776 / 64 | 0,910716 | 3,552877 | 62,33% |
| 90 dias | INSUFFICIENT_EVIDENCE | 1.375 / 20 | 0,876396 | 2,281470 | 69,96% |

O teste final congelado possui apenas 18, quatro e quatro origens não sobrepostas,
respectivamente, abaixo do mínimo de 30. Calibração de 30/90 dias tem apenas seis e
duas origens, abaixo do mínimo de dez. Não houve melhoria sustentada contra baselines;
90 dias também apresenta drift na origem capturada. Diagnósticos numéricos de 7/30
dias são explicitamente experimentais, sem validação. Uma probabilidade computada
não constitui previsão utilizável.

Resultados completos por candidato, comparações em populações comuns e períodos
estão em [../TASK03_REPORT.md](../TASK03_REPORT.md). Dados sintéticos em testes e
nos exemplos anteriores permanecem identificados como simulados e não participam
destas métricas reais.
