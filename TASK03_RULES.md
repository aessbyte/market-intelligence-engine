# Task 03 — Regras quantitativas e protocolo temporal

## População e disponibilidade

Uma população corresponde a `exchange=binance`, `market=spot`, símbolo e D1.
O dataset mantém rows originais, UTC em epoch ms, endpoint, corte do servidor,
versão e SHA-256 canônico. Não há preenchimento, ordenação corretiva ou fallback
sintético. Candles incompletos são excluídos e contados; gaps/timestamps/OHLCV
inconsistentes impedem treino. Histórico curto é registrado sem presumir data de
listagem. Recortes exigem início UTC e motivo, preservando hash/qualidade do pai.

Disponibilidade assumida de um candle fechado: `close_time_ms + 1`. Essa é uma
convenção teórica, não uma medição da publicação histórica. Binance pode revisar
dados, e `exchangeInfo` não é point-in-time. O hash não autentica o fornecedor.

## Features causais

Após 100 candles, cada origem D1 gera 65 variáveis ordenadas. Indicadores usam
janela anterior de até 250 candles, com as sementes da Etapa 1. EMA/RSI/ATR podem
variar com a janela; treinamento e previsão usam a mesma configuração.

Incluem distância/inclinação EMA/SMA em ATR, RSI/100, MACD(12,26,9)/ATR,
ATR/fechamento, log-retornos 1/7/30, força relativa 5/20 dias, volatilidade diária
observada, compressão de amplitude 5 dias contra os 20 anteriores, largura de
Bollinger, eficiência, volume relativo e z-score (contra os 20 anteriores),
log(1+volume cotado), deslocamento/participação, liquidez, persistência e one-hot
do regime. Ausências usam zero acompanhado de indicador de ausência.

Estrutura e Wyckoff são calculados pelas regras existentes; o diário é consumido
na ordem de disponibilidade. Nunca se consulta o estado final retrospectivo.
Pivôs usados em distâncias já precisam estar confirmados. BOS/CHoCH e sinais
Wyckoff têm contagens separadas de candidatos/confirmados em janela de 12 dias;
invalidado deixa de contar. Posição/largura da faixa usam seus limites congelados.
Cada scalar registra fonte/derivação e timestamp de disponibilidade.

MACD usa EMA12−EMA26 e EMA9 desse diferencial, com sementes SMA; sem biblioteca
técnica externa. Sigma é desvio populacional dos log-retornos dos últimos 30 dias
por padrão, não anualizado. Persistência começa após o aquecimento declarado.
H1/H4 permanecem descritivos: não se inventa histórico multitemporal de features.
O histórico dos eventos precisa preservar o contexto completo disponível desde
o início do dataset; uma janela isolada de 250 candles não é equivalente.

## Alvos

Para origem `t` e horizonte `h ∈ {7,30,90}` dias corridos:

`r_log = log(C[t+h]/C[t])`, `b = k × sigma[t] × sqrt(h)`, com `k=0,5` predefinido.

* Bearish: `r_log < −b`.
* Neutral: `−b ≤ r_log ≤ b`.
* Bullish: `r_log > b`.

As classes cobrem todos os retornos válidos e são exclusivas. Limites dependem
do ativo/volatilidade/horizonte, sem otimização no teste. Sigma zero/inválido ou
endpoint ausente não gera alvo. Endpoint exato: origem + h×86.400.000 ms.
Também são registrados retorno aritmético `C[t+h]/C[t]−1`, máxima excursão
favorável por highs e adversa por lows **dos candles posteriores**, separadas do
retorno final. Não são features de entrada. O alvo só fica disponível no endpoint.

## Modelos e calibração

Configuração fixa, seed 42:

* Frequências: contagens do treino com prior simétrico Dirichlet(1,1,1),
  suavização explícita para classes raras e log loss finito.
* Momentum: frequência de classes no treino condicionada ao sinal do log-retorno
  observado de 7 dias; bins sem amostras usam a frequência global do treino.
* Logística multinomial: StandardScaler ajustado só no treino; softmax, solver
  lbfgs, C=0,1, máximo 600 iterações; não convergência impede uso.
* Gradient boosting: no mínimo 1.500 linhas de treino, 40 árvores por classe,
  profundidade 2, taxa 0,05, subsample 1, sem split aleatório/early stopping.

Todos usam os mesmos blocos quando disponíveis. Modelos não lineares indisponíveis
nos primeiros folds são comparados dentro dos folds comuns; contagens distintas
não autorizam comparar médias agregadas como populações idênticas.

