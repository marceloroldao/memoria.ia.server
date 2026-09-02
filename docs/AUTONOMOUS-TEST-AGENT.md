# Agente de teste autônomo

O Memoria.ia Server inclui um executor de testes relacionais que usa o provedor LLM já configurado na Memoria.ia. A credencial do provedor nunca é enviada ao navegador nem copiada para o shell.

## Fluxo

1. O agente GPT gera uma afirmação, uma pergunta e um gabarito estruturado.
2. A afirmação é enviada ao contrato público `conversation/ingest`.
3. A pergunta é enviada ao contrato público `conversation/resolve`.
4. O avaliador normaliza acentos, caixa e pontuação e compara os termos esperados com a resposta estruturada.
5. Todos os turnos aparecem na janela de chat e compõem o relatório final.

## Isolamento

Cada execução recebe um `session_id` no formato `autotest:<run_id>`. Dessa forma, os cenários artificiais não são consultados pela conversa normal. Esta alpha não promove automaticamente nenhuma relação de teste para uma memória pessoal ou de produção.

## Limites da alpha

- 1 a 50 ciclos por execução;
- intervalo máximo de 10 segundos entre ciclos;
- uma execução continua no servidor enquanto a página estiver aberta ou for atualizada, mas o estado do executor é volátil e se perde quando o contêiner `server` reinicia;
- pausar ou encerrar aguarda a chamada externa corrente terminar;
- o relatório Markdown não contém chaves ou credenciais;
- o custo depende do modelo configurado; os tokens e o custo estimado, quando fornecido pelo adaptador, aparecem no relatório.

## API administrativa

Todas as rotas exigem a sessão autenticada do Memoria.ia Server:

- `POST /api/server/v1/autotests`
- `GET /api/server/v1/autotests/{run_id}?after={seq}`
- `POST /api/server/v1/autotests/{run_id}/pause`
- `POST /api/server/v1/autotests/{run_id}/resume`
- `POST /api/server/v1/autotests/{run_id}/stop`
- `GET /api/server/v1/autotests/{run_id}/report`

## Evolução planejada

- persistência de execuções e retomada após reinício;
- teto explícito de custo por execução;
- famílias de cenários selecionáveis;
- comparação entre versões da Memoria.ia e do BDR;
- avaliação semântica complementar, sempre preservando o gabarito objetivo;
- agendamento de testes fora do horário de pico.
