# Memoria.ia Server v0.1.0-alpha.4

Correção da seleção de modelo configurada pelo painel.

- remove a prioridade indevida do antigo `mock` definido no Compose;
- usa provedor, modelo e credencial persistidos pelo Memoria Admin;
- mantém URLs base configuráveis para OpenAI, Gemini e endpoints compatíveis;
- exige reinício do serviço Memoria.ia após salvar a configuração.

Atualização:

```bash
cd ~/memoria.ia.server
git pull
docker compose up -d --force-recreate memoria server
```
