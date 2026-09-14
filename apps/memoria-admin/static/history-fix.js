// Resilience + cross-conversation semantic memory bridge for the Web admin chat.
(() => {
  const originalLoad = window.loadConversationHistory;
  if (typeof originalLoad === 'function') {
    window.loadConversationHistory = async function (...args) {
      const conversation = document.getElementById('conversation');
      const snapshot = conversation ? conversation.innerHTML : '';
      try {
        return await originalLoad.apply(this, args);
      } finally {
        const state = document.getElementById('chatPersistenceState');
        if (conversation && state && state.textContent.includes('histórico indisponível') && snapshot) {
          conversation.innerHTML = snapshot;
          conversation.scrollTop = conversation.scrollHeight;
        }
      }
    };
  }

  const send = document.getElementById('sendMemoria');
  const message = document.getElementById('message');
  const answerMode = document.getElementById('chatAnswerMode');
  if (!send || !message) return;

  const originalSend = send.onclick;
  const profileSession = 'profile:web';
  let lastPromotion = '';

  function normalized(text) {
    return String(text || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toLowerCase();
  }

  function looksLikeQuestion(text) {
    const value = normalized(text);
    if (!value) return false;
    if (value.endsWith('?')) return true;
    return /^(qual|quais|quem|onde|quando|como|porque|por que|o que|que |quanto|quantos|quantas|me diga|lembra|lembre)/.test(value);
  }

  function asksLearnedSummary(text) {
    const value = normalized(text);
    return (value.includes('aprendeu') || value.includes('aprendendo') || value.includes('descobriu') || value.includes('descobertas'))
      && (value.includes('hoje') || value.includes('ultim') || value.includes('recent'));
  }

  async function persistEpisodeOnly(role, text) {
    const order = nextChatOrder();
    const timestamp = new Date().toISOString();
    const episodeId = `${chatSessionId}:${order}`;
    return api('/api/v1/episodes', {
      method: 'POST',
      body: JSON.stringify({
        episode_id: episodeId,
        role,
        text,
        session_id: chatSessionId,
        order,
        timestamp,
        event_type: 'chat_turn',
        topics: ['chat', 'web', 'direct-memory']
      })
    });
  }

  function formatKnowledgeHit(hit) {
    const src = Array.isArray(hit.sources) && hit.sources.length ? hit.sources[0] : null;
    const provider = src?.provider || Object.keys(hit.providers || {})[0] || 'server';
    const sourceLine = src?.title ? `\nFonte: ${provider} · ${src.title}` : `\nFonte: ${provider}`;
    const confidence = typeof hit.confidence === 'number' ? `${Math.round(hit.confidence * 100)}%` : 'n/d';
    const related = Array.isArray(hit.related) && hit.related.length
      ? `\nRelacionado: ${hit.related.slice(0, 5).map(x => x[0]).join(', ')}`
      : '';
    return `${hit.excerpt || hit.label}\n\nConhecimento adquirido pelo servidor\nConfiança: ${confidence}\nObservações: ${hit.observations}${sourceLine}${related}`;
  }

  async function resolveServerKnowledge(text) {
    if (asksLearnedSummary(text)) {
      const recent = await api('/api/server/v1/knowledge/recent');
      const items = Array.isArray(recent.items) ? recent.items.slice(0, 8) : [];
      if (!items.length) return null;
      const lines = items.map(item => `• ${item.label} — ${Math.round((item.confidence || 0) * 100)}% · ${item.observations} observação(ões)`);
      return {
        reply: `O servidor já consolidou ${recent.concepts || items.length} conceito(s) a partir de ${recent.observations || 0} observação(ões).\n\nMais recentes:\n${lines.join('\n')}`,
        hit: items[0]
      };
    }
    const result = await api(`/api/server/v1/knowledge/query?q=${encodeURIComponent(text)}`);
    const hit = Array.isArray(result.hits) && result.hits.length ? result.hits[0] : null;
    return hit ? {reply: formatKnowledgeHit(hit), hit} : null;
  }

  async function directMemorySend() {
    const text = message.value.trim();
    if (!text) return;

    bubble(text, 'user');
    message.value = '';
    const question = looksLikeQuestion(text) || asksLearnedSummary(text);

    try {
      await persistEpisodeOnly('user', text);
    } catch (error) {
      log('direct_chat_episode_error', {role: 'user', error: error.message});
      bubble(`Aviso: não foi possível gravar esta mensagem no BDR: ${error.message}`, 'error', 'Persistência');
    }

    try {
      if (!question) {
        const ingested = await api('/api/v1/conversation/ingest', {
          method: 'POST',
          body: JSON.stringify({
            role: 'user',
            text,
            session_id: profileSession,
            timestamp: new Date().toISOString()
          })
        });
        const relations = Array.isArray(ingested.relations) ? ingested.relations : [];
        const reply = relations.length
          ? `Registrado sem LLM: ${relations.length} relação(ões) extraída(s).`
          : 'Registrado sem LLM. Nenhuma relação explícita foi extraída desta entrada.';
        bubble(reply, 'assistant', 'Memoria.ia · direta');
        await persistEpisodeOnly('assistant', reply).catch(() => {});
        showMetrics({mode:'direct-no-llm',operation:'ingest',relations:relations.length,input_tokens:0,output_tokens:0});
        log('direct_chat_ingest', {relations: relations.length, session_id: profileSession});
      } else {
        const resolved = await api('/api/v1/conversation/resolve', {
          method: 'POST',
          body: JSON.stringify({query: text, session_id: profileSession})
        });
        const personalHit = String(resolved.status || '').toUpperCase() === 'HIT' && resolved.selected_context;
        if (personalHit) {
          const reply = String(resolved.selected_context);
          bubble(reply, 'assistant', 'Memoria.ia · memória pessoal');
          await persistEpisodeOnly('assistant', reply).catch(() => {});
          showMetrics({mode:'direct-no-llm',operation:'resolve-personal',status:resolved.status,confidence:resolved.confidence ?? resolved.score ?? null,input_tokens:0,output_tokens:0});
          log('direct_chat_resolve', {status: resolved.status, space:'personal', session_id:profileSession});
        } else {
          const learned = await resolveServerKnowledge(text).catch(error => {
            log('server_knowledge_query_error', {error:error.message}); return null;
          });
          if (learned) {
            bubble(learned.reply, 'assistant', 'Memoria.ia · Server Knowledge');
            await persistEpisodeOnly('assistant', learned.reply).catch(() => {});
            showMetrics({mode:'direct-no-llm',operation:'resolve-server-knowledge',status:'HIT',confidence:learned.hit?.confidence ?? null,observations:learned.hit?.observations ?? null,input_tokens:0,output_tokens:0});
            log('direct_chat_resolve', {status:'HIT',space:'server-knowledge',key:learned.hit?.key || null});
          } else {
            const reply = 'Relação não encontrada nem na memória pessoal nem no conhecimento adquirido pelo servidor.';
            bubble(reply, 'system', 'Memoria.ia · sem HIT');
            await persistEpisodeOnly('assistant', reply).catch(() => {});
            showMetrics({mode:'direct-no-llm',operation:'resolve',status:'MISS',input_tokens:0,output_tokens:0});
          }
        }
      }
      await window.loadConversationHistory?.();
    } catch (error) {
      bubble(`Erro na resolução direta: ${error.message}`, 'error', 'Memoria.ia');
      log('direct_chat_error', {error: error.message, session_id: profileSession});
    }
  }

  send.onclick = async () => {
    if (answerMode?.value === 'direct') {
      await directMemorySend();
      return;
    }
    if (typeof originalSend === 'function') return originalSend.call(send);
  };

  send.addEventListener('click', () => {
    if (answerMode?.value === 'direct') return;
    const text = message.value.trim();
    if (!text) return;
    const signature = `${text}\u0000${Date.now() >> 10}`;
    if (signature === lastPromotion) return;
    lastPromotion = signature;
    fetch('/api/v1/conversation/ingest', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({role:'user',text,session_id:profileSession,timestamp:new Date().toISOString()})
    }).then(async response => {
      if (!response.ok) {
        const body=await response.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `${response.status} ${response.statusText}`);
      }
    }).catch(error => console.warn('[memoria] profile promotion failed:', error.message));
  }, true);
})();
