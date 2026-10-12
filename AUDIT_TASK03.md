# Auditoria inicial — Task 03

Base auditada: commit `5a574fb2e1d503b45a9f1aa2403fb328213f5dcb`, branch `main`.
Inspeção anterior à implementação: 55 arquivos, documentação/relatórios das duas
etapas, providers, validação, indicadores, eventos, estrutura, Wyckoff, cenários,
CLI, schemas, testes e exemplos. Suíte inicial: **83 testes passaram**.

## Capacidades verificadas

Coleta spot pública paginada, corte comum do servidor, validação de continuidade
e OHLCV, indicadores e regimes determinísticos, pivôs confirmados com atraso,
BOS/CHoCH, diário append-only de revisões, faixas/Spring/Upthrust/SOS/SOW/LPS/LPSY,
conflitos entre intervalos, cenários condicionais e replay v1/v2 estão operacionais.
Os testes de prefixo comparam o diário completo filtrado pela disponibilidade com
a execução em cada prefixo. Candidatos não são promovidos retroativamente.

## Defeitos e lacunas

1. `structure.py`: timeout de BOS/CHoCH não liberava o identificador do nível no
   conjunto `broken`. Em configuração que exige três fechamentos, um candidato
   expirado podia bloquear para sempre tentativas posteriores no mesmo nível.
   Corrigir antes da extração de features e acrescentar teste de regressão.
2. A fronteira de parsing aceitava booleanos em campos numéricos OHLCV, pois
   `float(True)` é válido em Python. Rejeitar esses valores explicitamente.
3. Não existe treinamento, dataset persistente, features preditivas, alvos,
   walk-forward, calibração, métricas probabilísticas ou modelo quantitativo.
   Slots futuros null são contratos, não funcionalidades estatísticas.
4. `exchangeInfo` só comprova o estado atual. Não há universo histórico de
   listagens/delistagens, autenticação de snapshots ou garantia contra revisões.
5. Histórico padrão de 250 candles é inadequado para evidência independente em
   90 dias. Dados H1/H4 disponíveis em snapshots curtos não cobrem anos de D1.
6. Eventos antigos permanecem no diário como fatos históricos; features devem
   filtrar revisões por disponibilidade e aplicar janela de relevância explícita.
   Não usar o estado final retrospectivo de cada evento.
7. OHLCV não observa inventário institucional, fluxo ou fase Wyckoff verdadeira.
   Confirmação por regra descreve observações; não valida poder preditivo.

Não foi identificado look-ahead na geração sequencial dos módulos existentes;
isso é uma conclusão limitada ao código e às sequências testadas, não garantia da
disponibilidade histórica dos dados da corretora.

### Achados adicionais e correções verificadas

* IDs de `false_break` e `possible_false_break` colidiam para níveis diferentes
  no mesmo candle; passaram a incluir o evento/nível de origem. Testes preservam
  ambas as observações e os diários de cada prefixo. Exemplo BTC Task 02 regenerado.
* O histórico real de 3.342 candles incluiu um D1 de 08/02/2018 cujo close timestamp
  era 1518049694788, em vez do fim diário esperado. Rejeitado sem reparo.
  Recorte explícito de 09/02/2018 em diante: 3.166 candles íntegros; motivo,
  qualidade e hash do pai em `examples/task03-data-audit.json` e no dataset.
* Calibração só passa com linhas/classes suficientes e pelo menos 10 origens
  não sobrepostas; caso contrário temperatura não é ajustada e suporte fica
  indisponível. Contagens diárias sobrepostas não substituem essa evidência.
* Checksum de bundle não validava dimensões/escalas/probabilidades/árvores. Agora
  há validação semântica antes de inferência e traversal de árvores limitado.
* Reiniciar o histórico mudava persistência/contexto de eventos. Inferência exige
  o mesmo início e hash do prefixo histórico do bundle, permitindo extensão à
  direita, mas rejeitando revisões ou contexto reduzido.
* O corte de informação não é o horário real de produção. Bundle/forecast
  explicitam essa convenção; `examples/task03-run.json` registra produção real
  separadamente. Não se alega emissão histórica anterior à criação do artefato.

## Decisão de escopo quantitativo

Primeira população: um símbolo Binance spot, features D1 causais; D1/H4/H1
continuam integrados na análise descritiva. Histórico multitemporal de features
não será fabricado a partir dos snapshots atuais. Treino/validação/calibração/teste
cronológicos, purge por endpoint dos alvos, embargo e contagem de observações
independentes por horizonte. Dados simulados só validam software.

Nenhuma alegação de vantagem será inferida de uma única captura ou amostra.
