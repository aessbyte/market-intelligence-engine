# Verificação executada — Etapa 1

Data: 11/10/2026. Ambiente local Python 3.12.14. Motor sem dependências externas
de execução. Instalação editável em virtualenv e construção de wheel verificadas.

## Testes automatizados

`python -m unittest discover -s tests -v`: **39 testes, todos passaram**.

Cobertura comportamental:

* Cliente público com transporte simulado: endpoints e ausência de credenciais,
  símbolos, disponibilidade, horário do servidor, limites, paginação, corte comum,
  HTTP 429/5xx, falhas de conexão, erros de cliente/restrição e JSON inválido.
* Validação: H1/H4/D1, preços/volumes/trades, valores não finitos, lacunas, duplicatas,
  ordem, alinhamento UTC, timestamps de fechamento, séries curtas e defasadas.
* Indicadores: sementes EMA/Wilder com valores calculados à mão, RSI misto com
  referência independente, alta/baixa/flat, OBV e volume zero.
* Regimes: alta, baixa, lateralização, indeterminado, limiares exatos e conflitos.
* Look-ahead: append de candles futuros não altera indicadores/regime; prefixo
  histórico equivale ao recorte no mesmo cutoff; replay histórico de três intervalos;
  candle no limite inclusivo de fechamento fica excluído.
* Engine/CLI: repetibilidade, não mutação do snapshot, dados simulados explícitos,
  erros/degradação, entradas malformadas, overflow de indicadores, JSON Schema e
  códigos de saída. Schema rejeita probabilidade inventada.

Esses testes não demonstram poder preditivo nem disponibilidade de dados point-in-time.

## Verificações estáticas

Executadas no ambiente conectado sobre cópia dos mesmos arquivos fonte/testes:

```text
ruff 0.11.13 check src tests: passou
ruff 0.11.13 format --check src tests: 17 arquivos formatados
mypy 1.15.0 src: sucesso, 9 arquivos fonte, modo strict
```

## Integração real e reprodução

CLI executada com BTCUSDT e endpoint público Binance, sem credenciais: exit 0,
750 candles fechados (250 por intervalo), todas as séries válidas. A captura e a
análise estão em `examples`. Replay local da captura produziu objeto JSON idêntico
ao resultado obtido no ambiente conectado. Detalhes e hash em `examples/DEMO.md`.

CI configurada para repetir testes offline, ruff, mypy e replay em Python 3.11 e
3.12. Este relatório registra os checks executados nesta entrega; não afirma que
os jobs hospedados do GitHub já tenham terminado.
