# Server Shell

Camada de composição do Memoria.ia Server.

Responsabilidades permitidas:

- navegação entre Memoria Admin e BDR Explorer;
- autenticação de entrada e encaminhamento de escopos;
- configuração de endpoints dos adaptadores;
- health agregado;
- servir os módulos sob rotas estáveis.

Responsabilidades proibidas:

- armazenar memórias;
- interpretar semântica;
- acessar internals do BDR;
- implementar persistência;
- misturar modelos de dados dos módulos.

A shell será implementada depois da validação isolada dos dois módulos importados.
