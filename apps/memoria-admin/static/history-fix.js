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

  const originalPersist = window.persistChatTurn;
  if (typeof originalPersist !== 'function' || typeof window.api !== 'function') return;

  window.persistChatTurn = async function persistChatTurnWithProfile(role, text) {
    const result = await originalPersist(role, text);
    if (role !== 'user') return result;

    try {
      await window.api('/api/v1/conversation/ingest', {
        method: 'POST',
        body: JSON.stringify({
          role: 'user',
          text,
          session_id: 'profile:web',
          order: result.order,
          timestamp: new Date().toISOString()
        })
      });
      if (typeof window.log === 'function') {
        window.log('chat_profile_memory_promoted', {profile: 'profile:web', order: result.order});
      }
    } catch (error) {
      if (typeof window.log === 'function') {
        window.log('chat_profile_memory_error', {profile: 'profile:web', error: error.message});
      }
      // The original session write remains authoritative if promotion fails.
    }
    return result;
  };
})();
