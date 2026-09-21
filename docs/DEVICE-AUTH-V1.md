# Device Authentication V1

Status: server-only security layer for registered devices.

This feature does not change Memoria.ia, semantic memory, BDR storage semantics, or MA2A routing. It authenticates devices against the Memoria.ia Server before they can use device-owned operational endpoints.

## Cryptography

- device identity key: Ed25519 public key registered in Device Registry;
- server authority key: Ed25519 key pair generated once and persisted under `server-data`;
- server private key file: `/data/device-authority.json` with mode 0600;
- server certificate signature: Ed25519 over canonical JSON;
- challenge nonce: 32 random bytes encoded as base64url;
- bearer token: random, short-lived, stored only in memory as SHA-256(token).

The server authority fails closed if its persisted key state is malformed or no longer matches `server_id`.

## Device certificate

When an active device has a valid Ed25519 key, approval issues a local certificate:

```text
schema
serial
server_id
device_id
public_key_fingerprint
permissions
issued_at
valid_until
signature
issuer_public_key
```

The certificate is valid for one year by default. Suspending the device marks the certificate suspended. Re-approval restores it when still valid. Revocation marks it revoked and all existing device tokens stop authorizing immediately.

Legacy registrations with non-Ed25519 keys remain administratively visible and may be active, but cannot perform device authentication.

## Challenge-response

Public device bootstrap routes:

```text
GET  /api/server/v1/device-auth/authority
POST /api/server/v1/device-auth/challenge
POST /api/server/v1/device-auth/verify
```

Authentication sequence:

```text
device -> challenge(device_id)
server -> challenge_id + nonce + server_id + certificate
device -> signs canonical challenge message with Ed25519 private key
device -> verify(device_id, challenge_id, signature)
server -> verifies registered public key + active certificate
server -> short-lived Device token
```

The signed message is exactly:

```text
memoria-server-device-auth/v1
<server_id>
<device_id>
<challenge_id>
<nonce>
```

Challenges are one-time, expire quickly, and are rate-limited per client/device tuple.

## Authenticated device routes

```text
GET  /api/server/v1/device/self
POST /api/server/v1/device/heartbeat
Authorization: Device <token>
```

The token is bound to exactly one `device_id`. Heartbeat cannot nominate another device.

## Fail-closed behavior

The server refuses to silently replace:

- corrupted `server-identity.json`;
- corrupted `devices.json`;
- corrupted/mismatched `device-authority.json`.

A torn audit line does not reset the audit sequence; the next valid sequence continues from the highest valid event already persisted.

## Remaining work

- server authority key rotation with overlap window;
- device public-key rotation protocol;
- scoped device permissions enforced per endpoint;
- mTLS or MA2A transport binding when the network layer is ready;
- optional persistent token/session revocation list if tokens need to survive process restarts;
- enrollment invitations/QR bootstrap for OFF.IA.
