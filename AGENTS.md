# Instruções de desenvolvimento

## Escopo

Python 3.11+, arquitetura em `src/market_intelligence`, testes em `tests`.
Não implementar execução de ordens, endpoints privados, GUI definitiva ou previsões
sem evidência no escopo da Etapa 1. Preservar licença MIT e privacidade do repositório.

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
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src
```

Testes são offline; chamadas live devem ser explícitas e separadas dos unitários.
Para validar a demonstração sem rede:

```bash
market-intelligence replay examples/btc-snapshot.json --output /tmp/replay.json
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
