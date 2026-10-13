# Task 05 — Registro de entrega

Execução e testes: 12/10/2026 UTC. Publicação: 13/10/2026 UTC.

Commit da implementação: [`af1774fea300f642cf2f5e7eb3986bec7019ee4b`](https://github.com/aessbyte/market-intelligence-engine/commit/af1774fea300f642cf2f5e7eb3986bec7019ee4b).
Base preservada: `fcf7118437676c48f1f004cad75106ad07e46aa7`.
O commit de evidências contém este registro, a resposta real e quatro screenshots.

* 188 testes Python passaram, incluindo os 157 anteriores.
* 40 testes Vitest e 30 Playwright passaram; TypeScript/Vite compilaram.
* Ruff lint/formatação passaram; mypy strict passou em 34 arquivos fonte.
* O fluxo real Binance/BTCUSDT passou nos seis painéis, desktop e Android emulado
  360 px, sem erros JavaScript ou overflow da página.
* O resultado `5de00e82fbacd4feaacf44ec` usa referência H1 de 82.157,66 USDT,
  corte `1791848542830`, 250 candles fechados por intervalo e modelo
  `model-3703fd3ae9432487` sem retreinamento.
* Probabilidades públicas: 7/30 dias `UNVALIDATED_MODEL`; 90 dias
  `INSUFFICIENT_EVIDENCE`; todos os valores públicos permanecem `null`.

Foram publicados 54 arquivos de código/configuração/documentação na implementação.
Os 89 arquivos da base foram comparados por Git blob: nenhum módulo analítico,
teste anterior ou exemplo anterior mudou. Seis arquivos existentes de docs,
configuração e CI foram ampliados. A conferência final compara os hashes de todos
os arquivos da entrega com a árvore GitHub, incluindo os artefatos binários.

O ambiente local bloqueava sockets; API/browser foram executados em sandbox remoto
com rede. Houve reinícios/limites de memória durante a preparação. A suíte final
foi executada com um servidor estático e um worker de navegador por vez. As quatro
falhas de seletores da primeira suíte estática foram corrigidas e os 30 testes
foram repetidos com sucesso. Nenhuma fixture foi usada para validar acesso live.

Documentação: [WEB.md](docs/WEB.md). Relatório técnico: [TASK05_REPORT.md](TASK05_REPORT.md).
Screenshots: [desktop](examples/task05/real-binance-desktop-overview.png),
[mobile](examples/task05/real-binance-mobile-overview.png),
[previsões](examples/task05/real-binance-mobile-forecasts.png),
[auditoria](examples/task05/real-binance-desktop-audit.png).

Após instalação/build, execute `bash scripts/start-web.sh` e abra
`http://127.0.0.1:8000`; OpenAPI em `/docs`. No Android da mesma rede, use
`MIE_HOST=0.0.0.0 bash scripts/start-web.sh` e `http://IP-DO-COMPUTADOR:8000`.
O sandbox remoto de verificação não é um deployment público permanente.

Pendências documentadas: Task 04 separada ausente na base; futuros/W1 não
suportados; PWA preparada sem offline; deploy HTTPS e validação em aparelho físico;
validação preditiva prospectiva independente antes de alegar vantagem estatística.
