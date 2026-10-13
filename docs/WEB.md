# Aplicação web — execução, contratos e operação

O dashboard integra o motor Python existente a FastAPI, React/TypeScript/Vite e
Lightweight Charts. Nenhum resultado quantitativo é substituído no navegador.
Consultas não treinam modelos e não executam operações na Binance.

Lightweight Charts utiliza licença Apache 2.0 compatível com esta distribuição;
a atribuição nativa da biblioteca permanece habilitada no gráfico. O projeto
preserva sua licença MIT e dependências frontend ficam registradas no lockfile.

O servidor atende Binance **spot**, com H1/H4/D1. W1 e futuros estão indisponíveis
no motor atual. A API informa que a disponibilidade de futuros não foi consultada;
isso não significa que o símbolo não exista nesse mercado.

## Instalação e início rápido

Requisitos: Python 3.11 ou superior, Node.js 22 ou 24, npm e acesso aos endpoints
públicos Binance para modo live. Não é necessária chave de API. Na raiz:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
cd frontend
npm ci
npm run build
cd ..
bash scripts/start-web.sh
```

Abra **http://127.0.0.1:8000** no navegador. Digite `BTCUSDT`, clique em Analisar e
acompanhe as etapas efetivamente informadas pelo backend. O resultado abre sem
recarregar a página. API/OpenAPI: **http://127.0.0.1:8000/docs** e
**http://127.0.0.1:8000/openapi.json**.

O script exige `.venv` e `frontend/dist/index.html`; não instala dependências nem
compila silenciosamente. Seu modo padrão é live e não carrega exemplos ou modelos
automaticamente. Sem bundle, estrutura/indicadores/cenários permanecem disponíveis
quando os dados são íntegros; probabilidades são explicitamente indisponíveis.

Em Windows, ative `.venv\Scripts\Activate.ps1`, compile pelo mesmo npm e inicie
diretamente, configurando o build:

```powershell
$env:MIE_FRONTEND_DIST = (Resolve-Path frontend/dist).Path
python -m market_intelligence.web --host 127.0.0.1 --port 8000
```

## Replay histórico e modelos existentes

Para visualizar a captura real arquivada da Task 03 e suas métricas/modelo:

```bash
bash scripts/start-web-example.sh
```

Esse preset define snapshot, bundle e dataset presentes em `examples/task03-btc-*`.
O frontend exibe **REPLAY HISTÓRICO**, corte UTC e a informação de que não é uma
cotação atual. Apenas o símbolo da captura é atendido. Dados reais históricos
não viram dados live; fixtures sintéticas continuam rotuladas `SIMULATED`.

Os modelos BTC da Task 03 não demonstraram vantagem sustentada. Uma aplicação
funcional pode corretamente mostrar `UNVALIDATED_MODEL` ou `INSUFFICIENT_EVIDENCE`,
com probabilidades e magnitude públicas `null`. Diagnósticos experimentais ficam
em uma expansão própria, identificados como pesquisa não validada.

Para usar um modelo salvo em uma consulta live, configure ambos os artefatos:

```bash
export MIE_MODEL_BUNDLE="$PWD/examples/task03-btc-model.json"
export MIE_PREDICTION_DATASET="$PWD/examples/task03-btc-dataset.json"
bash scripts/start-web.sh
```

Não defina `MIE_REPLAY_SNAPSHOT` nesse modo. O serviço reutiliza o dataset configurado
quando seu corte é compatível e pode coletar histórico D1 atualizado, mantendo o
início da coorte e verificações existentes de checksum/disponibilidade. Dados
alterados, insuficientes, incompatíveis ou sem modelo para o símbolo provocam
abstinência. O bundle é carregado uma vez; não há fitting por consulta.

Treinamento e seleção continuam em comandos CLI separados:

```bash
market-intelligence train examples/task03-btc-dataset.json \
  --config examples/task03-config.json --output /tmp/btc-model.json \
  --report /tmp/btc-evaluation.json
