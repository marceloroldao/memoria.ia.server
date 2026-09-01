from __future__ import annotations

import hmac

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .product_config import ProductConfigurationStore


class LLMConfigurationRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(default="", max_length=128)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class LicenseConfigurationRequest(BaseModel):
    license_id: str = Field(min_length=1, max_length=256)
    plan: str = Field(default="early_access", min_length=1, max_length=64)
    valid_until: str | None = Field(default=None, max_length=64)
    max_nodes: int = Field(default=1, ge=1, le=1_000_000)
    capabilities: list[str] = Field(default_factory=lambda: ["memory.read", "memory.write", "chat.use"])


def attach_configuration_routes(
    app: FastAPI,
    *,
    api_key: str,
    store: ProductConfigurationStore,
) -> None:
    """Attach administrator-only local configuration endpoints.

    Secrets are write-only through this API: responses expose only whether a
    credential is configured, never the credential value itself.
    """

    def require_admin(x_memoria_key: str | None = Header(default=None)) -> None:
        if x_memoria_key is None or not hmac.compare_digest(x_memoria_key, api_key):
            raise HTTPException(status_code=401, detail="administrator credential required")

    @app.get("/api/v1/admin/configuration")
    def configuration_status(x_memoria_key: str | None = Header(default=None)):
        require_admin(x_memoria_key)
        return {
            "llm": store.llm_public_status(),
            "license": store.license_public_status(),
            "restart_policy": "LLM/provider changes take effect after service restart in product-alpha.",
            "secret_policy": "Provider credentials are never returned by this API.",
        }

    @app.put("/api/v1/admin/configuration/llm")
    def configure_llm(request: LLMConfigurationRequest, x_memoria_key: str | None = Header(default=None)):
        require_admin(x_memoria_key)
        try:
            store.configure_llm(provider=request.provider, model=request.model, api_key=request.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "configured": True,
            "llm": store.llm_public_status(),
            "restart_required": True,
        }

    @app.put("/api/v1/admin/configuration/license")
    def configure_license(request: LicenseConfigurationRequest, x_memoria_key: str | None = Header(default=None)):
        require_admin(x_memoria_key)
        try:
            store.configure_license(
                license_id=request.license_id,
                plan=request.plan,
                valid_until=request.valid_until,
                max_nodes=request.max_nodes,
                capabilities=request.capabilities,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "configured": True,
            "license": store.license_public_status(),
            "validation": "local-alpha-metadata-only",
            "external_authority": "not_configured",
        }
