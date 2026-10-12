# Task 03 — Entrega técnica e avaliação probabilística

O pipeline de dados, treino, walk-forward, inferência e integração foi implementado.
O experimento real BTCUSDT **não sustenta previsões validadas**: 7 e 30 dias retornam
`UNVALIDATED_MODEL`, e 90 dias retorna `INSUFFICIENT_EVIDENCE` na referência avaliada.
Probabilidades públicas e distribuição de retornos validada permanecem `null`.
Isso é uma conclusão dos gates de evidência, não uma falha em produzir resultados.

## Auditoria da base e correções

Base: commit `5a574fb2e1d503b45a9f1aa2403fb328213f5dcb`, 55 arquivos e **83 testes
iniciais aprovados**. A inspeção confirmou providers, indicadores, pivôs, estrutura,
Wyckoff, cenários e replay; os slots null existentes não eram modelos estatísticos.
Auditoria completa: [AUDIT_TASK03.md](AUDIT_TASK03.md).

Foram corrigidos o bloqueio permanente de um nível após expiração de BOS/CHoCH em
configurações com múltiplos fechamentos e a aceitação de booleanos em campos OHLCV.
Regressões cobrem esses casos. O diário causal preserva revisões por disponibilidade;
features não usam o estado final retrospectivo de um evento. O contexto histórico
completo de estrutura/Wyckoff é preservado também na inferência, evitando diferenças
entre o contexto usado no treino e uma janela curta fornecida posteriormente.

Os testes de prefixo verificam causalidade nas sequências exercitadas. Eles não
certificam latência histórica, ausência de revisões do fornecedor ou validade de
metadados de listagem point-in-time.

## Funcionalidades entregues

| Componente | Implementação e contrato |
| --- | --- |
| Dataset | Binance spot D1, UTC, rows originais, qualidade, limites temporais, origem, versão, hash e recorte explícito auditado |
| Features | 65 variáveis causais de indicadores, regime, estrutura e Wyckoff, com fonte/disponibilidade por scalar |
| Alvos | Classes exclusivas de retorno final em 7/30/90 dias, limiar proporcional à volatilidade inicial, retorno contínuo e excursões separadas |
| Modelos | Frequência suavizada, baseline de momentum, logística multinomial e gradient boosting com mínimo de treino |
| Validação | Walk-forward cronológico, purge, embargo, scaler no treino, seleção na validação, calibração reservada e teste final congelado |
| Probabilidades | Brier multiclass, log loss, tabelas de calibração por classe, ECE e comparação pareada contra referência simples |
| Magnitude | Mistura empírica condicionada à classe, mediana/quantis, intervalo nominal 80%, risco de retorno final abaixo de −20% e cobertura OOS |
| Confiabilidade | Abstinência por insuficiência, incompatibilidade, drift, baixa liquidez, calibração, poucas origens não sobrepostas ou falta de melhoria |
| Integração | CLI dataset/train/predict; análise/replay v3 explícitos em JSON/texto; padrão v2 e replay v1 preservados |
| Artefato | Parâmetros e metadados JSON validados; inferência sem sklearn ou pickle |

Fórmulas, operadores, regras de calibração, fronteiras e gates estão em
[TASK03_RULES.md](TASK03_RULES.md). Decisões: ADR 011–015 em
[ARCHITECTURE.md](ARCHITECTURE.md). A população quantitativa é D1 de um símbolo;
D1/H4/H1 continuam na leitura descritiva, sem fabricar features históricas H1/H4.

## Experimento real e integridade

Fonte: `https://data-api.binance.vision`, Binance spot BTCUSDT. Corte do servidor:
**2026-10-11 19:49:42.394 UTC**. Último candle D1 disponível: abertura 10/10/2026,
fechamento 10/10/2026 23:59:59.999 UTC, preço 82.988,36 USDT. A referência diária da
previsão é 11/10/2026 00:00 UTC; o corte da análise é posterior. Esta captura é
histórica e não representa a cotação atual.

A captura original continha 3.342 candles desde 17/08/2017. O candle de 08/02/2018
possuía fechamento `1518049694788`, incompatível com a duração D1. A validação
recusou o dataset. O período contíguo desde **09/02/2018** foi escolhido por
integridade antes da modelagem, excluindo 176 rows anteriores; nenhuma foi reparada.
O dataset utilizado contém **3.166 candles válidos**, sem gaps ou candles abertos.
O hash e a qualidade do pai estão registrados em `selection` e no data-audit.

