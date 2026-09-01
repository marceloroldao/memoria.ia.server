# ADR-002 — Fronteira entre licenciamento e registro interno

Status: aceito

## Decisão

Cada provedor baixa e instala seu próprio Memoria.ia Server. A instalação precisa ser licenciada por uma futura Central de Licenciamento.

O Memoria.ia Server registra seus dispositivos internos, mas não emite sua própria licença comercial e não cadastra globalmente clientes de outros provedores.

## Fluxo

1. O provedor instala o Memoria.ia Server.
2. O servidor gera sua identidade e solicitação de ativação.
3. A Central de Licenciamento valida o provedor e emite um certificado.
4. O certificado define plano, validade, limites e funcionalidades.
5. O servidor aplica esses direitos localmente.
6. OFF.IAs e dispositivos são registrados internamente no servidor.
7. Dispositivos internos confiam no servidor ao qual pertencem.
8. O servidor responde perante a Central de Licenciamento.

## Identidades distintas

### Licença do servidor

- emitida externamente;
- identifica provedor, organização e instalação;
- define plano e limites;
- possui validade e assinatura;
- pode ser renovada, suspensa ou revogada.

### Certificado do dispositivo

- emitido ou aprovado internamente;
- vinculado ao `server_id`;
- identifica um nó local;
- define permissões internas;
- pode ser suspenso ou revogado pelo próprio servidor.

## Regra de dependência

Os dispositivos não devem consultar a central comercial para operações normais. A indisponibilidade temporária da central não pode derrubar imediatamente a operação local.

A política exata de tolerância offline será definida na etapa de licenciamento, com certificado assinado e período de graça explícito.