```

Trocar modelo/dataset exige reiniciar o servidor. Um artefato treinado não é,
por isso, um modelo validado. Consulte `TASK03_RULES.md` e `TASK03_REPORT.md`.

## Desenvolvimento com Vite

Dois terminais, ambos na raiz do projeto inicialmente:

```bash
# Terminal 1: API, sem build estático.
source .venv/bin/activate
python -m market_intelligence.web --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2: frontend com proxy para API/OpenAPI.
cd frontend
npm ci
npm run dev
```

Abra **http://localhost:5173**. O proxy encaminha `/api`, `/docs` e `/openapi.json`
ao backend, evitando requisições diretas do navegador à Binance. Para outra porta
de API, defina `MIE_API_PROXY_TARGET=http://127.0.0.1:8001` ao iniciar Vite.

## Uso em Android

O telefone utiliza Chrome ou outro navegador atual; não precisa de Python,
Node, Termux ou chaves Binance. O servidor roda no computador ou host de deploy.

Na mesma rede Wi-Fi, depois do build:

```bash
MIE_HOST=0.0.0.0 MIE_PORT=8000 bash scripts/start-web.sh
```

No Android, abra `http://IP-DO-COMPUTADOR:8000`; `127.0.0.1` no telefone aponta para
o próprio telefone. A porta precisa estar acessível na rede local. A aplicação
continua usando API e frontend na mesma origem. O servidor não exige autenticação
de usuários; escolha a rede/interface em que ele será disponibilizado.

O layout foi projetado para 360 px: busca compacta, navegação horizontal, alvos de
toque confortáveis, gráficos com pinça/pan, painéis expansíveis e rolagem de tabelas
dentro dos painéis. Alternar abas preserva o resultado e não solicita novo treino
ou análise. Tema claro/escuro é uma preferência local do navegador.

O manifest e ícones preparam uso standalone/PWA. Para um deploy instalável, use
HTTPS e os critérios do navegador. A opção Adicionar à tela inicial pode criar
um atalho em outros ambientes. Não há service worker para cache de dados/API;
consulta e navegação offline não são prometidas.

## O que cada painel representa

| Painel | Origem e interpretação |
| --- | --- |
| Visão geral | Fechamento H1, volume do candle, ATR, regime e síntese direta de estados/evidências do motor |
| Gráfico | OHLCV fechado, EMA20/50, RSI14 e eventos/níveis retornados pelo backend |
| Estrutura | Pivôs, HH/HL/LH/LL, BOS/CHoCH e níveis com estado e disponibilidade |
| Wyckoff | Faixas, testes e eventos reconhecidos por regras; interpretações permanecem hipóteses |
| Previsões | Classes de retorno final em 7/30/90 dias, gates, probabilidade/magnitude quando disponíveis |
| Auditoria | Modelo/dataset, períodos, métricas OOS agregadas, teste final, baseline comparável, calibração e cobertura |

Preço de referência **não é ticker instantâneo**. Variação percentual compara os
dois últimos fechamentos H1 e não é variação de 24 horas. Volume é do ativo base
no último H1. Timestamps são mostrados em UTC. Qualidade operacional `ok` não
significa elegibilidade estatística.

Um evento tem posição histórica, primeira detecção, confirmação/invalidação e
disponibilidade da revisão. O marcador causal é colocado no candle após cujo
fechamento seu estado se tornou disponível; usa o preço real do evento como coordenada vertical e etiqueta. Níveis começam na disponibilidade. Origens retrospectivas ficam desligadas
por padrão e são identificadas quando habilitadas. O inspetor mostra todas essas
datas separadamente; não apresenta uma confirmação futura como sinal precoce.

Intervalo preditivo é distribuição de retorno final, não suporte/resistência ou
limite garantido de preço. A interface não constrói trajetórias ou fan charts a
partir de quantis finais isolados. Probabilidades indisponíveis não viram zero,
50% ou percentuais de cenário. Brier/log loss menores são melhores; comparar
modelos com folds diferentes exige o baseline na mesma população.

