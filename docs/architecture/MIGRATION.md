# Registro de migração

## Objetivo

Centralizar a experiência administrativa da Memoria.ia e o BDR Explorer durante sua maturação, sem fundir os domínios ou os respectivos cores.

## Importação inicial

| Destino | Origem | Referência |
|---|---|---|
| `apps/memoria-admin/static` | `marceloroldao/memoria.ia/src/memoria_resolutiva/webui` | `main` |
| `adapters/memoria/product_admin_config.py` | `marceloroldao/memoria.ia` | `main` |
| `apps/bdr-explorer/explorer` | `marceloroldao/resolutive-DB/explorer` | `feature/resolutive-db-explorer-v0.1` |
| testes de cada módulo | respectivos repositórios de origem | mesmas referências |

A migração é por cópia. Nenhum arquivo foi removido dos projetos de origem.

## Regra de evolução

1. Correções específicas do Core continuam no repositório proprietário.
2. Interface, navegação e composição evoluem aqui.
3. Um novo dado visual exige primeiro um contrato público no Core proprietário.
4. Código compartilhado deve permanecer independente dos dois domínios.
5. Alterações portáveis devem ser mantidas dentro do diretório do módulo.

## Extração futura

Um módulo estará pronto para separação quando:

- tiver manifesto e versão próprios;
- depender apenas de contratos publicados;
- possuir testes executáveis isoladamente;
- não importar código do outro módulo;
- não depender da navegação da `server-shell`;
- puder ser empacotado a partir de seu próprio diretório.
