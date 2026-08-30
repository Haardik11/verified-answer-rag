"""
OCR for scanned/image-only PDF pages via a vision-capable LLM, since
pypdf can only extract an existing text layer - a scanned page has no
text layer to pull from, just pixels. Routed through call_llm like every
other agent call, using the "vision_ocr" role so the model/provider can
be swapped via app/config.py like any other role.
"""

import base64
import re

from app.models.llm_router import call_llm

VISION_OCR_PROMPT = (
    "Transcribe all readable text from this image exactly as it appears. "
    "Respond with only the transcribed text, no commentary. Output it exactly "
    "once - do not restate, repeat, or re-attempt the transcription after "
    "you've written it. Stop generating immediately after the last word."
)


def _truncate_at_repeated_line(text: str) -> str:
    """
    Workaround for a real, reproducible failure in this model (see DEVLOG):
    on at least one test image it transcribes correctly, then restates the
    first line verbatim and continues into a second, garbled attempt at the
    same content. Neither temperature=0 nor an explicit "don't repeat
    yourself" prompt instruction stopped this - it's a deterministic bias in
    the model, not sampling noise, and isn't fixed at that level. This does
    not fix why the model does it; it just detects the exact signature of
    that failure (a non-empty line reappearing verbatim) and cuts the output
    there, since everything from that point on has been garbage in every
    observed case so far.
    """
    lines = text.split("\n")
    seen = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and stripped in seen:
            return "\n".join(lines[:i]).strip()
        if stripped:
            seen.add(stripped)
    return text


def ocr_image(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ],
        }
    ]
    response = call_llm(role="vision_ocr", messages=messages, temperature=0.0, max_tokens=2048)
    # The configured vision model is a "thinking" model that prepends its raw
    # chain-of-thought in <think> tags despite being told not to - found via a
    # real test transcription. Strip it so reasoning noise never ends up
    # chunked and indexed as if it were real document content.
    text = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    return _truncate_at_repeated_line(text)
