from fastapi.testclient import TestClient

from memoria_resolutiva.product_http import create_app
from memoria_resolutiva.product_identity import OrganizationIdentity
from memoria_resolutiva.product_service import EnterpriseMemoryService


def test_web_ui_is_served_from_product_app(tmp_path):
    service = EnterpriseMemoryService(OrganizationIdentity("org-a", "Org A"))
    client = TestClient(create_app(service, api_key="secret", data_dir=tmp_path))

    root = client.get("/")
    css = client.get("/ui/style.css")
    js = client.get("/ui/app.js")

    assert root.status_code == 200
    assert "Memoria.ia Enterprise" in root.text
    assert "Configuration" in root.text
    assert "LLM provider" in root.text
    assert "License" in root.text
    assert "Applications" in root.text
    assert "Create application credential" in root.text
    assert css.status_code == 200
    assert "chat-panel" in css.text
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
