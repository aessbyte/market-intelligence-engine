# Instruções de desenvolvimento

## Escopo

Python 3.11+, arquitetura em `src/market_intelligence`, testes em `tests`.
Frontend React/TypeScript em `frontend`; API opcional em `src/market_intelligence/web`.
Não implementar execução de ordens, endpoints privados ou previsões sem evidência.
A interface web foi autorizada explicitamente pela Task 05, ampliando a restrição
de GUI das etapas anteriores. Preservar licença MIT e privacidade do repositório.
Antes de ampliar o motor, ler documentação e código e executar a suíte existente;
não considerar uma capacidade implementada apenas porque está no README.

## Regras

* Manter rede exclusivamente em providers; análise deve ser pura e determinística.
* Usar dataclasses imutáveis, tipos explícitos e protocolo de transporte injetável.
* Respeitar `as_of_ms` em todos os intervalos; só usar candles já fechados.
* Não corrigir silenciosamente gaps, timestamps, ordem ou dados inválidos.
* Não apresentar dados simulados como reais. Fixtures devem ser rotuladas `simulated`.
* Nunca inventar probabilidades, preços futuros ou alegações de vantagem estatística.
* Registrar mudanças de decisões em ARCHITECTURE.md; versionar regras e contratos.
* Atualizar docs, schema JSON e exemplo quando o contrato mudar.
* Não colocar secrets em snapshots, logs, commits ou argumentos de teste.

## Instalação e checks obrigatórios

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,predictive,web]'
python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src
```

Testes são offline; chamadas live devem ser explícitas e separadas dos unitários.
Para validar a demonstração sem rede:

```bash
market-intelligence replay examples/btc-snapshot.json --schema-version 1 --output /tmp/replay.json
python -c 'import json; assert json.load(open("/tmp/replay.json")) == json.load(open("examples/btc-analysis.json"))'
```

## Regressões que devem ter teste

Parsing/continuidade, alinhamento UTC e corte inclusivo/exclusivo; disponibilidade e
paginação; séries curtas/flat/volume zero; todos os regimes e seus limiares;
conflito entre timeframes; append de futuros candles não altera features históricas;
prefixo histórico equivale ao recorte no mesmo cutoff; erro de rede não ativa dados
simulados; schema e códigos de saída CLI. Fórmulas devem ter valores de referência
independentes, sem apenas copiar a implementação para o teste.

Ruff verifica e formata `src` e `tests`; mypy strict verifica `src`. O uso de `Any`
na fronteira JSON é deliberado; valide tipos antes de convertê-los ao domínio.

Task 02: preservar event_journal append-only; alterações de estado só ficam visíveis
em available_at_ms, com confirmação de pivôs depois dos candles à direita.
Testar causalidade em cada prefixo e comparar diários filtrados por disponibilidade.
Wyckoff confirmado por regra não autoriza afirmar fases ou inventário institucional.
Probabilidades/retornos permanecem null até existir modelo/calibração versionados.
Manter replay legado v1 e os exemplos Task 02 (reais e simulados claramente separados).

Task 03: manter o contrato padrão v2; previsões integradas usam schema v3 explícito.
Treinamento depende do extra predictive; inferência usa artefatos JSON, sem pickle.
Features D1 e alvos devem registrar origem/disponibilidade. Nunca fazer shuffle de
séries; fazer purge de target_available_ms nas fronteiras, embargo configurável,
normalização no treino, seleção na validação e calibração no bloco reservado.
Nenhum resultado do teste pode alterar modelo, limiar ou hiperparâmetro.
Verificar métricas e contagens por horizonte, amostras não sobrepostas, cobertura
dos intervalos, gates de abstinência e reprodução com seed. Dados sintéticos não
validam modelos reais. Probabilidades públicas permanecem null quando o modelo
não satisfaz a política; diagnósticos experimentais precisam de rótulo explícito.

Task 05: preservar a separação motor/API/apresentação. `web/` só coordena providers,
artefatos previamente validados e `engine.analyze` v3; não duplicar regras e não
treinar em consultas. Schemas Pydantic e Zod precisam concordar com tipos reais,
nulls, mercado e timestamps. O endpoint de engine integral preserva os diários.
Mudanças de contrato web devem incluir testes Python, contrato TypeScript e UI.

Gráficos devem usar candles fechados/séries do backend. Pivôs não são conhecidos
em sua origem retrospectiva; testar marcadores por disponibilidade e níveis que
começam após a confirmação. Não converter candidato em fato, cenário em previsão,
intervalo de retorno em suporte ou probabilidade ausente em zero/default. Manter
replay/simulação visíveis. W1 e futuros permanecem explicitamente indisponíveis.

Checks web adicionais, além da suíte Python e seus checks:

```bash
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Playwright serve o build pronto pela API de teste na porta 8001. O provider é sintético,
rotulado `simulated`, sem rede nem fallback; esses testes não validam Binance live.
`MIE_TEST_PYTHON` pode definir o Python usado e `MIE_CHROMIUM` um executável existente.
Manter screenshots sintéticos distintos de screenshots reais/históricos.

Testar teclado, ausência de probabilidades, respostas incompletas, erro de símbolo,
falha de fonte, cache, navegação sem nova análise, overlays e viewport de 360 px.
Não escrever na API endpoints administrativos de treino ou execução de código.
Jobs/cache/limites ficam em memória e não são controles distribuídos de múltiplos
processos. Configurações e execução estão em `docs/WEB.md`.
