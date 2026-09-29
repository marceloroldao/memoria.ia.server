# Ingestão tipada de episódios observados (Server v1)

Rota: `POST /api/server/v1/device/observations/npc-episodes`.
Autenticação: `Authorization: Device <token>` emitido por desafio Ed25519.
Exige dispositivo aprovado `type=server`, permissões `memory.sync` e `world.connect`,
e grupo administrativo `live-world:<world_id>`. O dispositivo não pode se atribuir
grupo, escopo, device_id, namespace ou hierarquia pela requisição.

O corpo é exatamente o envelope `live-infinita-npc-episode-observation/v1`
produzido pelo módulo `nov_episode_sync` da Live.infinita, preservando
`source_kind=need_outcome`, `plan_id`, `proposal_id`, revisão, tick, contexto,
resultado, `record_key` e `content_sha256`. O Server valida identidade e digest
antes de encaminhar ao contrato canônico de evidência
`POST /api/v1/external/episodes` da Memoria.ia V2.

O segredo administrativo `X-Memoria-Key` permanece exclusivamente no Server.
O cliente não usa `/api/v1/episodes`, porque esse contrato exige papel de
conversa (user/assistant) e alteraria a origem de uma experiência autônoma.

Uma confirmação válida do Product EvidenceCore precisa conter `ack=true`,
identidade, hash e namespace consistentes e recibo persistido
`{backend,state_id,sha256}`. O Server só então responde com
`memoria-server-npc-episode-receipt/v1`, status `stored` ou `duplicate`,
`record_key`, `content_sha256`, `world_id` codificado em `namespace`,
`server_id`, `device_id` e `evidence_id`. Conflitos imutáveis retornam HTTP 409.
Falta de permissão/certificado, erros de origem, rejeição ou indisponibilidade
da memória não produzem ACK. O Server não escreve World State nem concede
autoridade de seleção cognitiva.

Este contrato é receptor apenas. A Live.infinita só pode avançar seu cursor
de envio após conferir o recibo durável, incluindo identidade do servidor e
do dispositivo. O receptor central precisa ser implantado antes de habilitar
o cliente de envio. Um enrolamento administrativo explícito deve fixar o
grupo `live-world:nov-live-autonomous-001` para a VM de produção.
