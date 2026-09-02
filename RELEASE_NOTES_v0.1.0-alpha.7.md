# Memoria.ia Server v0.1.0-alpha.7

## Novo

- catálogo persistente com vários modelos;
- seleção de modelo ativo sem apagar os demais;
- credenciais separadas e write-only por perfil;
- gateway para OpenAI, Gemini e Llama local;
- `llama.cpp` opcional pelo perfil Compose `local-llm`;
- compatibilidade com a configuração OpenAI existente;
- troca imediata após a migração inicial ao gateway.

## Atualização

```bash
cd ~/memoria.ia.server
git pull
docker compose build server model-gateway
docker compose up -d --force-recreate
cat VERSION
```

O resultado esperado é `0.1.0-alpha.7`. Atualize o navegador com `Ctrl + F5`.

Ao ativar o primeiro perfil salvo, execute uma única vez:

```bash
docker compose restart memoria
```

As trocas seguintes não precisam de reinicialização.
