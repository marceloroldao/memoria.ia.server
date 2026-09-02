# Catálogo e gateway de modelos

## Decisão

O Memoria.ia Server separa **modelo cadastrado** de **modelo ativo**. Trocar o ativo não remove configuração ou credencial dos demais perfis.

O `model-gateway` é um módulo independente entre a Memoria.ia e os provedores. A Memoria.ia continua responsável por selecionar contexto e memória; o gateway cuida apenas da chamada ao modelo escolhido.

## Provedores iniciais

- OpenAI Responses API;
- Gemini `generateContent`;
- Llama local por endpoint OpenAI-compatible do `llama.cpp`.

Os perfis públicos contêm nome, provedor, modelo e URL. As chaves ficam em arquivo separado com modo `0600` e nunca são retornadas pela API ou pela interface.

## Compatibilidade na atualização

Enquanto nenhum perfil estiver ativo, o gateway repassa a configuração OpenAI anterior. Isso evita interromper o chat logo após atualizar o servidor.

Na primeira ativação, a configuração persistida da Memoria.ia é migrada para `gateway-active`. Execute uma vez:

```bash
docker compose restart memoria
```

Depois dessa migração, a troca entre perfis é imediata e não exige reiniciar a Memoria.ia.

## Llama local

1. Crie o diretório configurado em `MEMORIA_LLAMA_MODELS_DIR`.
2. Coloque nele um modelo `.gguf` compatível com `llama.cpp`.
3. Informe o nome do arquivo em `MEMORIA_LLAMA_MODEL_FILE`.
4. Inicie o perfil local:

```bash
docker compose --profile local-llm up -d llama
```

5. Na interface, cadastre um perfil `Llama local`, use o modelo `local-llama` (ou o valor de `MEMORIA_LLAMA_MODEL_ALIAS`). A URL padrão é `http://llama:8080/v1`.
6. Ative o perfil.

O Llama é opcional. OpenAI e Gemini continuam funcionando quando o contêiner local não estiver iniciado.

## Fronteiras

- o gateway não acessa o BDR nem a memória pessoal;
- o navegador acessa o catálogo somente pela sessão autenticada do shell;
- o serviço Llama não publica porta no host;
- os modelos GGUF são montados como somente leitura;
- o catálogo tem volume próprio e poderá ser separado em outro serviço futuramente.
