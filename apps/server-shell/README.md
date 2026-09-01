# Server Shell

Camada de composição do Memoria.ia Server.

## Responsabilidades

- navegação entre Memoria Admin e BDR Explorer;
- entrada única local em `http://127.0.0.1:8780`;
- encaminhamento das APIs por namespaces explícitos;
- health agregado sem expor endereços internos;
- configuração dos serviços por variáveis de ambiente.

A shell não armazena memórias, não interpreta semântica e não acessa internals do BDR.

## Rotas

| Rota | Destino |
|---|---|
| `/` | central de gerenciamento |
| `/admin/memoria` | Memoria Admin |
| `/explorer/bdr` | BDR Explorer |
| `/api/v1/*` | API pública da Memoria.ia |
| `/api/bdr-explorer/v1/*` | API do BDR Explorer |
| `/api/server/v1/health` | saúde agregada |

## Executar

Inicie a API da Memoria.ia e o BDR Explorer em seus processos próprios. Depois, na raiz deste repositório:

```bash
python apps/server-shell/server.py
```

Por padrão:

- Memoria.ia: `http://127.0.0.1:8000`;
- BDR Explorer: `http://127.0.0.1:8765`;
- Server Shell: `http://127.0.0.1:8780`.

Os endereços podem ser alterados pelas variáveis documentadas em `.env.example`.

## Limite arquitetural

A shell é descartável do ponto de vista dos módulos: ambos continuam executáveis de forma independente. O proxy aceita somente os dois namespaces registrados e não funciona como proxy aberto.
