# Memoria.ia Server v0.1.0-alpha.6

## Novo

- botão **Teste autônomo** na própria tela de chat;
- agente GPT gerando cenários relacionais pelo provedor já configurado;
- ingestão e resolução pelos contratos públicos da Memoria.ia;
- namespace isolado por execução (`autotest:<run_id>`);
- diálogo visível entre Agente GPT, Memoria.ia e Avaliador;
- controles para pausar, continuar e encerrar;
- relatório Markdown com conversa, gabarito, acertos, falhas, tokens e custo estimado;
- API administrativa autenticada para controlar as execuções.

## Segurança e limites

- nenhuma chave é enviada ao navegador ou incluída no relatório;
- máximo de 50 ciclos por execução;
- o executor é volátil nesta alpha: reiniciar o contêiner `server` encerra e remove as execuções em memória;
- pausar ou encerrar aguarda a requisição externa corrente terminar.

## Atualização

```bash
cd ~/memoria.ia.server
git pull
docker compose build server
docker compose up -d --force-recreate server
cat VERSION
```

O resultado esperado é `0.1.0-alpha.6`. Depois, atualize o navegador com `Ctrl + F5`.
