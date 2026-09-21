# Roadmap — Memoria.ia Server

Status: planejamento evolutivo

## Visão

O Memoria.ia Server será instalado e operado por provedores, empresas ou organizações para centralizar a administração de suas OFF.IAs e de outros dispositivos internos.

Cada servidor preserva a autonomia local do ecossistema:

- OFF.IA continua funcionando offline;
- Memoria.ia continua dona da memória, semântica e estado lógico;
- BDR continua dono da persistência;
- o servidor coordena dispositivos, sincronização autorizada, observabilidade e roteamento;
- o servidor não é a autoridade comercial que emite sua própria licença.

A licença principal será emitida por uma camada administrativa superior, desenvolvida futuramente em sistema separado.

## Arquitetura em camadas

```text
Central de licenciamento futura
        |
        | licencia, renova, suspende e define limites
        v
Memoria.ia Server do provedor
        |
        | registra e administra internamente
        v
OFF.IAs, computadores, servidores, robôs e dispositivos IoT
```

## Etapa 0 — Base modular

Estado: concluída

- repositório `memoria.ia.server`;
- Memoria Admin importado;
- BDR Explorer importado;
- módulos tecnicamente separados;
- contratos e adaptadores em diretórios próprios;
- server shell com entrada unificada;
- namespaces de API independentes;
- health agregado;
- validação de Python e JavaScript.

## Etapa 1 — Registro interno de dispositivos

Estado: em implementação — Device Registry V1 disponível no Server.

Já implementado no V1:
- identidade persistente do servidor (`server_id`);
- registro local de dispositivos em `server-data`;
- estados pendente, ativo, suspenso e revogado;
- aprovação, suspensão, reativação e revogação;
- heartbeat administrativo com `last_seen`;
- capacidades e versões declaradas;
- trilha de auditoria append-only;
- interface administrativa em `/devices`.

Pendente para concluir a etapa:
- autenticação própria do dispositivo;
- challenge-response;
- certificado interno Ed25519 assinado pelo servidor;
- rotação/revogação de chaves e escopos por dispositivo.

Referência: [Device Registry V1](DEVICE-REGISTRY-V1.md).

Objetivo: permitir que cada servidor administre seus próprios nós.

- identidade única do servidor;
- cadastro e aprovação de dispositivos;
- `device_id` vinculado ao `server_id`;
- chave pública por dispositivo;
- certificado interno assinado pelo servidor;
- tipos: OFF.IA, celular, computador, servidor, robô, sensor e IoT;
- capacidades declaradas: CPU, GPU, NPU, RAM e armazenamento;
- modelos locais disponíveis;
- versões de OFF.IA, Memoria.ia e BDR;
- estados: pendente, ativo, suspenso e revogado;
- última conexão e estado online/offline;
- grupos, nomes e permissões internas;
- limite local preparado para receber `max_devices` da licença.

Critério de conclusão: registrar, aprovar, listar, suspender e revogar dispositivos sem depender da futura central comercial.

## Etapa 2 — Segurança e administração local

- usuários administradores;
- funções e escopos;
- autenticação forte;
- comunicação criptografada;
- rotação e revogação de chaves;
- auditoria;
- isolamento entre organizações ou ambientes;
- proteção de segredos;
- política de conteúdo e payload;
- limites de requisição;
- backup de configuração.

Critério de conclusão: nenhuma operação administrativa sensível ocorre sem identidade, autorização e auditoria.

## Etapa 3 — Memoria Explorer e BDR Explorer integrados

### Memoria Explorer

- conceitos e relações;
- episódios e padrões;
- trajetórias de recuperação;
- candidatos selecionados e rejeitados;
- origem e confiança;
- camadas e abstrações;
- memórias utilizadas em cada resposta.

### BDR Explorer

- registros e endereços resolutivos;
- estatísticas físicas;
- capacidades públicas;
- telemetria de persistência quando existir contrato público;
- integridade, checkpoint e recuperação por contrato;
- operação inicialmente read-only.

Regra: o Explorer nunca analisa diretamente WAL, snapshots ou internals para inventar telemetria ausente.

## Etapa 3A — Portabilidade da memória pessoal

Objetivo: garantir que a Memoria.ia pertença ao cliente e sobreviva à troca de provedor.

- identidade pessoal independente do servidor;
- memória pessoal separada do vínculo comercial;
- exportação e importação versionadas;
- backup criptografado controlado pelo cliente;
- proveniência entre memória pessoal, conteúdo do provedor e dados operacionais;
- revogação do vínculo sem apagar a memória;
- funcionamento local sem provedor;
- consentimento antes de sincronizar com novo provedor;
- testes automáticos de migração e restauração.

Critério de conclusão: trocar o `ProviderBinding` sem alterar a `PersonalIdentity` ou perder a `PersonalMemory`.

Referência: [ADR-004 — Portabilidade da memória pessoal](architecture/ADR-004-PERSONAL-MEMORY-PORTABILITY.md).

## Etapa 4 — Sincronização seletiva

Escopos previstos:

