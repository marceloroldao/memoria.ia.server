# ADR-004 — Memória pessoal pertence ao cliente

Status: aceito

## Decisão

A Memoria.ia utilizada pela OFF.IA é pessoal e pertence ao cliente final.

O provedor oferece conectividade, serviços, processamento, sincronização autorizada, suporte e integração com seu Memoria.ia Server. Esse vínculo não transfere ao provedor a propriedade da memória pessoal.

O cliente pode trocar de provedor sem perder sua Memoria.ia, identidade pessoal, relações, episódios, preferências ou histórico local.

## Separação obrigatória de dados

### Memória pessoal portátil

- criada pelo cliente ou pela sua OFF.IA;
- armazenada prioritariamente sob controle do cliente;
- protegida por chaves do cliente;
- exportável e restaurável;
- preservada ao trocar de provedor;
- não pode ser apagada apenas porque o contrato com o provedor terminou.

### Dados fornecidos pelo provedor

- catálogo, suporte e informações operacionais;
- configurações da oferta;
- conteúdos licenciados pelo provedor;
- credenciais e permissões de acesso;
- dados sujeitos às regras contratuais do serviço.

Esses dados devem possuir proveniência e escopo próprios. O encerramento do serviço pode retirar o acesso ao conteúdo do provedor, mas não pode remover a memória pessoal do cliente.

### Dados operacionais do servidor

- registros técnicos;
- auditoria;
- estado da assinatura interna;
- telemetria;
- certificados e vínculos;
- limites e segurança.

Esses dados pertencem ao domínio operacional do provedor e não devem ser confundidos com a memória pessoal.

## Identidade independente do provedor

A identidade pessoal da OFF.IA não deve ser derivada do `server_id` do provedor.

O vínculo deve ser modelado separadamente:

```text
PersonalIdentity
    |
    +-- PersonalMemory
    |
    +-- ProviderBinding atual
            |
            +-- provider_id
            +-- server_id
            +-- certificado do vínculo
            +-- serviços autorizados
```

Trocar de provedor substitui o `ProviderBinding`; não recria a `PersonalIdentity` nem a `PersonalMemory`.

## Fluxo de troca de provedor

1. O cliente solicita ou autoriza a desvinculação.
2. A OFF.IA preserva integralmente a memória pessoal local.
3. O certificado do vínculo anterior é revogado.
4. Credenciais e conteúdos exclusivos do provedor anterior são separados.
5. O cliente recebe dados de ativação do novo provedor.
6. Um novo vínculo é criado.
7. A memória pessoal continua disponível.
8. Somente memórias explicitamente autorizadas são sincronizadas com o novo servidor.

## Requisitos técnicos

- formato de exportação versionado;
- backup criptografado sob controle do cliente;
- importação e restauração;
- identificação de proveniência;
- separação por escopos;
- chaves pessoais independentes do provedor;
- revogação apenas do vínculo;
- teste automático de portabilidade;
- modo local sem provedor;
- consentimento explícito antes de sincronizar dados pessoais com um novo provedor.

## Proibição arquitetural

O Memoria.ia Server não pode:

- tornar-se dono da memória pessoal;
- usar o fim da assinatura para apagar a memória local;
- impedir exportação da memória pessoal;
- vincular permanentemente a identidade do cliente ao provedor;
- misturar dados pessoais e conteúdo do provedor sem proveniência;
- transferir memória a outro provedor sem autorização.
