from fastapi.testclient import TestClient

from memoria_resolutiva.product_http import create_app
from memoria_resolutiva.product_identity import OrganizationIdentity
from memoria_resolutiva.product_service import EnterpriseMemoryService


def test_web_ui_is_served_from_product_app(tmp_path):
    service = EnterpriseMemoryService(OrganizationIdentity("org-a", "Org A"))
    client = TestClient(create_app(service, api_key="secret", data_dir=tmp_path))
    root = client.get("/"); css = client.get("/ui/style.css"); js = client.get("/ui/app.js")
    assert root.status_code == 200
    assert "Memoria.ia Enterprise" in root.text
    assert "Configuration" in root.text
    assert "LLM provider" in root.text
    assert "License" in root.text
    assert "Applications" in root.text
    assert "Create application credential" in root.text
    assert css.status_code == 200 and "chat-panel" in css.text
    assert js.status_code == 200
    assert "/api/v1/chat/compare" in js.text
    assert "/api/v1/admin/configuration/llm" in js.text
    assert "/api/v1/admin/configuration/license" in js.text
    assert "/api/v1/admin/applications" in js.text
    assert "SAVE THIS CREDENTIAL NOW" in js.text


def test_web_ui_does_not_embed_server_secret(tmp_path):
    service = EnterpriseMemoryService(OrganizationIdentity("org-a", "Org A"))
    client = TestClient(create_app(service, api_key="server-only-secret", data_dir=tmp_path))
    for path in ("/", "/ui/app.js", "/ui/style.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert "server-only-secret" not in response.text


def test_server_admin_chat_keeps_bdr_history_contract_in_static_assets():
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    direct_js = (static / "history-fix.js").read_text(encoding="utf-8")
    curiosity_js = (static / "curiosity-admin.js").read_text(encoding="utf-8")
    css = (static / "style.css").read_text(encoding="utf-8")
    assert 'id="conversationHistory"' in html
    assert 'id="newConversation"' in html
    assert "/api/v1/episodes/history?event_type=chat_turn" in js
    assert "openPersistedConversation" in js and "loadConversationHistory" in js
    assert ".history-panel" in css and ".history-item.active" in css
    assert 'id="chatAnswerMode"' in html and "Memoria direta · sem LLM" in html
    assert "/api/v1/conversation/ingest" in direct_js
    assert "/api/v1/conversation/resolve" in direct_js
    assert "direct-no-llm" in direct_js
    assert "questions are never written back as facts" in direct_js
    assert 'data-page="curiosity"' in html
    assert 'id="curiosityTrajectory"' in html
    assert "/api/server/v1/curiosity" in curiosity_js
    assert "curiosity/jump" in curiosity_js
