from pathlib import Path
import sys

GATEWAY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWAY_DIR))

from gateway import ModelStore, gemini_to_openai, llama_to_openai


def test_store_keeps_multiple_provider_credentials_separate(tmp_path):
    store = ModelStore(tmp_path)
    openai = store.save({"name": "GPT", "provider": "openai", "model": "gpt-x", "api_key": "oa"})
    gemini = store.save({"name": "Gemini", "provider": "gemini", "model": "gemini-x", "api_key": "gm"})
    llama = store.save({"name": "Local", "provider": "llama", "model": "local.gguf"})
    public = store.list_public()
    assert len(public["profiles"]) == 3
    assert all("api_key" not in profile for profile in public["profiles"])
    assert openai["credential_configured"] is True
    assert gemini["credential_configured"] is True
    assert llama["credential_configured"] is None


def test_active_profile_cannot_be_deleted(tmp_path):
    store = ModelStore(tmp_path)
    profile = store.save({"name": "Local", "provider": "llama", "model": "local.gguf"})
    store.activate(profile["id"])
    try:
        store.delete(profile["id"])
    except Exception as error:
        assert getattr(error, "status", None) == 409
    else:
        raise AssertionError("active profile deletion should fail")


def test_gateway_migration_marker_is_persistent(tmp_path):
    store = ModelStore(tmp_path)
    assert not store.gateway_configured()
    store.mark_gateway_configured()
    assert ModelStore(tmp_path).gateway_configured()


def test_llama_uses_default_url_when_field_is_empty_or_friendly_default(tmp_path):
    store = ModelStore(tmp_path)
    empty = store.save({"name": "Local A", "provider": "llama", "model": "local-a", "base_url": ""})
    friendly = store.save({"name": "Local B", "provider": "llama", "model": "local-b", "base_url": "padrão"})
    shorthand = store.save({"name": "Local C", "provider": "llama", "model": "local-c", "base_url": "llama:8080/v1"})
    assert empty["base_url"] == "http://llama:8080/v1"
    assert friendly["base_url"] == "http://llama:8080/v1"
    assert shorthand["base_url"] == "http://llama:8080/v1"


def test_gemini_conversion_uses_openai_responses_shape():
    converted = gemini_to_openai(
        {"candidates": [{"content": {"parts": [{"text": "resposta"}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}},
        "gemini-test",
    )
    assert converted["output"][0]["content"][0]["text"] == "resposta"
    assert converted["usage"]["input_tokens"] == 3


def test_llama_conversion_uses_openai_responses_shape():
    converted = llama_to_openai(
        {"choices": [{"message": {"content": "local"}}], "usage": {"prompt_tokens": 4, "completion_tokens": 1}},
        "llama-test",
    )
    assert converted["output"][0]["content"][0]["text"] == "local"
    assert converted["usage"]["output_tokens"] == 1
