"""
FastAPI wrapper around the self-correcting agent. One real endpoint -
POST /ask - runs a question through the full retrieve -> synthesize ->
verify loop and returns the answer along with its sources and
verification status, so a frontend can show the user not just an answer
but how confident the system actually is in it.

Run with: PYTHONPATH=. uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent.graph import answer_question

app = FastAPI(title="VerifiedRAG")

# Wide open CORS is fine here - this is a local-only dev/demo tool, not a
# deployed service with real users to protect.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


class Source(BaseModel):
    source: str
    chunk_index: int
    score: float
    text: str


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    attempts: int
    verification_reason: str
    sources: list[Source]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    result = answer_question(request.question)
    return AskResponse(
        answer=result["answer"],
        grounded=result["grounded"],
        attempts=result["attempts"],
        verification_reason=result["verification_reason"],
        sources=[
            Source(source=c.source, chunk_index=c.chunk_index, score=c.score, text=c.text)
            for c in result["chunks"]
        ],
    )
