# Regras matemáticas e operacionais — Task 02

Versões: structure-v1, wyckoff-v1, multitimeframe-v1, scenarios-v1. Todos os
limiares são heurísticos explícitos, não estimados por desempenho futuro.
Configuração completa no resultado e em `examples/task02-config.json`.

## Tempo e diário de eventos

Entrada: candles validados de spot, UTC, fechados antes de `as_of_ms` comum.
Reutiliza-se a validação da Etapa 1. Não se preenchem lacunas ou candles abertos.
Módulos aceitam histórico curto para testes; o orquestrador conserva mínimo 100
e exatamente a janela solicitada. Série inválida não gera eventos.

Cada evento guarda id, kind, preço, intervalo, parâmetros, evidências e estado:
`candidate`, `confirmed`, `invalidated`.

* `event_time_ms`: abertura do candle no gráfico; para uma faixa, início da janela observada.
* `detected_at_ms`: primeira detecção, após o fechamento do candle que a tornou observável.
* `available_at_ms`: instante em que **esta revisão de estado** ficou disponível.
* `confirmed_at_ms`/`invalidated_at_ms`: instantes dessas transições, ou null.

Disponibilidade = fechamento inclusivo Binance + 1 ms. Uma revisão só é visível
quando `available_at_ms <= as_of_ms`. `events` é a última revisão por id no corte;
`event_journal` é append-only e conserva candidatos e confirmações anteriores.
Para consultar o passado, filtrar o diário pelo instante e materializar a última
revisão de cada id; não filtrar apenas o estado atual. Uma confirmação posterior
nunca aparece retroativamente como disponível na abertura do candle do pivô.

`confirmed` significa regra satisfeita; não certeza econômica, previsão ou fase.
Eventos confirmados históricos podem permanecer registrados depois da janela de
monitoramento. Cenários só aceitam evidência direcional fresca (12 candles).

## Estrutura

Pivô candidato high: máxima estritamente maior que as `left_bars` máximas anteriores;
low: mínima estritamente menor que as anteriores. Default esquerda=2, direita=2.
Qualquer empate/superação do extremo à direita invalida o candidato. Após observar
todos os `right_bars` candles sem violação, confirmar. Extremos simultâneos são
possíveis; não se inventa a ordem intrabar. Não há zig-zag retrospectivo ou exclusão
de pivôs confirmados quando aparece um pivô mais forte.

Relações com o último pivô confirmado do mesmo tipo: delta=(novo−anterior)/anterior.
Acima da tolerância 0,001: HH/HL; abaixo de −0,001: LH/LL; dentro inclusive: EH/EL.
A relação fica disponível na confirmação do novo pivô, não na sua abertura.

Estrutura por dois highs e dois lows: HH+HL=alta; LH+LL=baixa; EH+EL ou LH+HL
(compressão)=lateralização; demais pares=indeterminado. Um rompimento confirmado
pode atualizar a direção antes do próximo par completo. Quando novos pivôs são
confirmados, a leitura dos pares volta a atualizar a estrutura; não se oculta uma
divergência de pivôs após um CHoCH.

BOS/CHoCH usam o último high/low confirmado **já conhecido antes do candle atual**.
Alta: fechamento > nível×1,001. Baixa: fechamento < nível×0,999. Primeiro fechamento
gera candidato; 2 fechamentos consecutivos além do buffer confirmam. Contra a
direção estrutural anterior alta/baixa: CHoCH; continuidade ou direção anterior
indeterminada: BOS. Evidência registra explicitamente a direção anterior.

Fechar de volta através do nível dentro de 5 candles do primeiro rompimento
invalida o evento e gera `false_break` como observação confirmada. Isso não estima
a probabilidade de falso rompimento. O nível fica novamente elegível a um novo
rompimento, com outro id temporal. Candidato sem confirmação até o quinto candle
é invalidado por timeout. Wick além do nível sem fechamento além do buffer gera
`possible_false_break` candidato, sem afirmar reversão. Níveis são os últimos três
pivôs confirmados de cada lado; guardam id, disponibilidade, relação e estado de uso.

## Faixas Wyckoff

A janela anterior exclui o candle analisado. Default N=40:

* L=min(low), U=max(high), W=U−L, M=(U+L)/2.
* Largura W/M entre 0,003 e 0,25.
* Eficiência = abs(último close−primeiro close)/sum(abs(variações)); máximo 0,35.
* Pelo menos 2 contatos em cada extremo, próximos até 0,1×W. Candles contíguos
  de contato contam como um só episódio, evitando multiplicar artificialmente testes.
* Pelo menos 80% dos fechamentos na região central [L+0,1W,U−0,1W].
* Pelo menos 80% dos candles com volume>0, trades>0 e quote_volume acima do piso
  configurado (default 0). Não é uma medida de profundidade do livro.

