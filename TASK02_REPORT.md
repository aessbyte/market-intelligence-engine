# Relatório técnico — Task 02

## Auditoria e compatibilidade

Baseline `3868fd7ea9daca0aeda8affbc2d47eca976c79a0`: todos os 30 arquivos
conferidos por hash Git, documentação e código lidos antes de editar. Os 39 testes
existentes passaram; replay real v1 conferido. Estado inicial em AUDIT_TASK02.md.

Cliente Binance, validação, indicadores e regime da Etapa 1 foram reutilizados.
Nenhum desses componentes foi refeito. Comandos analyze/replay permanecem; snapshot
continua v1. Saída padrão v2, versão do pacote 0.2.0. Resultado v1 disponível por
opção explícita e reproduz exatamente o exemplo antigo. Licença MIT e repositório
privado mantidos. Não se implementou ordem, chave privada, GUI ou modelo preditivo.

## Funcionalidades verificadas

| Área | Implementação |
| --- | --- |
| Estrutura | pivôs configuráveis, HH/HL/LH/LL/EH/EL, tendência, níveis, BOS/CHoCH por fechamentos, invalidação/possíveis falsas rupturas |
| Causalidade | timestamps gráfico/detecção/disponibilidade, candidato/confirmado/invalidado, diário append-only de revisões |
| Wyckoff | faixa com limites congelados, testes de extremos, Spring/Upthrust, SOS/SOW, LPS/LPSY, filtros explícitos de volume e liquidez |
| Interpretação | observações separadas de hipóteses; acumulação/distribuição/reacumulação/redistribuição candidatas; fase null |
| Multitimeframe | D1/H4/H1 fechados no mesmo corte, concordâncias/conflitos, divergência estrutura/indicadores, sem autoridade automática do D1 |
| Cenários | bullish/bearish/neutral com tese, evidência favorável/contrária, ativação, invalidação, níveis, estado e insuficiências |
| Contratos/CLI | JSON Schema v2 e legado v1, configuração JSON validada, apresentação textual em português, slots quantitativos indisponíveis |

Regras matemáticas, operadores e limites completos em TASK02_RULES.md.

## Testes e verificações executados

Python local 3.12.14. `python -m unittest discover -s tests -q`: **83 testes
passaram**, incluindo os 39 anteriores, mantidos, e 44 novos. Cobrem todos os tipos
de evento pedidos, atraso de confirmação e invalidação, empate de pivôs, janela
configurável, ausência de contexto, dados faltantes e baixa liquidez, conflitos,
ativação/invalidação dos três cenários, determinismo, CLI e schemas.

Causalidade: todos os prefixos das sequências de BOS/CHoCH, Spring, Upthrust e SOS/LPS,
mais 120 prefixos de sequência mista analítica, comparados ao diário completo filtrado
por available_at_ms. Também verificadas entrada integral no corte parcial,
exclusão no fechamento inclusivo e invariância integrada ao acrescentar candles
futuros H1/H4/D1. Nenhuma confirmação apareceu antes dos dados necessários.

Ruff 0.11.13: lint e format de src/tests. Mypy 1.15.0 strict: 16 módulos fonte.
Checks executados sobre os arquivos finais no ambiente conectado; teste e replay
também executados localmente. Instalação editável, wheel e replay dos três exemplos
(legado real, Task 02 real, sintético) verificados. CI configurada para repetir checks
em Python 3.11/3.12; isso não é uma afirmação de que jobs hospedados já concluíram.

## Execução real e exemplo sintético

Binance BTCUSDT em 2026-10-11T18:33:48.435Z: 750 candles íntegros.
Estrutura D1 baixa, H4/H1 lateralização, com conflitos preservados. No corte,
bullish aguarda confirmação; bearish invalidado; neutral ativo por regra de faixas.
Evidências contrárias D1 continuam explícitas. JSON remoto e replay local coincidem.
Snapshot bruto, JSON, texto e hashes em examples/TASK02_DEMO.md e task02-btc-*.

task02-synthetic-* declara source=simulated; demonstra SOS/LPS sem alegar preços
observados ou coerência de agregação real entre timeframes. Fixtures adicionais
simuladas cobrem Spring/Upthrust, SOW/LPSY e suas invalidações. Nenhuma probabilidade,
alvo de preço ou retorno esperado foi apresentado.

## Resumo dos arquivos

Novos módulos: events.py, structure.py, wyckoff.py, multitimeframe.py, scenarios.py,
config.py e render.py. Integração: engine.py, cli.py e versão do pacote. Contratos:
result.schema.json expandido e result-v1.schema.json conservado. Seis novos arquivos
de testes, incluindo fixtures. Documentos de auditoria, regras, relatório e exemplos.
README, ARCHITECTURE, AGENTS, exemplo legado e CI atualizados. Configuração e
capturas novas em examples. Código de binance.py, validation.py, indicators.py,
regime.py e models.py preservado.

O SHA e a lista exata de arquivos alterados ficam no commit GitHub da entrega,
referenciado na resposta final. A árvore publicada é conferida contra os arquivos
locais por hash de blob Git; não é necessário inserir um SHA autorreferencial aqui.

## Limitações e trabalho antes do motor quantitativo

O sistema é interpretativo por regras. Confirmação significa condição satisfeita,
não fase Wyckoff verdadeira, ação institucional ou vantagem estatística. Buffers,
janelas e filtros são heurísticos; sensibilidade precisa ser estudada. Extremos
intrabar não têm ordem conhecida. Não há ranges aninhados, múltiplos retestes do
mesmo tipo/faixa, dados de livro/fluxo ou confirmação entre corretoras. Sinais
históricos permanecem no diário após o horizonte de monitoramento; cenários
aplicam filtro de frescor. Alterar janela de entrada pode alterar contexto/sementes.

Próximos requisitos para previsão quantitativa:

1. Base point-in-time e versionamento de disponibilidade/revisões, listagens e
   metadados históricos; controle de survivorship e qualidade entre corretoras.
2. Definição de alvos, horizontes e retorno; desenho de amostragem e custo de decisão.
3. Backtester causal de eventos com instante de confirmação, custos, fees,
   slippage e splits temporais purgados/embargados quando houver labels sobrepostos.
4. Avaliação fora da amostra e walk-forward; baselines, estabilidade por regime/ativo,
   sensibilidade de parâmetros e incerteza estatística. Nenhum ajuste em teste futuro.
5. Modelo probabilístico versionado, calibração fora da amostra (Brier/log loss,
   reliability), faixas de retorno com cobertura verificada e evidência reproduzível.
6. Dados de microestrutura quando necessários, monitoramento de drift, alertas de
   degradação e política explícita de abstinência do modelo.

Até esses requisitos serem atendidos, probabilidades e faixas de retorno permanecem
null/unavailable; cenários ativos não equivalem a previsões ou recomendações.
