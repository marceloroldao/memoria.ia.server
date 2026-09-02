from pathlib import Path


APP_JS = Path(__file__).resolve().parents[2] / "memoria-admin" / "static" / "app.js"


def test_normal_chat_persists_full_turns_and_semantic_memory():
    source = APP_JS.read_text(encoding="utf-8")

    assert "/api/v1/episodes" in source
    assert "/api/v1/conversation/ingest" in source
    assert "session_id:chatSessionId" in source
    assert "event_type:'chat_turn'" in source
    assert "persistChatTurn('user',msg)" in source
    assert "persistChatTurn('assistant',body.text)" in source


def test_chat_session_and_order_survive_browser_reload():
    source = APP_JS.read_text(encoding="utf-8")

    assert "memoria.chat.session_id" in source
    assert "memoria.chat.order" in source
    assert "localStorage.setItem(chatSessionStorageKey,chatSessionId)" in source
    assert "localStorage.setItem(chatOrderStorageKey,String(chatOrder))" in source
