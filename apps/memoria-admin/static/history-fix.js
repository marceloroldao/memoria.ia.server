// Defensive hotfix: never erase the visible chat when history refresh is unavailable.
// The main app owns the durable history contract; this wrapper only preserves UX state.
(() => {
  const original = window.loadConversationHistory;
  if (typeof original !== 'function') return;
  window.loadConversationHistory = async function (...args) {
    const conversation = document.getElementById('conversation');
    const snapshot = conversation ? conversation.innerHTML : '';
    try {
      return await original.apply(this, args);
    } finally {
      const state = document.getElementById('chatPersistenceState');
      if (conversation && state && state.textContent.includes('histórico indisponível') && snapshot) {
        conversation.innerHTML = snapshot;
        conversation.scrollTop = conversation.scrollHeight;
      }
    }
  };
})();
