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
    "Respond with only the transcribed text, no commentary."
)


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
    response = call_llm(role="vision_ocr", messages=messages, max_tokens=2048)
    # The configured vision model is a "thinking" model that prepends its raw
    # chain-of-thought in <think> tags despite being told not to - found via a
    # real test transcription. Strip it so reasoning noise never ends up
    # chunked and indexed as if it were real document content.
    return re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
