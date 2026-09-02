# Memoria.ia Server v0.1.0-alpha.2

Atualização visual da primeira versão instalável.

## Alterado

- substitui a antiga interface Enterprise pela interface chat-first;
- interface em português;
- navegação entre Chat, Configurações e Diagnóstico;
- sessão administrativa preservada localmente no navegador;
- relatório TXT de diagnóstico sem inclusão intencional de chaves;
- rotas de ativos adaptadas para `/admin/memoria`;
- Core Memoria.ia v1.0.0rc2 e BDR v1.1.0 permanecem inalterados.

## Origem visual

`marceloroldao/memoria.ia`, branch `product/windows-native-alpha`, commit `2871dc4a90b9aaa393f1525245424e14e02aaca2`.

## Atualização de uma instalação existente

```bash
cd ~/memoria.ia.server
git pull
docker compose build server
docker compose up -d --force-recreate server
```

Depois, recarregue o navegador sem cache.
