# Planos comerciais — rascunho

Status: proposta para validação técnica e comercial

Os planos licenciam uma instalação ou conjunto contratado de Memoria.ia Server. OFF.IAs e dispositivos internos utilizam a capacidade autorizada ao servidor e não compram a licença principal diretamente.

## Linha proposta

A lista inicial continha dois níveis chamados “Médio”. Para preservar sete faixas sem ambiguidade, o segundo foi provisoriamente denominado **Profissional**. O nome ainda pode ser alterado.

| Plano | Uso previsto | Limite inicial sugerido |
|---|---|---:|
| Free | avaliação e uso pessoal | 3 dispositivos |
| Developer | desenvolvimento e testes | 10 dispositivos |
| Pequeno | pequenos provedores e empresas | 50 dispositivos |
| Médio | operação regional | 250 dispositivos |
| Profissional | operação avançada | 1.000 dispositivos |
| Grande | grandes redes | 5.000 dispositivos |
| Enterprise | contrato personalizado | negociável |

Os limites são hipóteses, não compromissos comerciais. Devem ser confirmados por testes de carga, custos de suporte e estratégia de mercado.

## Capacidades por evolução

### Free

- uma instalação;
- registro básico;
- Memoria Admin;
- BDR Explorer básico;
- atualização manual;
- sem alta disponibilidade.

### Developer

- APIs de desenvolvimento;
- logs técnicos;
- ambientes e credenciais de teste;
- integração com OFF.IA;
- dados demonstrativos;
- restrição de produção conforme contrato futuro.

### Pequeno

- uso comercial;
- dispositivos e grupos;
- sincronização seletiva;
- backup;
- métricas básicas;
- usuários administrativos;
- atualizações estáveis.

### Médio

- mais dispositivos e administradores;
- políticas por grupos;
- métricas e alertas avançados;
- roteamento interno;
- auditoria com retenção ampliada.

### Profissional

- múltiplos servidores do mesmo provedor;
- filiais;
- replicação;
- alta disponibilidade;
- roteamento avançado;
- suporte prioritário.

### Grande

- clusters e milhares de dispositivos;
- servidores regionais;
- balanceamento;
- redundância;
- recuperação de desastre;
- observabilidade consolidada.

### Enterprise

- limites personalizados;
- múltiplas organizações;
- integração de identidade corporativa;
- implantação dedicada;
- módulos e contratos específicos;
- suporte e acordo de atendimento;
- possibilidade futura de OEM.

## Direitos da licença

O contrato técnico deve suportar:

- `server_id`;
- `organization_id`;
- `plan`;
- `max_devices`;
- `max_admin_users`;
- `features`;
- `issued_at`;
- `valid_until`;
- versão do schema;
- emissor;
- assinatura;
- período de tolerância offline.

Preços, cobrança, impostos e condições comerciais serão definidos na futura camada administrativa.
