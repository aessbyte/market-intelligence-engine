# Task 05 — Inspeção anterior à integração web

Base local/remota: `fcf7118437676c48f1f004cad75106ad07e46aa7`, 89 arquivos,
Python 0.3.0. README, ARCHITECTURE, AGENTS, auditorias/relatórios Tasks 02/03,
schemas e interfaces inspecionados antes de implementar. **157 testes passaram**.
GitHub main e histórico recente não contêm Task 04; não se declara essa etapa
implementada ou sua validação concluída. Task 03 inclui auditorias adversariais,
mas elas não equivalem a uma Task 04 separada.

Não há frontend nem servidor HTTP existente. CLI e `engine.analyze` são funcionais;
o motor permanece puro, tipado e sem rede. Python standard library na análise e
inferência; dependências ML opcionais só no treinamento. Ambiente dispõe de Node
24, npm 11, Chromium, Playwright, FastAPI/Pydantic/Uvicorn/HTTPX.

## Integração escolhida

* FastAPI versionada em `/api/v1`, como adaptador separado do motor. React,
  TypeScript e Vite em `frontend/`; Lightweight Charts para OHLCV.
* Usar `analyze(..., result_version=3)` e helpers matemáticos existentes. Nada de
  heurísticas substitutas, treinamento por requisição ou operações Binance.
* Contrato web compacto omite diários duplicados da resposta principal, sem
  alterar valores/estados. JSON integral do motor continua disponível por ID.
* Jobs transitórios em memória fornecem progresso real de etapas; cache e limites
  de requisição em memória, sem banco ou serviço adicional.
* Modelos/datasets são configurações locais previamente validadas. Contexto
  histórico, checksum, símbolo e timestamps são respeitados. Indisponibilidade
  permanece explícita; diagnósticos experimentais são separados.
* Spot/H1/H4/D1 são suportados. Futuros e W1 não serão fornecidos ao motor spot
  como se fossem equivalentes. Disponibilidade não conferida é desconhecida.
* Gráfico usa candles fechados e séries do backend. Eventos distinguem posição
  histórica, primeira detecção, confirmação e disponibilidade da revisão.
* SPA e API no mesmo domínio no build; proxy Vite em desenvolvimento. CORS com
  origens explícitas, sem credentials/chaves privadas; treino não tem endpoint.
* Manifest e ícones preparam instalação/atalho standalone, dependente do navegador
  e HTTPS. Não há service worker ou cache offline da análise/API. Falha da fonte não ativa fixtures nem dados simulados.

A autorização explícita da Task 05 supera a proibição antiga de GUI do AGENTS
relativa às etapas anteriores. Regras de dados, causalidade e testes continuam.
