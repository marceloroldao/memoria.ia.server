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

  // Do not depend on replacing the global persistChatTurn binding: capture the
  // send action before app.js clears the textarea and promote only user text.
  const send = document.getElementById('sendMemoria');
  const message = document.getElementById('message');
  if (!send || !message) return;

  let lastPromotion = '';
  send.addEventListener('click', () => {
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
        session_id: 'profile:web',
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
