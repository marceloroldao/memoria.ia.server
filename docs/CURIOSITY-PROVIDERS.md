# Curiosity discovery providers

The V2 curiosity engine uses an ordered provider chain instead of depending on a single search endpoint.

1. `duckduckgo`: opportunistic HTML discovery. Some datacenter IPs receive HTTP 202/challenge pages; this is treated as an empty provider, not as a fatal engine failure.
2. `wikipedia`: keyless MediaWiki OpenSearch fallback used when the primary provider returns no usable links or errors.

Every successful evidence event records the provider that supplied the URL. Provider failures and fallbacks are observable through `provider_error` and `provider_fallback` events.

External content remains `epistemic_status=web_observation`, confidence 0.25, and is never promoted automatically into personal memory.
