# Device Registry V1

Status: implementação inicial do Memoria.ia Server, sem alterações na Memoria.ia.

## Fronteira

O Device Registry é dado operacional do servidor. Ele persiste em `server-data` e não grava memória semântica, episódios, relações ou estado interno do BDR.

Arquivos persistidos:

- `/data/server-identity.json` — identidade estável da instalação;
- `/data/devices.json` — cadastro e estado dos dispositivos;
- `/data/audit.jsonl` — trilha append-only de operações administrativas.

## Identidade do servidor

Na primeira inicialização o Server cria um `server_id` aleatório com prefixo `srv-`. O arquivo é persistente, portanto reiniciar ou reconstruir o container não altera a identidade enquanto o volume `server-data` for preservado.

## Ciclo do dispositivo

Estados V1:

```text
pending -> active -> suspended -> active
    \         \          \
     +----------+-----------> revoked
```

`revoked` é terminal.

Tipos aceitos:

- `offia`;
- `phone`;
- `computer`;
- `server`;
- `robot`;
- `sensor`;
- `iot`.

O registro exige chave pública. O Server grava somente a chave pública e seu fingerprint SHA-256. Certificado interno assinado ainda **não** é emitido nesta versão; o campo `certificate_status=not_issued` torna essa ausência explícita.

## API administrativa

Todas as rotas abaixo estão atrás da sessão administrativa atual do Server:

```text
GET  /api/server/v1/server/identity
GET  /api/server/v1/devices
GET  /api/server/v1/devices/{device_id}
POST /api/server/v1/devices/register
POST /api/server/v1/devices/{device_id}/approve
POST /api/server/v1/devices/{device_id}/suspend
POST /api/server/v1/devices/{device_id}/revoke
POST /api/server/v1/devices/{device_id}/heartbeat
GET  /api/server/v1/audit?limit=100
GET  /api/server/v1/capabilities
```

O heartbeat V1 atualiza `last_seen`, capacidades e versões declaradas. Neste primeiro corte ele ainda é uma operação administrativa autenticada pela sessão do Server. Autenticação própria do dispositivo, challenge-response e certificado Ed25519 entram no próximo gate de segurança.

## Capacidades

O cadastro aceita, sem impor semântica à Memoria.ia:

- CPU, GPU, NPU;
- RAM e armazenamento;
- arquitetura e rede;
- modelos locais;
- versões OFF.IA, Memoria.ia, BDR, MA2A, firmware e sistema operacional;
- grupos e permissões locais.

## Auditoria

Registro, aprovação, heartbeat, suspensão, reativação e revogação produzem eventos em `audit.jsonl`.

Campos com nomes associados a senha, segredo, API key, private key, token ou credential são redigidos antes da persistência do evento.

## Próximo gate

1. challenge-response usando a chave pública cadastrada;
2. certificado interno Ed25519 assinado pelo Server;
3. token/certificado próprio para heartbeat, removendo dependência da sessão administrativa;
4. rotação e revogação de chaves;
5. escopos por dispositivo;
6. integração MA2A somente depois desses contratos estarem estáveis.
