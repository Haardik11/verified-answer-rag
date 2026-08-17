# VerifiedRAG

A self-correcting, multimodal document Q&A agent — not just another
"chat with your PDF" demo. I got tired of RAG chatbots that trust their
own first answer no matter what, so this one checks whether its answer
is actually supported by what it retrieved before showing it to you, and
automatically retries with a rewritten search if it isn't confident,
instead of quietly shipping something unsupported.

For the full build story — every real bug I found, how I tracked it
down, how I fixed it, with actual evidence, not just "it works now" —
see [`DEVLOG.md`](./DEVLOG.md). I kept it updated the whole way through.

## What makes this different from a basic RAG chatbot

- **Self-correction, not just retrieval.** A `retrieve -> synthesize ->
  verify` loop — if a separate verification step decides an answer isn't
  actually grounded in the retrieved evidence, the query gets rewritten
  and it retries (capped, so it can't loop forever). This is the
  Corrective RAG / Self-RAG pattern.
- **Hybrid retrieval.** Dense (semantic, embeddings + Qdrant) and sparse
  (keyword, BM25) search combined via Reciprocal Rank Fusion, not just
  one or the other.
- **Honest about its own confidence.** Every answer gets labeled
  "Verified," "Unverified," or "General knowledge — not from your
  documents" — never quietly presented as grounded when it isn't. A
  message router also skips retrieval entirely for greetings/small talk
  instead of running the whole pipeline for no reason.
- **Multimodal ingestion.** PDFs, plain text, spreadsheets (CSV/Excel),
  and scanned/image-only PDF pages (via vision-model OCR) all go through
  the same pipeline.
- **Measured, not just claimed.** A real evaluation harness (`app/eval/`)
  scores the system against ground truth I hand-verified myself, and
  reports an actual hallucination rate broken down by failure-mode
  category (simple lookups, paraphrased questions, multi-hop reasoning,
  adversarial/unanswerable questions, exact-figure lookups). See
  `eval_results.json` for the latest run.

## Architecture

```
data/  -->  app/ingestion/  -->  app/retrieval/  -->  app/agent/  -->  app/main.py (FastAPI)  -->  frontend/ (React)
(PDF, text,     (loaders,          (embeddings,          (LangGraph:                (POST /ask)         (chat UI)
 CSV/xlsx,       chunker)           Qdrant, BM25,          route -> retrieve ->
 scanned PDF)                       RRF fusion)            synthesize -> verify)
```

- `app/config.py` + `app/models/llm_router.py` — every agent calls one
  function, `call_llm(role, messages)`. Which provider/model handles each
  role lives in one config dict, so swapping a model is a one-line
  change, not a code change. This actually saved me more than once (see
  the devlog).
- `app/ingestion/` — loaders for PDF, text, spreadsheets, and scanned-PDF
  OCR, plus chunking.
- `app/retrieval/` — dense embeddings (fastembed/ONNX), Qdrant vector
  store, BM25 keyword search, RRF fusion.
- `app/agent/` — the LangGraph self-correcting loop, plus the verifier.
- `app/eval/` — the evaluation harness (test cases, scorer, runner).
- `app/main.py` — the FastAPI backend.
- `frontend/` — the React/TypeScript chat UI.

## Try it

```bash
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY (used for verifier/synthesizer/router)

# Build the searchable index from the sample documents in data/
PYTHONPATH=. python3 scripts/build_index.py

# Start the backend
PYTHONPATH=. uvicorn app.main:app --port 8000

# In another terminal, start the frontend
cd frontend
npm install
npm run dev   # opens on http://localhost:5173
```

Run the evaluation harness (reports a hallucination rate over the test cases):

```bash
PYTHONPATH=. python3 scripts/run_eval.py
```

## Status

Done and tested: ingestion (including multimodal), hybrid retrieval, the
self-correcting agent loop, the FastAPI backend, the React frontend, and
the evaluation harness (still catching up on a full run — see
`eval_results.json` and `DEVLOG.md` steps 24-25 for where it's at and
why). I deliberately didn't build Docker/AWS deployment — decided that
wasn't worth the time versus the parts that actually prove the project's
core claim.
