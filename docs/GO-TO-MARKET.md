# Estratégia de entrada no mercado

## Objetivo

Registrar a abordagem comercial para transformar as tecnologias resolutivas em uma cadeia de produtos progressiva, iniciando por uma solução demonstrável e evoluindo até uma rede cooperativa entre provedores.

Este documento é direcional. Limites, preços e promessas comerciais somente devem ser consolidados depois de medições e validações reais.

## Tese central

A estratégia não deve apresentar todas as tecnologias ao mercado simultaneamente. Cada camada deve resolver um problema compreensível e preparar a camada seguinte:

**OFF.IA → Memoria.ia → Memoria.ia Server → provedores → M2A2/MA2A**

- **OFF.IA** torna a tecnologia visível ao usuário.
- **Memoria.ia** oferece memória, contexto e continuidade independentes do modelo.
- **Memoria.ia Server** permite ao provedor operar, licenciar e administrar o serviço.
- **Provedores** formam o canal de distribuição e disponibilizam infraestrutura.
- **M2A2/MA2A** conecta instalações maduras em uma rede cooperativa.

A rede global não é requisito para o primeiro produto comercial.

## Proposta de valor

Proposta inicial recomendada:

> Ofereça IA privada aos seus clientes, com memória pessoal portátil e liberdade para usar modelos locais ou APIs.

O produto não deve ser apresentado apenas como “mais uma IA”. Seu diferencial é permitir que memória, modelo, processamento, dispositivo e provedor evoluam ou sejam substituídos separadamente.

## Separação de propriedade e responsabilidades

### Cliente final

- É proprietário de sua memória pessoal.
- Pode exportá-la e migrá-la para outro provedor compatível.
- Não deve ficar preso a uma VPS, API, modelo, fabricante ou aplicação específica.

### Provedor

- Instala e licencia seu próprio Memoria.ia Server.
- Registra e administra seus dispositivos internos.
- Pode oferecer instâncias de OFF.IA e outros serviços resolutivos.
- Não se torna proprietário da memória pessoal do cliente.

### Central comercial

- Administra identidades, certificados, licenças, planos e direitos de uso.
- Não armazena a memória pessoal dos clientes.
- Não deve ser uma dependência contínua para o funcionamento local.
- Deve permitir um período seguro de tolerância quando estiver temporariamente indisponível.

### Rede M2A2/MA2A

- Coordena cooperação entre instalações autorizadas.
- Não deve confundir conhecimento compartilhável com memória pessoal.
- Somente recebe recursos e informações explicitamente permitidos pelos contratos de privacidade e escopo.

## Etapas comerciais

### 1. OFF.IA: produto demonstrável

Entregar uma experiência simples que demonstre:

- funcionamento offline;
- privacidade;
- memória persistente;
- continuidade entre sessões;
- aprendizado controlado;
- liberdade para trocar o modelo utilizado.

O objetivo desta etapa é tornar os benefícios observáveis sem exigir que o usuário compreenda toda a arquitetura resolutiva.

### 2. Memoria.ia: camada integrável

Oferecer a Memoria.ia entre aplicações e modelos de IA, inicialmente para software houses, SaaS e organizações que já utilizam APIs ou modelos locais.

O valor deve ser medido por:

- recuperação correta de informações;
- continuidade entre sessões;
- redução do contexto reenviado;
- redução de tokens e custo;
- latência;
- portabilidade e controle da memória.

### 3. Memoria.ia Server: produto para provedores

Permitir que provedores baixem, instalem e licenciem o servidor.

Cada instalação poderá:

- registrar dispositivos internos;
- administrar clientes e instâncias;
- executar modelos locais;
- consumir APIs externas;
- combinar recursos locais e remotos;
- aplicar políticas de privacidade, custo e capacidade.

### 4. Planos

Direção inicial:

- Free;
- Developer;
- Pequeno;
- Médio;
- Grande;
- Enterprise.

A diferenciação poderá considerar:

- instalações licenciadas;
- chaves de aplicação;
- usuários e dispositivos;
- capacidade e simultaneidade;
- alta disponibilidade;
- suporte e SLA;
- recursos de federação e rede.

Preços e limites devem ser definidos somente após telemetria operacional e estimativas reais de suporte, infraestrutura e risco.

### 5. Rede progressiva

A evolução recomendada é:

1. operação local;
2. rede privada entre nós autorizados;
3. federação entre provedores;
4. rede M2A2/MA2A ampliada.

Servidores com recursos ociosos poderão futuramente oferecer processamento. Compensação por tokens, créditos, reputação e liquidação devem existir como protocolos independentes, auditáveis e testados antes do uso comercial.

## Execução híbrida

O servidor poderá utilizar:

- LLM local em CPU, GPU ou NPU;
- APIs como GPT, Gemini e outras;
- combinação de modelos locais e APIs;
- seleção contextual por meio do Resolutive Routing.

Critérios de seleção:

- privacidade;
- custo;
- latência;
- carga do nó;
- capacidade disponível;
- qualidade necessária;
- disponibilidade;
- distância de rede.

A Memoria.ia preserva a continuidade. O modelo executa interpretação ou geração e deve permanecer substituível.

## Riscos principais

1. **Escopo excessivo**  
   Tentar lançar aplicação, servidor, licenciamento e rede global ao mesmo tempo.

2. **Comunicação complexa**  
   Explicar todos os componentes antes de apresentar um benefício direto ao cliente.

3. **Dependência da central**  
   Interromper o serviço local por uma falha temporária no licenciamento.

4. **Mistura de domínios**  
   Confundir memória pessoal, conhecimento do provedor e conteúdo compartilhado na rede.

5. **Preços prematuros**  
   Definir planos sem medir consumo, armazenamento, processamento e suporte.

6. **Promessas sem evidência**  
   Declarar economia, desempenho ou inteligência sem benchmarks reproduzíveis.

7. **Bloqueio de fornecedor**  
   Criar um formato de memória fechado ou difícil de exportar.

8. **Computação de terceiros sem proteção**  
   Compartilhar processamento antes de existirem isolamento, auditoria, reputação, segurança e regras de responsabilidade.

9. **Pesquisa misturada ao produto**  
   Alterar contratos comerciais estáveis com experimentos ainda não validados.

## Critérios para a primeira versão comercial

Antes da primeira oferta paga, validar:

- instalação e atualização reproduzíveis;
- isolamento entre clientes;
- exportação e importação da memória pessoal;
- formato de memória versionado;
- licença identificável por instalação;
- tolerância offline da licença;
- logs e métricas sem exposição de conteúdo privado;
- integração com pelo menos um modelo local e uma API externa;
- backup, restauração e recuperação após falhas;
- métricas de latência, memória, tokens e custo;
- documentação das responsabilidades de cada componente;
- caminho de migração entre planos e provedores.

## Decisão estratégica consolidada

A entrada no mercado deve ocorrer pelo benefício mais fácil de demonstrar: IA privada com memória persistente e portátil.

A arquitetura completa será revelada progressivamente:

- primeiro como experiência;
- depois como tecnologia integrável;
- em seguida como infraestrutura licenciável;
- finalmente como rede cooperativa.

Essa ordem reduz risco, permite receita antes da rede global e cria provedores reais que futuramente poderão formar a M2A2/MA2A.