## API versionada

| Método e endpoint | Função |
| --- | --- |
| `GET /api/v1/health` | Saúde, modo, versões e capacidades suportadas |
| `GET /api/v1/symbols?q=BTC` | Até 100 símbolos spot consultados, com metadados |
| `GET /api/v1/symbol-validation/BTCUSDT` | Disponibilidade spot e distinção de futuros não consultados |
| `POST /api/v1/analyses` | Validar entrada e criar job de análise; HTTP 202 |
| `GET /api/v1/jobs/{job_id}` | Estado real, etapa, falha ou ID do resultado |
| `GET /api/v1/analyses/{analysis_id}` | Contrato web completo e compacto |
| `GET /api/v1/analyses/{analysis_id}/engine` | JSON v3 integral do motor, com diários |
| `GET /api/v1/analyses/{analysis_id}/ohlcv?interval=H1` | Candles/séries/eventos do intervalo |
| `GET /api/v1/analyses/{analysis_id}/indicators` | Indicadores por timeframe |
| `GET /api/v1/analyses/{analysis_id}/diagnostic` | Regime, evidências, conflitos e limitações |
| `GET /api/v1/analyses/{analysis_id}/structure` | Estrutura por timeframe |
| `GET /api/v1/analyses/{analysis_id}/wyckoff` | Wyckoff por timeframe |
| `GET /api/v1/analyses/{analysis_id}/scenarios` | Cenários condicionais |
| `GET /api/v1/analyses/{analysis_id}/predictions` | Previsões e abstinências |
| `GET /api/v1/analyses/{analysis_id}/model-quality` | Métricas e metadados do modelo |

