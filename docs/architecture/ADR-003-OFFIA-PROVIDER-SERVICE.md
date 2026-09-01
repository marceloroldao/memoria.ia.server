# ADR-003 — OFF.IA oferecida como serviço do provedor

Status: aceito

## Decisão

A OFF.IA é distribuída aos clientes como aplicativo de IA oferecido por provedores que operam uma instalação licenciada do Memoria.ia Server.

O cliente baixa a OFF.IA e a configura com informações fornecidas pelo seu provedor. O aplicativo é registrado como dispositivo interno no servidor daquele provedor.

## Consequências

- o licenciamento comercial principal ocorre entre a Central futura e o provedor;
- o relacionamento com o cliente final é administrado pelo provedor;
- o servidor precisa de cadastro interno de clientes, assinaturas e dispositivos;
- a OFF.IA precisa de fluxo simples e seguro de ativação;
- a aplicação continua local-first;
- o servidor deve suportar personalização do provedor;
- os direitos internos do cliente não devem ser confundidos com a licença principal do servidor.

## Separação de planos

Existem dois níveis comerciais distintos:

1. planos da Central para licenciar o Memoria.ia Server do provedor;
2. ofertas que cada provedor cria para seus próprios clientes de OFF.IA.

O primeiro será definido pela futura camada administrativa. O segundo pertence à administração interna do provedor e deve respeitar os limites da licença do servidor.