Quando a janela satisfaz as condições e o candle atual fecha na faixa, criar
candidato com limites **congelados**. Dois fechamentos líquidos dentro confirmam
a observação de faixa; fechar fora antes de confirmar invalida. O extremo de uma
ruptura não é incorporado retroativamente à faixa para apagar um Spring/Upthrust.

Volume relativo = volume atual / média dos até 20 candles anteriores, excluindo
o atual. Sem baseline, não se declara liquidez suficiente. Candle líquido requer
volume>0, trades>0, piso de quote volume e razão≥0,1. São filtros de observação;
nenhum deles demonstra executabilidade. Avisos guardam timestamp e observações.

## Eventos Wyckoff

Buffer de ruptura: b=0,02W; tolerância de reteste: t=0,1W.

| Interpretação | Observação candidata | Confirmação adicional | Invalidação |
| --- | --- | --- | --- |
| Spring | low<L−b e close em [L,U] | candle posterior fecha acima do high da varredura; origem e confirmação líquidas; razão de volume da confirmação≥0,8 | close<L ou timeout |
| Upthrust | high>U+b e close em [L,U] | posterior close abaixo do low da varredura; mesmos filtros de liquidez/volume | close>U ou timeout |
| SOS | close>U+b | origem com razão volume≥1,2 e corpo/range≥0,5; segundo fechamento além de U+b, líquido, razão volume≥0,8 | close≤U ou timeout |
| SOW | close<L−b | simétrico ao SOS abaixo de L−b | close≥L ou timeout |
| LPS | após SOS confirmado, low em [U−t,U+t], close≥U, volume≤volume do candle original SOS | candle posterior fecha acima do high do reteste, com liquidez/volume suficientes | close<U−t ou timeout |
| LPSY | após SOW confirmado, high em [L−t,L+t], close≤L, volume≤volume original SOW | posterior close abaixo do low do reteste | close>L+t ou timeout |

Sem filtros de força suficientes, SOS/SOW ficam candidatos e não se confirmam
apenas porque o preço continuou. LPS/LPSY não são emitidos sem SOS/SOW confirmado.
Prazo de follow-through: 8 candles; monitoramento/reteste: 12 candles. Não há
correção retrospectiva da posição de entrada. Cada tipo direcional é emitido uma
vez por faixa nesta versão; reattempts dependem de nova faixa. Faixa rompida por
SOS/SOW confirmado passa a invalidated, mantendo o contexto por 12 candles para
ret testes; depois, uma nova faixa requer uma nova janela anterior.

Testes do extremo com fechamento dentro são fatos de preço (`range_lower_test`,
`range_upper_test`). Spring, Upthrust etc. são interpretações desses fatos com
follow-through. Hipóteses sempre `candidate`, fase sempre null: Spring/SOS sugerem
accumulation; Upthrust/SOW sugerem distribution. Se a estrutura conhecida **antes
da detecção da faixa** era alta/baixa, usar reaccumulation/redistribution,
respectivamente. Só eventos não invalidados e recentes sustentam essas hipóteses.
O sistema não mede inventário institucional nem atribui fases A–E.

## Multitimeframe e cenários

D1 contextualiza, H4 mostra desenvolvimento intermediário, H1 mostra detalhes.
Nenhum intervalo tem veto ou peso superior. Registrar concordâncias entre pares,
conflitos e divergências estrutura/indicadores. Consenso estrutural exige três
leituras iguais e dados disponíveis. Candle superior aberto é excluído antes
da análise; eventos posteriores ao corte são rejeitados na integração.

Três cenários, sem exclusividade preditiva:

* Bullish ativo: pelo menos duas estruturas em alta, nenhuma em baixa, evento
  direcional confirmado recente, suporte H1 disponível/preservado e três séries
  íntegras sem aviso de baixa liquidez no último candle. Invalidação: duas
  estruturas em baixa ou fechamento H1 abaixo do último suporte confirmado.
* Bearish: condições simétricas, resistência H1 preservada e invalidação acima dela.
* Neutral ativo: preço em faixas confirmadas em pelo menos dois intervalos, sem
  duas estruturas concordantes em alta/baixa. Invalidação: cenário direcional
  ativo ou ruptura confirmada de faixa em pelo menos dois intervalos.

Sem evidência bastante: awaiting_confirmation. Com condição de invalidação
satisfeita e dados suficientes: invalidated. Dados faltantes/baixa liquidez
impedem ativação e são informados. Evidências opostas não são escondidas quando
um cenário ativa; especialmente, D1 pode conflitar com um range H4/H1.

`probability`, `price_target`, `forecast.calibrated_probability`, intervalo de
retorno, horizonte, versão de modelo e evidência de calibração são null.
`forecast.status=unavailable`. O schema proíbe valores preditivos arbitrários.
