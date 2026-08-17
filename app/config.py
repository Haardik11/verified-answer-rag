"""
Central config: which model each agent role uses. Change one of these to
swap providers, no other code needs to touch it.

"ollama"    - free, local, unlimited. Fine for dev/debugging and simple roles.
"openai"    - paid API. Good for roles that need real judgment (verifier).
"anthropic" - paid API, same idea.
"groq"      - paid API, OpenAI-compatible. Bigger open-weight models (e.g.
              GPT-OSS 120B). Switched verifier/synthesizer here because the
              free local 3B model kept contradicting itself on grounding
              judgments and mangling source citations - see DEVLOG steps 12-13
              for the actual debugging story.
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
    # Groq deprecated llama-3.3-70b-versatile on 2026-08-16; openai/gpt-oss-120b
    # is its official recommended successor, also free-tier (see DEVLOG.md).
    "router": ModelConfig(provider="groq", model="openai/gpt-oss-120b"),
    "query_rewrite": ModelConfig(provider="groq", model="openai/gpt-oss-120b"),
    "verifier": ModelConfig(provider="groq", model="openai/gpt-oss-120b"),
    "synthesizer": ModelConfig(provider="groq", model="openai/gpt-oss-120b"),

    # Vision-capable, for OCR-ing scanned/image-only PDF pages that have no
    # extractable text layer. This is a paid preview model on Groq (not
    # covered by the free tier, unlike the text roles above) - used sparingly,
    # only for pages actually detected as scanned.
    "vision_ocr": ModelConfig(provider="groq", model="qwen/qwen3.6-27b"),
}