Após aquecimento de 100 candles, existem 3.067 origens de features. Alvos disponíveis:
3.060 em 7 dias, 3.037 em 30 e 2.977 em 90. Volatilidade usa 30 log-retornos e o
limiar fixo é `0,5 × sigma_origem × sqrt(h)`. As definições não foram ajustadas por
resultados de teste. Início/fim dos blocos, samples purgados, suporte das classes,
temperaturas e modelos excluídos estão no relatório JSON.

O treinamento registrado ocorreu em **11/10/2026, 20:04:40–20:05:03 UTC**, duração
23,84 s, seed 42 e um thread BLAS durante fitting. Não se alega que o modelo já
existia na referência diária das 00:00. Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0 e
scikit-learn 1.8.0 constam no registro de reprodução.

## Protocolo fora da amostra

Treino inicial: 730 dias, expansivo em passos de 365. Validação: 180 dias.
Calibração: 180 dias. Teste nominal: 365 dias, embargo de 7 dias entre blocos.
Alvos atravessando fronteiras são purgados, inclusive no fim de cada holdout.
O último fold elegível é congelado antes de sua avaliação; não há retreino depois
de consultar seu teste. Configuração/modelos candidatos são predefinidos.

Há seis folds em 7/30 dias e cinco em 90. O fold residual mais recente de 90 dias
não possui observações suficientes após purge e não é utilizado. Reutilizar dados
de teste antigo no treino de um fold cronologicamente posterior só ocorre após a
disponibilidade do alvo, mantendo o protocolo fixo.

## Métricas reais por modelo

Menor Brier e log loss são melhores. Brier multiclass usa soma dos três erros
quadráticos, escala 0–2. ECE é média dos erros de calibração ponderados por classe.
As métricas de cada candidato refletem a calibração disponível naquele fold; em
30/90 dias faltaram origens não sobrepostas para calibrar, e os modelos permaneceram
sem ajuste de temperatura. Métricas agregadas não tornam essas probabilidades validadas.

| Horizonte | Modelo | N OOS | Folds | Brier | Log loss | ECE |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| 7 d | Frequência | 1.914 | 0–5 | 0,649155 | 1,073335 | 0,020671 |
| 7 d | Momentum | 1.914 | 0–5 | 0,650613 | 1,075598 | 0,033379 |
| 7 d | Logística | 1.914 | 0–5 | 0,727384 | 1,196864 | 0,132337 |
| 7 d | Gradient boosting | 840 | 3–5 | 0,651225 | 1,074185 | 0,042189 |
| 30 d | Frequência | 1.776 | 0–5 | 0,655210 | 1,080654 | 0,023360 |
| 30 d | Momentum | 1.776 | 0–5 | 0,657342 | 1,083562 | 0,026862 |
| 30 d | Logística | 1.776 | 0–5 | 1,000880 | 3,774897 | 0,271886 |
| 30 d | Gradient boosting | 771 | 3–5 | 0,617689 | 1,027590 | 0,076475 |
| 90 d | Frequência | 1.375 | 0–4 | 0,660741 | 1,090114 | 0,085105 |
| 90 d | Momentum | 1.375 | 0–4 | 0,659646 | 1,088913 | 0,034776 |
| 90 d | Logística | 1.375 | 0–4 | 1,198783 | 6,449640 | 0,392000 |
| 90 d | Gradient boosting | 550 | 3–4 | 0,977047 | 1,574344 | 0,299382 |

Boosting exige 1.500 rows de treino, portanto **não possui a mesma população** das
linhas de frequência/momentum/logística acima. Para comparação nos seus folds, o
baseline simples escolhido na validação teve:

| Horizonte | N comum | Brier do baseline nos mesmos folds | Log loss do baseline nos mesmos folds |
| --- | ---: | ---: | ---: |
| 7 d | 840 | 0,658083 | 1,087949 |
| 30 d | 771 | 0,653853 | 1,078935 |
| 90 d | 550 | 0,715280 | 1,171031 |

As melhorias pontuais de boosting em 7/30 dias são descritivas. Não autorizam
substituir retrospectivamente o modelo escolhido na validação, nem comprovam
vantagem durável. Logística ficou substancialmente pior em 30/90 dias, com log loss
elevado e probabilidades mal calibradas. Complexidade não acrescentou evidência
suficiente para disponibilizar previsão pública.

## Estratégia de seleção e magnitude

