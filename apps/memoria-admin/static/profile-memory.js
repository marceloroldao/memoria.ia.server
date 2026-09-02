// Cross-conversation semantic memory for the web admin chat.
// User assertions are promoted to a stable profile namespace; assistant output is not.
(() => {
  const originalPersistChatTurn = window.persistChatTurn;
  if (typeof originalPersistChatTurn !== 'function' || typeof window.api !== 'function') return;

  window.persistChatTurn = async function persistChatTurnWithProfile(role, text) {
    const result = await originalPersistChatTurn(role, text);
    if (role !== 'user') return result;

    const timestamp = new Date().toISOString();
    try {
      await window.api('/api/v1/conversation/ingest', {
        method: 'POST',
        body: JSON.stringify({
          role: 'user',
          text,
          session_id: 'profile:web',
          order: result.order,
          timestamp
        })
      });
      if (typeof window.log === 'function') {
        window.log('chat_profile_memory_promoted', { profile: 'profile:web', order: result.order });
      }
    } catch (error) {
      if (typeof window.log === 'function') {
        window.log('chat_profile_memory_error', { profile: 'profile:web', error: error.message });
      }
      // Session persistence remains authoritative even if profile promotion fails.
    }
    return result;
  };
})();
