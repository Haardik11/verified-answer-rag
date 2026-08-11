"""
Central config: which model each agent role uses.

Change any of these to swap providers without touching any pipeline code.
"ollama"    -> free, local, unlimited. Good for dev/debugging and simple roles.
"openai"    -> paid API. Good for roles that need real judgment (verifier).
"anthropic" -> paid API. Same idea, different provider.
"groq"      -> paid API (OpenAI-compatible). Hosts larger open-weight models
               (e.g. Llama 3.3 70B) - used for verifier and synthesizer, since
               the free local 3B model wasn't reliably self-consistent at
               judging whether an answer is grounded, and also tended to
               paraphrase source citations incorrectly in its written answers
               (see DEVLOG.md steps 12-13).
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
    "verifier": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
    "synthesizer": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
}
