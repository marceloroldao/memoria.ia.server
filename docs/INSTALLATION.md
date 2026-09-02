# Instalação inicial — v0.1.0-alpha.1

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

## Modos de modelo

### Memória/mock

Padrão seguro para a primeira instalação:

```dotenv
MEMORIA_LLM_PROVIDER=mock
```

### OpenAI

```dotenv
MEMORIA_LLM_PROVIDER=openai
MEMORIA_LLM_MODEL=MODELO_ESCOLHIDO
OPENAI_API_KEY=SUA_CHAVE
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Gemini

```dotenv
MEMORIA_LLM_PROVIDER=gemini
MEMORIA_LLM_MODEL=MODELO_ESCOLHIDO
GEMINI_API_KEY=SUA_CHAVE
```

### LLM local no servidor

Inicie separadamente um servidor de inferência compatível com a API OpenAI, como um runtime baseado em llama.cpp. Depois configure:

```dotenv
MEMORIA_LLM_PROVIDER=openai
MEMORIA_LLM_MODEL=NOME_DO_MODELO_LOCAL
OPENAI_API_KEY=local
OPENAI_BASE_URL=http://host.docker.internal:PORTA/v1
```

A versão alpha ativa um destino por configuração. A seleção simultânea e contextual entre vários modelos continuará na etapa do `resolutive-routing`.

Após alterar `.env`:

```bash
docker compose up -d --force-recreate
```

## Dados persistentes

Somente o serviço Memoria.ia grava no volume:

```text
memoria-ia-server_memoria-data
```

BDR Explorer está em modo demonstrativo nesta primeira instalação. A conexão read-only com um BDR persistente será implementada por contrato público.

## Limitações desta alpha

Ainda não estão implementados:

- cadastro final de clientes e OFF.IAs;
- QR Code de ativação;
- portabilidade completa entre provedores;
- Central de Licenciamento;
- seleção simultânea entre vários modelos;
- execução local gerenciada de GGUF;
- HTTPS automático;
- cluster e alta disponibilidade.

A alpha serve para instalar, validar o painel, testar Memoria.ia e preparar a evolução do servidor.