Esta tabela avalia a política predefinida de escolher modelo na validação de cada
fold. É diferente de escolher retrospectivamente o melhor candidato pela tabela
de teste. Baseline de comparação também é escolhido na validação.

| Horizonte | N OOS | Origens espaçadas pelo horizonte | Brier | Log loss | ECE | Cobertura do intervalo nominal 80% | MAE da mediana de retorno |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 d | 1.914 | 278 | 0,649886 | 1,074473 | 0,031169 | 81,77% | 5,29 p.p. |
| 30 d | 1.776 | 64 | 0,910716 | 3,552877 | 0,208811 | 62,33% | 15,11 p.p. |
| 90 d | 1.375 | 20 | 0,876396 | 2,281470 | 0,209657 | 69,96% | 32,51 p.p. |

Em 7 dias a política escolheu somente baselines; sua melhoria pareada contra a
referência é zero. Em 30/90 dias seleção pela validação não protegeu contra mudança
de população e deterioração fora da amostra. Em 30 dias a cobertura agregada também
ficou abaixo do piso predefinido de 65% para intervalo nominal de 80%.

Contagens de origens não sobrepostas são aproximações conservadoras de amostra
efetiva, não prova de independência. Os relatórios guardam intervalos bootstrap
pareados de 95%, com 1.000 reamostragens. Não houve melhoria sustentada que passasse
os gates em Brier e log loss, juntamente com os demais critérios.

## Teste final preservado e calibração

Para 7/30 dias, blocos nominais finais: treino desde 20/05/2018 até 18/05/2025,
validação 25/05–21/11/2025, calibração 28/11/2025–27/05/2026, teste desde 03/06/2026.
O teste nominal iria até 03/06/2027, mas a captura fornece apenas um bloco parcial.
Depois de purge, origens válidas terminam em 04/10/2026 para 7 dias e 11/09/2026
para 30; os últimos alvos ficam conhecidos em 11/10/2026.

Para 90 dias, blocos finais: treino desde 20/05/2018 até 18/05/2024, validação
25/05–21/11/2024, calibração 28/11/2024–27/05/2025, teste 03/06/2025–03/06/2026.
Origens purgadas terminam em 04/03/2026; último alvo conhecido em 02/06/2026.
Datas finais nominais são limites exclusivos; valores exatos constam no JSON.

| Horizonte | Modelo congelado | Treino / validação / calibração / teste | N teste não sobreposto | Brier final | Log loss final | ECE final | Cobertura final |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 7 d | Frequência | 2.555 / 180 / 180 / 124 | 18 | 0,636412 | 1,054044 | 0,005319 | 87,10% |
| 30 d | Logística | 2.532 / 157 / 157 / 101 | 4 | 0,512225 | 0,854771 | 0,183714 | 79,21% |
| 90 d | Frequência | 2.107 / 97 / 97 / 275 | 4 | 0,773976 | 1,258013 | 0,281247 | 69,09% |

A calibração final de 7 dias tem 26 origens não sobrepostas, suporte de classes
`[49,88,43]` (bearish, neutral, bullish) e temperatura 0,978987. Em 30 dias são seis
origens e suporte `[37,87,33]`; em 90 são duas e `[41,42,14]`. O mínimo predefinido é
dez origens não sobrepostas: em 30/90 o ajuste é indisponível, temperatura 1 e status
de calibração `INSUFFICIENT_EVIDENCE`. `CALIBRATED` em 7 dias significa ajuste no
bloco reservado; não significa vantagem ou validação do modelo inteiro.

O mínimo de teste final é 30 origens não sobrepostas; nenhum horizonte o satisfaz.
Em 30 dias, a melhoria final média de Brier da logística contra o baseline é
0,077235, mas IC95% **[−0,085476; 0,349257]**; melhoria de log loss 0,159349, IC95%
**[−0,075932; 0,544156]**. Ambos incluem zero. O resultado final favorável isolado
não supera as falhas agregadas, calibração insuficiente e quatro origens efetivas.

## Resultado na referência e limitações

| Horizonte | Status público | Razões principais |
| --- | --- | --- |
| 7 d | UNVALIDATED_MODEL | Baseline final, melhoria não sustentada e apenas 18 origens finais não sobrepostas |
| 30 d | UNVALIDATED_MODEL | Melhoria incerta, calibração insuficiente, ECE alto, cobertura agregada fraca e quatro origens finais |
| 90 d | INSUFFICIENT_EVIDENCE | Drift na origem atual, 20 origens OOS agregadas, quatro finais, calibração insuficiente e ausência de melhoria |

