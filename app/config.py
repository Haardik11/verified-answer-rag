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
    # Not yet used by any pipeline code - placeholder for a future feature.
    "extractor": ModelConfig(provider="ollama", model="llama3.2"),

    # Actually used roles - all on Groq, so no local Ollama server is required to run this project.
    "router": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
    "query_rewrite": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
    "verifier": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
    "synthesizer": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),

    # Vision-capable, for OCR-ing scanned/image-only PDF pages that have no
    # extractable text layer. This is a paid preview model on Groq (not
    # covered by the free tier, unlike the text roles above) - used sparingly,
    # only for pages actually detected as scanned.
    "vision_ocr": ModelConfig(provider="groq", model="qwen/qwen3.6-27b"),
}
