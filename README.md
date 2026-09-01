# Memoria.ia Server

Painel de gerenciamento da Memoria.ia e ambiente visual do Resolutive DB (BDR).

Este repositório reúne os dois produtos durante a fase de integração, mantendo fronteiras explícitas para que possam ser separados posteriormente sem reescrever o Core.

## Estrutura

```text
apps/
  server-shell/       # composição, navegação e inicialização
  memoria-admin/      # interface administrativa da Memoria.ia
  bdr-explorer/       # interface visual e observabilidade do BDR
packages/
  contracts/          # contratos compartilhados, versionados e sem dependência de UI
  design-system/      # identidade visual e componentes comuns
adapters/
  memoria/            # integração somente por API pública da Memoria.ia
  bdr/                # integração somente por API pública do BDR
docs/
  architecture/       # decisões, limites e plano de extração
```

## Princípios

- Memoria.ia continua dona da memória, semântica e estado lógico.
- BDR continua dono da persistência e do espaço físico de endereçamento.
- As interfaces consomem contratos públicos; não acessam internals, WAL ou snapshots diretamente.
- `server-shell` compõe os módulos, mas não contém regras de domínio.
- Cada módulo possui manifesto, testes e rotas próprias.
- A primeira fase é local e read-only para o Explorer.
- Operações administrativas futuras exigirão autenticação, escopos e auditoria.

## Módulos de origem

| Módulo | Origem | Estado importado |
|---|---|---|
| Memoria Admin | `marceloroldao/memoria.ia` | Web UI Enterprise da branch `main` |
| BDR Explorer | `marceloroldao/resolutive-DB` | `feature/resolutive-db-explorer-v0.1` |

Os arquivos importados mantêm sua origem documentada em `docs/architecture/MIGRATION.md`.

## Estado

Base de integração inicial. O objetivo imediato é preservar o que já funciona, unificar a navegação e estabelecer contratos que permitam evolução independente.

## Planejamento

- [Roadmap de evolução](docs/ROADMAP.md)
- [Fronteira de licenciamento](docs/architecture/ADR-002-LICENSING-BOUNDARY.md)
- [Rascunho dos planos](docs/PLANS_DRAFT.md)

- [OFF.IA como serviço do provedor](docs/OFFIA-PROVIDER-ONBOARDING.md)
- [Decisão arquitetural do serviço OFF.IA](docs/architecture/ADR-003-OFFIA-PROVIDER-SERVICE.md)
