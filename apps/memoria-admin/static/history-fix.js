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

  async function directMemorySend() {
    const text = message.value.trim();
    if (!text) return;

    bubble(text, 'user');
    message.value = '';
    const question = looksLikeQuestion(text);

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
        showMetrics({
          mode: 'direct-no-llm',
          operation: 'ingest',
          relations: relations.length,
          input_tokens: 0,
          output_tokens: 0
        });
        log('direct_chat_ingest', {relations: relations.length, session_id: profileSession});
      } else {
        const resolved = await api('/api/v1/conversation/resolve', {
          method: 'POST',
          body: JSON.stringify({query: text, session_id: profileSession})
        });
        const hit = String(resolved.status || '').toUpperCase() === 'HIT';
        const selected = resolved.selected_context;
        const reply = hit && selected
          ? String(selected)
          : 'Relação não encontrada.';
        bubble(reply, hit ? 'assistant' : 'system', hit ? 'Memoria.ia · colapso' : 'Memoria.ia · sem HIT');
        await persistEpisodeOnly('assistant', reply).catch(() => {});
        showMetrics({
          mode: 'direct-no-llm',
          operation: 'resolve',
          status: resolved.status || 'MISS',
          confidence: resolved.confidence ?? resolved.score ?? null,
          input_tokens: 0,
          output_tokens: 0
        });
        log('direct_chat_resolve', {
          status: resolved.status,
          session_id: profileSession,
          selected_context: selected || null
        });
      }
      await window.loadConversationHistory?.();
    } catch (error) {
      bubble(`Erro na resolução direta: ${error.message}`, 'error', 'Memoria.ia');
      log('direct_chat_error', {error: error.message, session_id: profileSession});
    }
  }

  // Replace only the click action. The Enter handler from app.js still calls this button,
  // therefore both mouse and keyboard follow the selected mode.
  send.onclick = async () => {
    if (answerMode?.value === 'direct') {
      await directMemorySend();
      return;
    }
    if (typeof originalSend === 'function') {
      return originalSend.call(send);
    }
  };

  // In LLM mode, preserve the cross-conversation promotion. In direct mode the
  // direct handler decides whether the input is an assertion (ingest) or intent
  // query (resolve), so questions are never written back as facts.
  send.addEventListener('click', () => {
    if (answerMode?.value === 'direct') return;
    const text = message.value.trim();
    if (!text) return;
    const signature = `${text}\u0000${Date.now() >> 10}`;
    if (signature === lastPromotion) return;
    lastPromotion = signature;

    fetch('/api/v1/conversation/ingest', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        role: 'user',
        text,
        session_id: profileSession,
        timestamp: new Date().toISOString()
      })
    }).then(async response => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `${response.status} ${response.statusText}`);
      }
    }).catch(error => {
      console.warn('[memoria] profile promotion failed:', error.message);
    });
  }, true);
})();
