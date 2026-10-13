# Market Intelligence Engine

Motor Python para análise **auditável** de mercados spot usando OHLCV público da
Binance. As etapas 1 e 2 oferecem indicadores, estrutura, hipóteses Wyckoff e cenários
condicionais. A Task 03 acrescenta datasets históricos, features causais, modelos
probabilísticos e avaliação temporal fora da amostra. O experimento real BTCUSDT
**não sustentou uma previsão validada**: os campos públicos de probabilidade e
magnitude permanecem `null`, com motivos explícitos e diagnósticos experimentais.
Não há execução de ordens ou credenciais privadas. A Task 05 integra o motor a uma
aplicação web responsiva, com gráficos financeiros, estrutura, Wyckoff, cenários,
previsões e transparência estatística. O navegador apresenta o resultado do backend;
não reimplementa modelos nem treina a cada consulta.

Licença MIT. O repositório permanece privado conforme a criação solicitada; a licença
permite distribuição open source quando o proprietário decidir publicá-lo.

## Instalação

Python 3.11 ou superior. Análise descritiva e inferência de artefatos JSON usam a
biblioteca padrão. Treinamento requer o extra opcional `predictive`.

```bash
git clone https://github.com/aessbyte/market-intelligence-engine.git
cd market-intelligence-engine
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Para treinamento e desenvolvimento completo:

```bash
python -m pip install -e '.[dev,predictive]'
python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src
```

O extra fixa NumPy 2.3.5, SciPy 1.17.0 e scikit-learn 1.8.0; as ferramentas de
verificação também são fixadas em `pyproject.toml`. Os testes são offline, com dados
sintéticos explicitamente identificados e transporte simulado. Eles verificam o
software; não demonstram desempenho preditivo real. `jsonschema` está no extra `dev`.

## Uso

### Aplicação web — Task 05

Python 3.11+, Node.js 22 ou 24 e npm. Instale o adaptador web e compile o frontend:

```bash
python -m pip install -e '.[web]'
cd frontend
npm ci
npm run build
cd ..
bash scripts/start-web.sh
```

Abra **http://127.0.0.1:8000** e informe um símbolo, como `BTCUSDT`. O servidor padrão
consulta dados públicos atuais da Binance spot. Sem modelo previamente configurado,
o diagnóstico continua disponível e as previsões retornam indisponibilidade explícita.
Documentação da API: **http://127.0.0.1:8000/docs**.

Para visualizar a captura real histórica e o modelo experimental da Task 03:

```bash
bash scripts/start-web-example.sh
```

Esse comando inicia um **replay explicitamente configurado**, identificado na interface;
não consulta a cotação atual e só atende ao símbolo da captura. As probabilidades
públicas permanecem `null` quando os gates científicos não são satisfeitos.

O dashboard oferece Visão geral, Gráfico, Estrutura, Wyckoff, Previsões e Auditoria,
com H1/H4/D1, overlays causais, métricas OOS e exportação JSON. Futuros e W1 não são
suportados pelo motor atual. O manifest prepara uso como PWA; não há cache offline
de consultas nem resultados sintéticos de fallback.

Configuração, modo de desenvolvimento, acesso pelo Android e deploy:
[`docs/WEB.md`](docs/WEB.md). Inspeção inicial: [`AUDIT_TASK05.md`](AUDIT_TASK05.md).
Relatório e screenshots: [`TASK05_REPORT.md`](TASK05_REPORT.md).
A Task 04 separada não foi localizada no repositório auditado; a integração não
pressupõe sua implementação ou uma validação estatística adicional.

### Linha de comando

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

## Previsão e validação temporal — Task 03

O contrato padrão continua v2. Previsões integradas exigem `--schema-version 3`,
um bundle JSON e um dataset D1 compatível com o histórico e o corte da análise.
Sem modelo ou evidência suficiente, v3 retorna os horizontes 7/30/90 dias com status
e probabilidades ausentes. O schema está em `result-v3.schema.json`.

```bash
# Rede explícita: armazenar histórico real, sem fallback sintético.
market-intelligence dataset BTCUSDT --bars 5000 --output btc-dataset.json

