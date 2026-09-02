# Memoria.ia Server v0.1.0-alpha.8

- corrige o cadastro do Llama local com URL vazia;
- usa automaticamente `http://llama:8080/v1`;
- oculta o campo de URL no perfil Llama padrão;
- aceita também `llama:8080/v1`, `padrão` ou `default` na API;
- mantém todos os recursos do catálogo de modelos da alpha.7.

```bash
cd ~/memoria.ia.server
git pull
docker compose build server model-gateway
docker compose up -d --force-recreate server model-gateway
```
