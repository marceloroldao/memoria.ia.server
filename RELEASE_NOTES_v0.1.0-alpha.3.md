# Memoria.ia Server v0.1.0-alpha.3

Atualização de segurança da versão instalável.

## Incluído

- tela inicial de login com usuário e senha;
- autenticação validada no servidor;
- cookie de sessão `HttpOnly` e `SameSite=Strict`;
- sessão com duração configurável;
- limite de tentativas de login;
- proteção do painel, Memoria Admin, BDR Explorer e APIs;
- botão de logout;
- geração de senha para instalações novas e existentes;
- testes do ciclo de autenticação.

## Atualização

```bash
cd ~/memoria.ia.server
git pull
bash scripts/update.sh
```

Consulte as credenciais somente no terminal do servidor:

```bash
grep '^MEMORIA_SERVER_ADMIN_USER=' .env
grep '^MEMORIA_SERVER_ADMIN_PASSWORD=' .env
```

A porta configurada anteriormente no `.env`, inclusive a porta 80, é preservada.

## Segurança

Em HTTP, mantenha `MEMORIA_SERVER_COOKIE_SECURE=false`. Depois de configurar HTTPS, altere para `true` e recrie o serviço.
