# Device Enrollment & Permissions V1

Status: server-only enrollment and authorization layer.

This layer belongs to Memoria.ia Server. It does not modify Memoria.ia, semantic memory, BDR storage semantics, or MA2A routing.

## Permission scopes

Known V1 scopes:

- `device.self.read`
- `device.heartbeat`
- `memory.sync`
- `model.local.use`
- `model.remote.use`
- `ma2a.connect`
- `telemetry.write`
- `world.connect`

New devices receive `device.self.read` and `device.heartbeat` when no explicit scope list is supplied.

The Server currently enforces:

- `GET /api/server/v1/device/self` -> `device.self.read`
- `POST /api/server/v1/device/heartbeat` -> `device.heartbeat`

The remaining scopes are reserved contracts for the matching future server modules. They are not treated as authorization until those endpoints exist.

Administrative scope changes use:

```text
POST /api/server/v1/devices/{device_id}/permissions
{"permissions":["device.self.read","device.heartbeat","memory.sync"]}
```

Changing permissions on an active Ed25519 device reissues its local certificate when the certificate payload no longer matches the registry state. Authorization reads current registry state, so removing a scope has immediate effect even for an already-issued short-lived device token.

## One-time enrollment

Administrative routes:

```text
GET  /api/server/v1/enrollments
POST /api/server/v1/enrollments
POST /api/server/v1/enrollments/{enrollment_id}/revoke
```

Public device claim route:

```text
POST /api/server/v1/device-enrollment/claim
```

Create example:

```json
{
  "label":"OFF.IA cliente 42",
  "type":"offia",
  "expires_minutes":60,
  "permissions":[
    "device.self.read",
    "device.heartbeat",
    "memory.sync"
  ],
  "groups":["cliente-42"]
}
```

The response contains `enrollment_code` exactly once. The server persists only SHA-256(code), never the plaintext invitation secret.

## Device-side claim

The device generates its Ed25519 key pair locally. Its private key never leaves the device.

Claim payload:

```json
{
  "enrollment_code":"enr1_...",
  "name":"OFF.IA do cliente",
  "public_key":"ed25519:<base64url raw public key>",
  "capabilities":{
    "cpu":"arm64",
    "models":["local-small"]
  },
  "versions":{
    "offia":"0.1"
  }
}
```

The invitation fixes device type, groups and permissions. The public claim cannot grant itself additional scopes.

A successful claim creates the device in `pending` state. The administrator still performs explicit approval. Approval issues the normal server-signed Ed25519 device certificate.

## Invitation lifecycle

```text
active -> claiming -> consumed
   |
   +-> revoked

active -> expired
```

`consumed` is one-time and cannot be replayed. A key already registered in the server cannot consume a new invitation.

The `claiming` state is persisted before device registration. This makes crash behavior fail-closed: a process failure cannot silently leave a secret invitation reusable for another device. Administrators can revoke a stuck invitation and create another.

## Security properties

- high-entropy invitation codes;
- plaintext invitation secret returned once;
- only digest persisted;
- one-time consumption;
- Ed25519 required on secure enrollment path;
- public endpoint rate-limited;
- invitation cannot override type/groups/scopes;
- corrupt enrollment state fails closed;
- scope removal is immediate;
- certificate is bound to current permission list.

## Next gates

- provider-friendly QR representation of the enrollment payload;
- signed discovery descriptor for server URL + authority fingerprint;
- device key rotation;
- authority key rotation with overlap;
- owner/customer binding above device identity;
- enforcement of `memory.sync`, `model.*`, `ma2a.connect`, `telemetry.write` and `world.connect` when those server endpoints are implemented.