7/30 dias incluem estimativas em `experimental_diagnostics`, rotuladas
`EXPERIMENTAL_NOT_VALIDATED`, para pesquisa. Em 90 dias o drift bloqueia também esse
diagnóstico na origem capturada. Não se preenchem campos ausentes com estimativas
arbitrárias. Probabilidades dos cenários condicionais continuam null; classes de
retorno final são outro objeto estatístico.

Limites materiais: apenas um ativo e uma captura; metadados atuais de exchangeInfo;
sem universo de delistagens point-in-time; sem medição de publicação histórica ou
garantia contra revisão; sigma e escala raiz do tempo são escolhas de modelo;
dependência residual entre origens; amostras raras de Wyckoff; drift avaliado por
distância padronizada simples; cobertura empírica não garante eventos extremos;
sem custos, slippage, execução ou retorno financeiro de estratégia. Os limiares de
abstinência são política predefinida, não certificação estatística universal.

## Testes, artefatos e arquivos

Testes adicionados cobrem parsing/integridade, features e disponibilidade, prefixos,
alinhamento exato de alvos, purge/embargo, scaler sem vazamento, calibração com suporte
insuficiente, soma de probabilidades, insuficiência histórica, seeds, parâmetros
JSON, serialização, incompatibilidade/revisão de históricos, gates sem melhoria e
integração CLI/schema v3. Testes antigos e exemplos v1/v2 são preservados.

Verificação final executada: **157 testes offline aprovados**, incluindo a suíte
anterior. Ruff lint e verificação de formatação passaram; mypy strict passou nos
26 arquivos-fonte. A integração real v3 retorna status operacional `ok`, mantém
D1/H4/H1 descritivos e incorpora os três horizontes com os status de abstinência
acima. Qualidade operacional `ok` não significa validação preditiva.

O snapshot multitemporal integrado foi coletado em 12/10/2026 com corte histórico
fixado em 11/10/2026 19:49:42.394 UTC e 250 candles fechados por intervalo. Horário
do servidor e exchangeInfo refletem a coleta em 12/10, não metadados históricos.
Snapshot canônico SHA-256:
`7d6b4857c0a85a474fcf2ca874dbb6ed52ef4ed237eed1f66a2fa4304a587571`.
Resultado integrado canônico SHA-256:
`83cfa4a219a927c476a98c5bdbab31737dd043794dc700fb9e9b282fdd238c39`.

<!-- ROOT_COMMIT_RECORD: registrar commit após publicação/verificação do GitHub. -->

Novos módulos estão em `src/market_intelligence/prediction/`: contracts, dataset,
features, targets, models, validation, metrics, training e inference. Integração
altera engine/CLI/render e inclui schema v3. Correções se concentram em estrutura e
parsing; dependências/CI/instruções/documentação acompanham a entrega. Exemplos reais
incluem dataset, config, bundle, métricas, previsão JSON/texto, análise integrada
JSON/texto, snapshot multitemporal, registro operacional e auditoria.
O roteiro em [examples/TASK03_DEMO.md](examples/TASK03_DEMO.md) permite reproduzi-los.

## Recomendações para a próxima etapa

1. Ampliar população e período com múltiplos ativos, ciclos e fontes, universo
   point-in-time de listagens/delistagens e monitoramento de revisões/latência.
2. Reservar prospectivamente calibração e holdouts longos com quantidade suficiente
   de origens não sobrepostas, especialmente 30/90 dias; não relaxar gates para
   fazer o exemplo retornar probabilidades públicas.
3. Investigar deterioração da logística e instabilidade dos modelos longos com
   seleção de features e regularização em validação temporal aninhada. Uma nova
   decisão exige outro holdout preservado, sem tuning sobre estes testes.
4. Validar cobertura e caudas por regime, melhorar detecção multivariada de drift
   e registrar incerteza de calibração e comparações com dependência temporal.
5. Criar registry de modelos/datasets com instante real de criação, integridade,
   aprovação, revogação e previsão prospectiva registrada antes dos alvos.
6. Só depois avaliar backtesting de estratégias com custos/slippage, liquidez,
   risco e múltiplos testes controlados. Qualidade de probabilidades não equivale
   a rentabilidade. Nenhuma execução de ordens foi implementada.