# Treinar, selecionar na validação, calibrar em bloco separado e avaliar holdouts.
market-intelligence train examples/task03-btc-dataset.json \
  --config examples/task03-config.json --output /tmp/btc-model.json \
  --report /tmp/btc-evaluation.json

# Inferência offline com artefato salvo; não refaz treinamento.
market-intelligence predict examples/task03-btc-dataset.json \
  --model examples/task03-btc-model.json --format text
market-intelligence predict examples/task03-btc-dataset.json \
  --model examples/task03-btc-model.json --output /tmp/btc-prediction.json

# Replay integrado dos três intervalos e previsões no mesmo corte histórico.
market-intelligence replay examples/task03-btc-snapshot.json --schema-version 3 \
  --model examples/task03-btc-model.json \
  --prediction-dataset examples/task03-btc-dataset.json --format text

# Análise descritiva v3 sem bundle: previsões indisponíveis explicitamente.
market-intelligence analyze ETHUSDT --schema-version 3 --format text
```

A coleta completa de BTC encontrou um timestamp de fechamento inválido em
08/02/2018. O treino recusou esse dataset. O exemplo real usa o período contíguo
desde **09/02/2018**, escolhido por integridade antes da modelagem; não houve reparo
do candle. Uma nova coleta com o mesmo critério explícito pode usar:

```bash
market-intelligence dataset BTCUSDT --bars 5000 \
  --start 2018-02-09T00:00:00Z \
  --selection-reason 'Excluir período anterior: fechamento D1 inválido em 2018-02-08; critério de integridade' \
  --output btc-dataset.json
```

Essa chamada captura dados atuais e gera outro hash; a reprodução exata usa o
dataset salvo. O bundle deve receber o histórico completo desde seu início
registrado, preservando candles anteriores e disponibilidades dos eventos. Dados
alterados, truncados, de outro símbolo ou posteriores ao corte provocam abstinência.

São comparados frequências históricas, momentum, regressão logística multinomial
e gradient boosting quando há treino suficiente. Features D1 incluem indicadores,
estrutura e Wyckoff conhecidos na origem; H1/H4 continuam na análise descritiva.
Alvos de 7/30/90 dias usam limites proporcionais à volatilidade observada na origem.
Walk-forward aplica purge de alvos, embargo, scaler somente no treino e calibração
reservada. Brier, log loss, tabelas de calibração, comparações pareadas e cobertura
dos intervalos são persistidos por horizonte/fold. Nenhum holdout seleciona modelos.

As classes estatísticas representam retorno **ao final do horizonte**. Seus campos
não são probabilidades dos cenários condicionais de estrutura/Wyckoff. Magnitude
empírica, quando sustentada, é distribuição de retornos e não suporte, resistência
ou preço garantido. `experimental_diagnostics` é exclusivamente material de pesquisa.

Regras matemáticas e gates: [`TASK03_RULES.md`](TASK03_RULES.md). Auditoria e defeitos
corrigidos: [`AUDIT_TASK03.md`](AUDIT_TASK03.md). Métricas reais, falhas e próximos
passos: [`TASK03_REPORT.md`](TASK03_REPORT.md). Comandos, dados e hashes da execução:
[`examples/TASK03_DEMO.md`](examples/TASK03_DEMO.md).

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
de regras. Smart Money completo, fluxo e backtesting de estratégias continuam como
extensões futuras. O pipeline probabilístico está implementado para pesquisa, com
critérios de abstinência; validação robusta para uso operacional continua pendente.

Há interface web integrada; não há infraestrutura de negociação, chave de API ou
backtest de estratégia.
O exemplo inclui modelo treinado e avaliação probabilística, sem vantagem estatística
declarada. Uma amostra de um único ativo/corretora não estabelece desempenho geral
nem resultado financeiro de uma estratégia.
