# OFF.IA como serviço do provedor

Status: visão de produto aceita

## Modelo

A OFF.IA será uma oferta de serviço de IA disponibilizada pelos provedores aos seus próprios clientes.

O provedor:

1. instala o Memoria.ia Server;
2. licencia seu servidor na futura Central de Licenciamento;
3. configura sua marca, endereço e políticas;
4. cria planos ou permissões internas para seus clientes;
5. fornece ao cliente as informações necessárias para vincular a OFF.IA.

O cliente:

1. baixa a OFF.IA por um canal oficial;
2. recebe do provedor um código, QR Code ou link de configuração;
3. informa esses dados no aplicativo;
4. autoriza o vínculo;
5. passa a usar a OFF.IA associada ao servidor de seu provedor.

## Fluxo de vinculação

```text
Cliente baixa OFF.IA
        |
        v
Informa código, link ou QR Code do provedor
        |
        v
OFF.IA descobre o Memoria.ia Server correto
        |
        v
Servidor valida convite e vínculo do cliente
        |
        v
OFF.IA cria sua chave local
        |
        v
Servidor registra o dispositivo e emite certificado interno
        |
        v
Aplicativo recebe configuração, permissões e serviços liberados
```

## Informações fornecidas pelo provedor

A experiência pode usar um único pacote de ativação contendo:

- endereço seguro do servidor;
- identidade do provedor;
- código de ativação de uso único;
- assinatura do pacote;
- validade;
- identificador do plano interno;
- marca e informações de suporte.

A configuração manual de URL deve existir apenas para ambientes técnicos. Para clientes comuns, o caminho preferencial será QR Code, link de ativação ou código curto.

## Identidades e relações

- a Central de Licenciamento conhece o provedor e o servidor licenciado;
- o Memoria.ia Server conhece os clientes e dispositivos daquele provedor;
- a OFF.IA conhece o servidor ao qual foi vinculada;
- a OFF.IA não precisa conhecer a Central de Licenciamento para uso normal;
- um provedor não enxerga clientes ou dispositivos de outro provedor.

## Propriedade e autonomia da memória

A Memoria.ia pessoal pertence ao cliente final e é independente do provedor. O vínculo com um servidor concede serviços, mas não transfere propriedade sobre identidade, episódios, relações, preferências ou histórico pessoal.

Depois da ativação, a OFF.IA deve continuar oferecendo suas funções locais quando estiver offline.

A conexão com o provedor acrescenta:

- sincronização autorizada;
- backup opcional;
- serviços e conhecimentos do provedor;
- atualizações;
- suporte;
- roteamento para recursos autorizados;
- comunicação com outros dispositivos do cliente.

O servidor amplia a OFF.IA, mas não deve inutilizar suas funções locais durante uma interrupção comum de Internet.

## Troca de provedor

A arquitetura deve prever, futuramente:

- desvinculação explícita;
- revogação do certificado anterior;
- exportação completa e versionada da memória pessoal;
- preservação da identidade e de toda a Memoria.ia pessoal;
- novo vínculo mediante autorização;
- regras claras para dados fornecidos pelo provedor.

A troca substitui somente o vínculo com o provedor. Ela não recria nem apaga a identidade ou a memória pessoal. Nenhum provedor deve conseguir assumir silenciosamente uma OFF.IA já vinculada.

## Segurança mínima

- HTTPS obrigatório fora do ambiente local;
- convite de uso único e com validade curta;
- chave privada criada e mantida no dispositivo;
- certificado interno revogável;
- confirmação visível da identidade do provedor;
- proteção contra troca silenciosa de servidor;
- nenhuma senha do provedor embutida no aplicativo;
- auditoria de ativação, revogação e troca de vínculo.
