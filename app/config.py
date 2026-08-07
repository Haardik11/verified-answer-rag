"""
Central config: which model each agent role uses.

Change any of these to swap providers without touching any pipeline code.
"ollama"    -> free, local, unlimited. Good for dev/debugging and simple roles.
"openai"    -> paid API. Good for roles that need real judgment (verifier).
"anthropic" -> paid API. Same idea, different provider.
"""

from dataclasses import dataclass


@dataclass
class ModelConfig:
    provider: str  # "ollama" | "openai" | "anthropic"
    model: str


ROLE_MODELS = {
    # Cheap/simple roles: fine on a small local model while developing.
    "router": ModelConfig(provider="ollama", model="llama3.2"),
    "query_rewrite": ModelConfig(provider="ollama", model="llama3.2"),

    # Judgment-heavy roles: use a stronger paid model once you have keys set up.
    "extractor": ModelConfig(provider="ollama", model="llama3.2"),
    "verifier": ModelConfig(provider="ollama", model="llama3.2"),
    "synthesizer": ModelConfig(provider="ollama", model="llama3.2"),
}

# Example of what you'll change later, once you add API keys to .env:
# ROLE_MODELS["verifier"] = ModelConfig(provider="openai", model="gpt-4o")
# ROLE_MODELS["synthesizer"] = ModelConfig(provider="openai", model="gpt-4o-mini")
