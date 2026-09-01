# ADR-001 — Monorepositório modular

Status: aceito

## Contexto

Memoria Admin e BDR Explorer precisam compartilhar uma experiência de operação, mas pertencem a domínios diferentes e poderão ser distribuídos separadamente.

## Decisão

Adotar um monorepositório modular com três aplicações:

- `server-shell`: composição, navegação e autenticação de entrada;
- `memoria-admin`: administração do serviço Memoria.ia;
- `bdr-explorer`: observação visual read-only do BDR.

Contratos e identidade visual ficam em pacotes neutros. Integrações com os cores ficam em adaptadores separados.

## Restrições

- Memoria Admin não importa BDR Explorer.
- BDR Explorer não importa Memoria Admin.
- A shell não implementa regras de memória ou persistência.
- O BDR Explorer não lê WAL, snapshot ou estruturas privadas.
- Credenciais nunca são compartilhadas implicitamente entre módulos.
- Rotas de API são versionadas e preservam a origem dos dados.

## Consequência

Os módulos podem evoluir juntos agora e ser extraídos mais tarde por divisão de diretório e histórico, sem reescrita do domínio.