Seleção pela menor Brier na validação, depois log loss; empate favorece simplicidade.
O teste não seleciona vencedor. Temperatura escalar ajustada exclusivamente na
calibração, minimizando log loss em grade fixa de 0,5 a 3, incluindo 1.
Exigir no mínimo 60 linhas, 10 por classe (configuráveis) e 10 origens espaçadas
pelo horizonte para ajustar essa temperatura. Sem suporte, manter temperatura 1,
calibração indisponível e previsão sem validação; registrar contagens e razões.
Artefatos JSON guardam coeficientes, scaler, árvores, temperatura e metadados;
inferência não executa pickle nem requer sklearn. Dependências de treino são fixadas.

## Walk-forward e teste final

Treino inicial expansivo de 730 dias, validação de 180, calibração de 180 e teste
de 365; embargo padrão de 7 dias antes de cada bloco seguinte. Passo de expansão:
365 dias. O último bloco emitido é o teste final, congelado antes da avaliação;
nunca se refaz o modelo após observar seus resultados. Residual só é aceito com
contagem mínima. Blocos são definidos por tempo, sem shuffle de linhas.

Em cada fronteira, manter apenas `target_available_ms < primeira origem do bloco
seguinte`. Também purgar alvos que alcancem o fim nominal do teste, evitando
janelas de alvo compartilhadas entre holdouts. As features podem usar passado
anterior ao bloco (isso estaria disponível); normalizadores não podem ajustá-lo
com observações posteriores ao treino. Scalers, calibração e distribuições de
retorno são registrados com seus períodos específicos.

Reuso de um holdout antigo em um treino de fold posterior é válido somente após
disponibilidade de seus alvos. Configurações e lista de candidatos são fixadas
antes da avaliação; resultados antigos não fazem tuning automático.

## Qualidade probabilística e magnitude

Brier multiclass = média da soma dos três erros quadráticos (escala 0–2).
Log loss = média de `−log(p_classe_real)`, clipping numérico 1e−15.
Calibração: 10 bins por classe, média prevista, frequência observada e contagem;
bins vazios têm valores null. ECE é a média dos três erros absolutos ponderados.
Acurácia é informada separadamente, sem substituir as métricas probabilísticas.

Comparação pareada seleciona origens espaçadas pelo horizonte e calcula melhorias
de Brier/log loss contra baseline escolhido **na validação**, com bootstrap
percentil (1.000 reamostragens, seed fixa). Limites de 95% inteiramente positivos
nas duas métricas são uma condição conservadora; não demonstram vantagem durável.
Não sobreposição reduz dependência, mas não prova independência estatística.

Magnitude: distribuição empírica de `z = r_log/(sigma_origem×sqrt(h))` no treino,
separada por classe. Misturar distribuições usando probabilidades estimadas e
transformar via `exp(z×sigma_atual×sqrt(h))−1`. Reportar quantis 5/10/50/90/95%,
intervalo nominal 80% (10–90), mediana e massa abaixo de −20% de retorno final.
Medir cobertura e erro fora da amostra. Intervalos não são suportes/resistências,
nem preços garantidos; a regra de raiz do tempo é hipótese de escala, não lei.

## Abstinência e integração

Sem população real, histórico/blocos/classes suficientes, melhoria sustentada,
calibração aceitável, testes não sobrepostos ou estabilidade temporal, retornar
`INSUFFICIENT_EVIDENCE` ou `UNVALIDATED_MODEL`. Drift por distância padronizada,
regime raro, baixa liquidez, símbolo/fonte incompatíveis, dados/modelo futuros ou
origem diária desatualizada também impedem uso. Gates/configuração estão no artefato.

Probabilidades públicas e magnitude validada ficam null quando os gates falham.
Estimativas computadas podem aparecer em `experimental_diagnostics`, explicitamente
sem validação e para pesquisa. Elas não substituem campos ausentes.
Uma validação histórica é restrita à população/períodos avaliados, nunca autorização
de negociação ou alegação de vantagem geral.

Origem da previsão é o último fechamento D1 + 1, com preço de referência diário;
`as_of_ms` identifica emissão/análise. Disponibilidade do bundle considera dataset
e todos os alvos de avaliação. Não se pode aplicar bundle posterior em replay
antigo. Schema v3 integra previsões; schemas v1/v2 preservam seus contratos.
As probabilidades de classes de retorno final são distintas dos cenários
condicionais por regras de estrutura/Wyckoff, cujos campos continuam null.
