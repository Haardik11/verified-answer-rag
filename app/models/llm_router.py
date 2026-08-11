"""
Every agent in the pipeline calls call_llm(role=..., messages=...) and never
touches OpenAI/Anthropic/Ollama directly. This is the whole point: swap a
model in app/config.py and every agent that uses that role picks it up
automatically, no code changes anywhere else.
"""

import os

from dotenv import load_dotenv

from app.config import ROLE_MODELS

load_dotenv()


def call_llm(role: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    if role not in ROLE_MODELS:
        raise ValueError(f"No model configured for role '{role}'. Add it to app/config.py")

    cfg = ROLE_MODELS[role]

    if cfg.provider == "openai":
        return _call_openai(cfg.model, messages, temperature, max_tokens)
    elif cfg.provider == "anthropic":
        return _call_anthropic(cfg.model, messages, temperature, max_tokens)
    elif cfg.provider == "ollama":
        return _call_ollama(cfg.model, messages, temperature, max_tokens)
    elif cfg.provider == "groq":
        return _call_groq(cfg.model, messages, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown provider '{cfg.provider}' for role '{role}'")


def _call_openai(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    from openai import OpenAI  # imported lazily so this package is only required if you actually use it

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    return resp.choices[0].message.content


def _call_anthropic(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system = next((m["content"] for m in messages if m["role"] == "system"), None)
    user_messages = [m for m in messages if m["role"] != "system"]
    resp = client.messages.create(
        model=model, system=system, messages=user_messages, max_tokens=max_tokens, temperature=temperature
    )
    return resp.content[0].text


def _call_groq(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    from openai import OpenAI  # Groq's API is OpenAI-compatible, so the same SDK works pointed at their endpoint

    client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    return resp.choices[0].message.content


def _call_ollama(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    import ollama  # requires `ollama serve` running locally, and the model pulled (e.g. `ollama pull llama3.2`)

    resp = ollama.chat(model=model, messages=messages, options={"temperature": temperature})
    return resp["message"]["content"]