- `local`: nunca sai do dispositivo;
- `personal`: dispositivos do mesmo proprietário;
- `family`;
- `team`;
- `organization`;
- `ma2a`;
- `public`.

Funcionalidades:

- sincronização incremental;
- conflitos e proveniência;
- autorização por escopo;
- criptografia;
- funcionamento offline;
- retomada após desconexão;
- backup e restauração;
- retenção configurável.

Critério de conclusão: o servidor sincroniza somente dados explicitamente autorizados e o dispositivo continua operando sem conexão.

## Etapa 5 — Observabilidade e atualização

- dispositivos online/offline;
- versões e compatibilidade;
- uso de CPU, GPU, NPU, RAM e armazenamento;
- latência;
- acertos e falhas de memória;
- tokens evitados;
- crescimento do BDR;
- alertas;
- atualização assinada;
- implantação gradual;
- retorno seguro à versão anterior.

## Etapa 6 — Resolutive Routing

- resolução local prioritária;
- descoberta de memória autorizada;
- seleção de nó por capacidade;
- carga, latência e distância;
- privacidade;
- custo;
- reputação;
- modelo local disponível;
- fallback controlado;
- integração futura com MA2A.

O roteamento deve consumir contratos do `resolutive-routing`, sem colocar sua lógica dentro da shell.

## Etapa 6A — Orquestração híbrida de modelos

Objetivo: permitir ao provedor combinar recursos locais e APIs externas.

- inventário de CPU, GPU, NPU e RAM;
- catálogo de modelos locais;
- runtime de LLM no servidor;
- adaptadores OpenAI, Gemini e outros;
- contrato comum de inferência;
- políticas local estrito, local preferencial, qualidade e custo;
- seleção contextual via `resolutive-routing`;
- consentimento e classificação de privacidade;
- fallback controlado;
- limites por cliente, oferta e licença;
- métricas de destino, latência, custo e carga;
- chaves externas protegidas no servidor;
- contexto mínimo preparado pela Memoria.ia.

Critério de conclusão: a mesma solicitação pode ser encaminhada com segurança ao dispositivo, ao servidor local ou a uma API autorizada, e a decisão fica observável e reproduzível.

Referência: [ADR-005 — Execução híbrida de modelos](architecture/ADR-005-HYBRID-MODEL-ROUTING.md).

## Etapa 7 — Fronteira de licenciamento

O servidor recebe uma licença, mas não a emite.

Preparação interna:

- interface `LicenseProvider`;
- estado da licença;
- `server_id` e `organization_id`;
- plano;
- validade;
- funcionalidades liberadas;
- limites de dispositivos e administradores;
- período de tolerância offline;
- aviso de renovação;
- bloqueio gradual e seguro;
- cache de certificado assinado;
- nenhuma regra de pagamento dentro do servidor.

Critério de conclusão: um provedor externo de licença pode ser conectado sem alterar os módulos de domínio.

## Etapa 8 — Central administrativa futura

Será desenvolvida em outro sistema e, quando oportuno, outro repositório.

Responsabilidades:

- cadastro de provedores;
- organizações;
- instalações de Memoria.ia Server;
- planos;
- emissão e renovação de certificados;
- suspensão e revogação;
- pagamentos e faturamento;
- suporte;
- limites contratados;
- métricas comerciais;
- royalties;
- contratos Enterprise.

Não pertencem ao Memoria.ia Server:

- venda de planos;
- cobrança;
- emissão da licença comercial principal;
- cadastro global de clientes;
- alteração dos próprios limites;
- administração comercial de outros provedores.

## Etapa 9 — Escala e alta disponibilidade

- múltiplos servidores do mesmo provedor;
- filiais e regiões;
- replicação;
- failover;
- balanceamento;
- políticas hierárquicas;
- observabilidade consolidada;
- recuperação de desastre;
- clusters;
- integração MA2A.

## Etapa 10 — Economia de recursos da rede

Fase posterior à identidade, medição, privacidade e roteamento:

- medição de recursos consumidos;
- capacidade ociosa;
- créditos de processamento;
- devolução de capacidade;
- regras de reputação;
- auditoria;
- isolamento de tarefas;
- política comercial externa.

Esta etapa não deve ser implementada antes de existirem segurança, medição verificável e contratos comerciais.

## Etapa 1A — Oferta da OFF.IA pelo provedor

Objetivo: permitir que o provedor entregue a OFF.IA como serviço aos seus clientes.

- cadastro interno de clientes;
- convites de ativação;
- QR Code, link ou código curto;
- descoberta segura do servidor;
- identidade visual e suporte do provedor;
- associação cliente–dispositivo–servidor;
- ofertas internas criadas pelo provedor;
- permissões derivadas do plano interno do cliente;
- desvinculação e revogação;
- preparação para troca segura de provedor;
- funcionamento local após a ativação.

Critério de conclusão: um cliente baixa a OFF.IA, informa os dados recebidos do provedor e conclui a vinculação sem precisar acessar a futura Central de Licenciamento.

Referência: [OFF.IA como serviço do provedor](OFFIA-PROVIDER-ONBOARDING.md).
