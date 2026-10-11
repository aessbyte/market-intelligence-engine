# Auditoria inicial — Task 02

Executada antes da primeira alteração de arquivo, em 11/10/2026.
Baseline GitHub: `3868fd7ea9daca0aeda8affbc2d47eca976c79a0`, branch `main`.
Árvore completa: 30 arquivos; hashes Git de todos conferidos com a cópia local.
A pasta local não continha `.git`; o estado publicado foi conferido via API GitHub.

## Evidência executada

* Leitura de README, ARCHITECTURE, AGENTS, VALIDATION, DEMO, licença, configuração,
  workflow, todos os módulos fonte e testes.
* Python 3.12.14: `python -B -m unittest discover -s tests -v`: 39 testes passaram.
* Replay do snapshot BTCUSDT: objeto JSON exatamente igual ao exemplo publicado.

## Implementação efetiva

Cliente público GET/time/exchangeInfo/klines; normalização/disponibilidade do símbolo;
paginação de até 5000 candles; timeout/retries limitados; snapshots brutos v1;
validação OHLCV/continuidade/UTC/cutoff; indicadores causais e sementes explícitas;
regime heurístico v1 e consenso unânime; JSON Schema v1; CLI analyze/replay;
protocolo AnalysisModule; 39 testes offline; CI Python 3.11/3.12 configurada; MIT.
Não foram encontrados pivôs, BOS/CHoCH, trading ranges, eventos Wyckoff, análise
estrutural multitimeframe, cenários bullish/bearish/neutral ou saída textual.
Os dois cenários existentes são textos genéricos de persistência/transição.

## Dependências e lacunas

Runtime: biblioteca padrão; extras dev: ruff 0.11.13, mypy 1.15.0, jsonschema 4.26.0.
Sem duplicação relevante dos indicadores/providers. A fronteira JSON usa Any;
objetos internos são dataclasses/enums. Orquestrador contém tratamento de qualidade
e criação do resultado: novos módulos devem reutilizar candles validados, sem
refetch ou reimplementar fórmulas. Classes AnalysisModule ainda não são registradas.

Schema estrito exige versionamento para novos campos. Snapshot v1 deve continuar
aceito. Índices/pivôs precisam distinguir gráfico, primeira observação e confirmação.
Não há log de eventos ou detecção de baixa liquidez. exchangeInfo é atual; dados
revisados, disponibilidade point-in-time e autenticação da origem não são resolvidos.
Testes de causalidade anteriores verificam indicadores, não eventos confirmados.
Sem motor estatístico, calibração, backtest ou alegação de vantagem demonstrada.

## Plano de preservação

Manter cliente, validação, indicadores, regime v1, comandos, snapshot v1 e chaves
existentes. Expandir resultado padrão para v2; oferecer resultado legado explícito v1
para reprodução do exemplo antigo. Novos módulos puros e configuráveis, diário
append-only de transições, regras documentadas, sem probabilidade arbitrária.
