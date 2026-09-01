# ADR-005 — Execução híbrida e seleção contextual de modelos

Status: aceito

## Decisão

O Memoria.ia Server pode executar e orquestrar múltiplos provedores de inferência:

- LLM local no próprio servidor do provedor;
- LLM local no dispositivo do cliente;
- APIs externas, como OpenAI, Gemini e outras;
- combinações e fallbacks entre esses destinos.

A disponibilidade de GPU não é obrigatória. Quando o servidor possuir GPU, CPU ou outro acelerador adequado, o provedor pode disponibilizar modelos locais para atender suas OFF.IAs.

## Princípio

A Memoria.ia continua dona da memória, do estado e da preparação do contexto.

O modelo selecionado recebe apenas o contexto mínimo autorizado para a solicitação, produz a resposta e não se torna proprietário da memória.

```text
Solicitação da OFF.IA
        |
        v
Memoria.ia resolve memória e contexto autorizado
        |
        v
Resolutive Routing avalia a demanda
        |
        +--> modelo no dispositivo
        +--> modelo local no servidor do provedor
        +--> OpenAI
        +--> Gemini
        +--> outro adaptador
        |
        v
Resposta + métricas + atualização autorizada da memória
```

## Critérios de seleção

O roteador pode considerar:

- classificação da tarefa;
- privacidade e escopo dos dados;
- autorização do cliente;
- capacidade exigida;
- qualidade histórica do modelo para a tarefa;
- modelo e formato compatíveis;
- CPU, GPU, NPU, RAM e carga;
- tamanho do contexto;
- latência;
- custo;
- disponibilidade;
- distância de rede;
- limites do plano;
- preferência do provedor;
- preferência do cliente;
- saúde e reputação do destino;
- necessidade de funcionamento offline.

A ordem e os pesos pertencem ao contrato do `resolutive-routing`, não à interface administrativa.

## Modos de política

### Local estrito

Nenhum dado é enviado para API externa. A tarefa usa o dispositivo ou o servidor do provedor.

### Local preferencial

Tenta processamento local primeiro e usa API externa somente quando autorizado e necessário.

### Qualidade preferencial

Seleciona o modelo mais adequado disponível, respeitando privacidade e limites.

### Custo controlado

Prioriza memória, modelos locais e destinos de menor custo.

### Personalizado

Política definida pelo provedor e limitada pelo consentimento do cliente.

## Adaptadores

Cada destino deve implementar um contrato comum, por exemplo:

- identidade do provedor;
- modelos disponíveis;
- capacidades;
- formatos de entrada;
- limites de contexto;
- streaming;
- saúde;
- estimativa de custo;
- métricas;
- cancelamento;
- política de retenção;
- classificação de privacidade permitida.

Adaptadores previstos:

- `LocalDeviceAdapter`;
- `LocalServerAdapter`;
- `OpenAIAdapter`;
- `GeminiAdapter`;
- adaptadores adicionais sem alteração do Core.

## Segurança e privacidade

- chaves de APIs externas permanecem no servidor do provedor;
- OFF.IA não recebe as chaves principais do provedor;
- dado pessoal só sai do dispositivo conforme escopo e consentimento;
- políticas locais podem proibir provedores externos;
- o log não armazena prompts completos por padrão;
- segredos nunca aparecem em métricas ou auditoria;
- cada envio externo registra destino, política e categoria de dados;
- falha externa não pode corromper a memória pessoal;
- conteúdo enviado deve ser minimizado pela Memoria.ia.

## Fallback

Fallback não significa liberdade para ignorar privacidade.

Exemplo permitido:

1. modelo local do dispositivo;
2. modelo local do servidor;
3. API externa autorizada;
4. resposta degradada ou fila.

Se a política for local estrita, uma API externa nunca entra na sequência.

## Observabilidade

Registrar, sem expor conteúdo pessoal:

- destino escolhido;
- modelo;
- motivo de seleção;
- tempo de fila;
- latência de inferência;
- tokens ou unidades processadas;
- custo estimado;
- memória utilizada;
- fallback;
- erro;
- carga do servidor;
- qualidade ou resultado quando mensurável.

## Separação arquitetural

- Memoria.ia: memória, contexto e estado;
- Resolutive Routing: decisão de destino;
- Model Adapter: tradução do contrato para cada motor;
- Runtime local: execução de modelos do provedor;
- Server Shell: configuração e observabilidade;
- Central de Licenciamento futura: direitos e limites comerciais.

A shell não deve conter o algoritmo de seleção.
