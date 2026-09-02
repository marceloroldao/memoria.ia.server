# Instalação inicial — v0.1.0-alpha.3

Esta versão instala o Memoria.ia Server em Linux usando Docker Compose.

## Componentes

- Memoria.ia v1.0.0rc2 com runtime nativo;
- Resolutive DB v1.1.0;
- BDR Explorer em modo demonstrativo e read-only;
- Server Shell com painel unificado;
- volume persistente para os dados da Memoria.ia;
- health checks e reinício automático.

## Requisitos sugeridos

- Linux x86_64, preferencialmente Ubuntu Server ou Debian;
- Docker Engine 24 ou superior;
- Docker Compose v2;
- 4 GB de RAM para a compilação inicial;
- 10 GB livres;
- acesso à Internet durante a construção das imagens.

GPU não é obrigatória nesta versão.

## Instalação

Baixe ou clone o repositório privado e entre no diretório:

```bash
git clone https://github.com/marceloroldao/memoria.ia.server.git
cd memoria.ia.server
bash scripts/install.sh
```

O script:

1. verifica Docker e Compose;
2. cria `.env` quando necessário;
3. gera uma chave administrativa aleatória;
4. constrói as imagens;
5. inicia os serviços;
6. preserva os dados no volume `memoria-data`.

Abra:

```text
http://IP_DO_SERVIDOR:8780
```

Antes de expor a instalação publicamente, use um proxy reverso com HTTPS e restrinja a porta 8780 conforme sua rede.

## Login administrativo

A atualização gera credenciais no arquivo local `.env`. Para consultá-las no próprio servidor:

```bash
grep '^MEMORIA_SERVER_ADMIN_USER=' .env
grep '^MEMORIA_SERVER_ADMIN_PASSWORD=' .env
```

Não envie essa senha em mensagens nem a inclua em capturas de tela.

A sessão dura oito horas por padrão. Quando HTTPS estiver configurado, altere:

```dotenv
MEMORIA_SERVER_COOKIE_SECURE=true
```

## Estado

```bash
bash scripts/status.sh
```

## Atualização

```bash
git pull
bash scripts/update.sh
```

## Parar sem apagar dados

```bash
bash scripts/uninstall.sh
```

O comando preserva o volume da Memoria.ia. A remoção de volumes deve ser uma decisão explícita.

## Configuração da organização

Edite `.env` antes ou depois da primeira inicialização:

```dotenv
MEMORIA_ORGANIZATION_ID=vuppi
MEMORIA_ORGANIZATION_NAME=VUPPI INTERNET
MEMORIA_NODE_ID=memoria:vuppi:primary
```

Se alterar a organização depois de já existirem dados, a Memoria.ia pode recusar a inicialização para evitar misturar identidades. Faça essa configuração antes de uso real.

## Catálogo de modelos

Abra `/admin/memoria`, entre em **Configurações** e cadastre quantos perfis precisar:

- provedor;
- identificador do modelo;
- credencial do provedor.

A credencial fica no volume persistente, em arquivo local com permissão restrita, e não é devolvida pela API.

Ative o perfil desejado. Apenas na primeira migração para o gateway reinicie a Memoria.ia:

```bash
docker compose restart memoria
```

Depois disso, OpenAI, Gemini e Llama local podem ser alternados sem apagar configurações e sem novos reinícios.

### Llama local

Coloque um arquivo GGUF no diretório `./models`, ajuste `MEMORIA_LLAMA_MODEL_FILE` no `.env` e execute:

```bash
docker compose --profile local-llm up -d llama
```

Na interface, cadastre o provedor **Llama local**, modelo `local-llama` e deixe a URL vazia para usar `http://llama:8080/v1`.

## Dados persistentes

Memoria.ia e o catálogo gravam em volumes separados:

```text
memoria-ia-server_memoria-data
memoria-ia-server_model-gateway-data
```

BDR Explorer está em modo demonstrativo nesta primeira instalação. A conexão read-only com um BDR persistente será implementada por contrato público.

## Limitações desta alpha

Ainda não estão implementados:

- cadastro final de clientes e OFF.IAs;
- QR Code de ativação;
- portabilidade completa entre provedores;
- Central de Licenciamento;
- HTTPS automático;
- cluster e alta disponibilidade.

A alpha serve para instalar, validar o painel, testar Memoria.ia e preparar a evolução do servidor.