Exemplo de submissão:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","market":"spot","bars":250}'
```

Consulte o `job_id` retornado até `completed` ou `failed`; em sucesso, consulte
o `result_id` em `/analyses/{id}`. Formato de erro:

```json
{"error":{"code":"SYMBOL_UNAVAILABLE","message":"Descrição da falha","request_id":"identificador"}}
```

Símbolos são normalizados para maiúsculas e precisam ter 5–30 caracteres
alfanuméricos. `bars` aceita 100–500 candles por intervalo, com padrão 250.
Mercado `futures` e
intervalo `W1` retornam erro explícito; não há conversão automática de mercado.
Nenhum endpoint de treinamento, ordens ou execução arbitrária é exposto.

Pydantic valida fronteiras do backend, o JSON Schema v3 valida o resultado do
motor e Zod verifica a resposta no frontend. O contrato compacto omite somente
diários duplicados/histórico de tendência, preservando valores e eventos atuais.
Exportar JSON no dashboard salva esse contrato; `/engine` fornece o resultado
integral para auditoria causal.

## Configuração

| Variável | Uso |
| --- | --- |
| `MIE_REPLAY_SNAPSHOT` | Caminho local explícito para modo replay; ausente significa live |
| `MIE_MODEL_BUNDLE` | Bundle JSON previamente treinado e validado como artefato |
| `MIE_PREDICTION_DATASET` | Dataset compatível; obrigatório em conjunto com o bundle |
| `MIE_FRONTEND_DIST` | Diretório de build servido pela API |
| `MIE_CORS_ORIGINS` | Origens HTTP(S) explícitas separadas por vírgula, sem barra final ou `*` |
| `MIE_PYTHON` | Executável Python usado pelos scripts de inicialização |
| `MIE_HOST` / `MIE_PORT` | Bind/porta usados por `scripts/start-web.sh` |
| `MIE_API_PROXY_TARGET` | Destino do proxy Vite, apenas desenvolvimento |
| `MIE_TEST_PYTHON` / `MIE_CHROMIUM` | Executáveis usados por Playwright, apenas testes |

Configuração de modelo é por processo e símbolo do bundle. Um modelo BTC não é
aplicado a ETH/JUP. Paths inválidos ou apenas um dos dois artefatos configurados
impedem inicialização. Sem artefatos, o comportamento normal é abstinência.

## Cache, timeouts e confiabilidade

Cache de análise: 30 s por símbolo/janela/modo/assinatura de artefatos. O timestamp
original é preservado em um cache hit. Ao expirar, outra consulta recolhe dados;
não há atualização automática da tela ou streaming de preço. Resultados/jobs
finalizados são retidos por 20 min, sujeitos a 16 registros e orçamento de JSON
retido de 64 MiB com descarte LRU. Reiniciar o processo remove tudo.

Diretório spot: cache de 5 min. Histórico preditivo D1: cache por origem diária.
Não há persistência ou compartilhamento entre processos. O orçamento serializado
não representa limite rígido de RSS; modelos/datasets e processamento também
ocupam memória.

Há dois workers de análise, oito pendências, 30 submissões por minuto/cliente e
180 leituras API por minuto/cliente, em memória. Corpo HTTP é limitado a 8 KiB
antes do parser, inclusive streaming. Recebimento tem timeout de 15 s; consultas
têm orçamento de 90 s; cada GET upstream web é limitado a até 8 s, sem retries
implícitos nesse adaptador. O cliente CLI mantém sua própria política documentada.
O frontend limita
cada chamada HTTP e o polling total. Erros não geram dados substitutos.

Logs são JSON com request/job/result IDs, etapa, código, duração e status HTTP.
Não registram chaves privadas, snapshots completos ou treinamento no navegador.
Respostas API usam `Cache-Control: no-store`; o cache de servidor permanece
explícito no contrato. São aplicados headers contra sniffing e framing.

## Testes e demonstração

Instale os extras necessários e execute:

```bash
python -m pip install -e '.[dev,predictive,web]'
python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Playwright serve o build pronto pela API de teste em `8001`, com provider sintético
explicitamente rotulado e sem consultas Binance. Screenshots desses testes
recebem prefixo `synthetic-`. São verificações de software, não evidência de
previsão nem de acesso live. `MIE_CHROMIUM` permite usar Chromium já instalado;
`MIE_TEST_PYTHON` define o Python com os extras disponíveis.

Para demonstração real, inicie o serviço live e consulte BTCUSDT. Para demonstração
histórica, use o preset de replay e mantenha seu banner/corte visíveis. Erro de
fonte, símbolo inválido e histórico insuficiente devem ser apresentados sem
fallback. Resultado verificado: 188 testes Python, 40 Vitest e 30 Playwright passaram.
Consulta real BTCUSDT e screenshots estão em `TASK05_REPORT.md` e
`examples/task05/`. Para repetir a captura live com navegador instalado:

```bash
node scripts/capture-web-demo.cjs
```

O script exige serviço live iniciado e não intercepta requisições ou injeta dados.

## Deploy futuro

Compile `frontend/dist`, instale o extra `web` e execute um processo API com
`MIE_FRONTEND_DIST` apontando para esse build. Sirva o domínio por HTTPS em proxy
frontal, mantendo API e SPA na mesma origem. Configure os paths dos artefatos de
forma explícita e reinicie quando forem atualizados. Não publique servidor Vite
de desenvolvimento como aplicação de produção.

O serviço atual é adequado a uma instância: jobs, cache e rate limits não são
distribuídos. Escalar para vários processos/hosts exige armazenamento/coordenação
compartilhados; isso não foi introduzido sem necessidade nesta etapa. O servidor
não inclui autenticação administrativa e não expõe treinamento. Autorização de
acesso ao deployment pode ser definida no proxy conforme o uso pretendido.

Não houve reconstrução do motor, melhoria artificial das métricas ou validação
preditiva adicional. A Task 04 separada não foi localizada na base inspecionada.
Futuros, W1, registry distribuído, streaming e avaliação prospectiva mais ampla
continuam como trabalho futuro; não são simulados na interface.
